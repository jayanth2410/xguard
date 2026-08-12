"""Groq-backed generation of clarification, implementation, and rollback content."""
import json
import re
from typing import Any, Dict, List, Literal, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import settings

try:
    from openai import OpenAI
except ImportError:  # Support environments that have an older OpenAI package.
    OpenAI = None


class AICheck(BaseModel):
    name: str
    description: str
    command: str = ""
    expected_result: str = ""


class AIQuestion(BaseModel):
    question_key: str
    question_text: str
    question_type: Literal[
        "text", "select", "multi_select", "date_time", "confirmation"
    ] = "text"
    category: str = "ai"
    is_required: bool = True
    options: Optional[List[str]] = None
    order: int = 0
    placeholder: Optional[str] = None

    @field_validator("question_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        key = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
        if not key:
            raise ValueError("question_key cannot be empty")
        return key[:100]

    @field_validator("options")
    @classmethod
    def validate_options(cls, value, info):
        if value is not None:
            value = [str(option).strip() for option in value if str(option).strip()]
        return value or None


class AIGenerationResult(BaseModel):
    ready_to_generate: bool = False
    intent: str
    change_type: str
    language: str = "bash"
    implementation_code: str = ""
    rollback_code: str = ""
    implementation_procedure: str = ""
    pre_checks: List[AICheck] = Field(default_factory=list)
    post_checks: List[AICheck] = Field(default_factory=list)
    impact_analysis: Dict[str, Any] = Field(default_factory=dict)
    questions: List[AIQuestion] = Field(default_factory=list)

    @field_validator("implementation_procedure", mode="before")
    @classmethod
    def normalize_procedure(cls, value):
        if isinstance(value, list):
            return "\n".join(
                f"{index}. {step}"
                for index, step in enumerate(value, start=1)
            )
        return value


class AIGenerationService:
    """Generate a strict, validated JSON response using Groq's OpenAI API."""

    def __init__(self):
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not configured under [ai] in config.ini")
        self.client = (
            OpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url=settings.AI_BASE_URL,
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
            if OpenAI is not None else None
        )
        self.model = settings.AI_MODEL
        self.last_total_tokens = 0

    def generate(
        self,
        *,
        title: str,
        description: str,
        change_type: str,
        target_host: str = "",
        platform: str = "",
        question_responses: Optional[List[Dict[str, Any]]] = None,
        force_final_generation: bool = False,
    ) -> AIGenerationResult:
        if not title.strip() and not description.strip():
            raise ValueError("A title or description is required for AI generation")

        prompt = self._build_prompt(
            title=title,
            description=description,
            change_type=change_type,
            target_host=target_host,
            platform=platform,
            question_responses=question_responses or [],
            force_final_generation=force_final_generation,
        )
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are XGuard's senior change automation engineer. "
                        "Return only valid JSON matching the requested schema."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            if self.client is not None:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                content = completion.choices[0].message.content or ""
                self.last_total_tokens = int(
                    getattr(completion.usage, "total_tokens", 0) or 0
                )
            else:
                response = httpx.post(
                    f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2,
                    },
                    timeout=settings.AI_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                response_data = response.json()
                content = response_data["choices"][0]["message"]["content"] or ""
                self.last_total_tokens = int(
                    response_data.get("usage", {}).get("total_tokens", 0) or 0
                )
        except Exception as exc:
            raise ValueError(f"Groq generation failed: {exc.__class__.__name__}") from exc

        try:
            parsed = json.loads(content)
            result = AIGenerationResult.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("Groq returned an invalid generation response") from exc

        self._validate_result(result)
        return result

    @staticmethod
    def _validate_result(result: AIGenerationResult) -> None:
        if result.ready_to_generate and not result.implementation_code.strip():
            raise ValueError("AI response did not include implementation code")
        if result.ready_to_generate and not result.rollback_code.strip():
            raise ValueError("AI response did not include rollback code")
        if not result.ready_to_generate and not result.questions:
            raise ValueError(
                "AI did not generate code or provide any remaining clarification questions"
            )

        seen = set()
        for index, question in enumerate(result.questions, start=1):
            if question.question_key in seen:
                raise ValueError(f"AI returned duplicate question key: {question.question_key}")
            seen.add(question.question_key)
            question.order = index
            if question.question_type in {"select", "multi_select"} and not question.options:
                raise ValueError(
                    f"Select question {question.question_key} has no options"
                )

    @staticmethod
    def _build_prompt(
        *,
        title: str,
        description: str,
        change_type: str,
        target_host: str,
        platform: str,
        question_responses: List[Dict[str, Any]],
        force_final_generation: bool,
    ) -> str:
        answers_json = json.dumps(question_responses, indent=2, default=str)
        final_instruction = (
            "FINAL GENERATION REQUEST: The user has answered the questions already presented. "
            "Set ready_to_generate to true and generate the final implementation and rollback code. "
            "Only return ready_to_generate=false when a specific new critical detail is missing, "
            "and in that case you MUST include the corresponding question."
            if force_final_generation else
            "ANALYSIS REQUEST: Identify any critical missing details before final generation."
        )
        return f"""
Analyse this IT change request and generate safe implementation content.

TITLE:
{title}

DESCRIPTION:
{description}

CURRENT CHANGE TYPE:
{change_type or 'unknown'}

SERVICENOW CI / TARGET (may be empty):
{target_host or 'not provided'}

OPERATING SYSTEM / PLATFORM (may be empty):
{platform or 'not provided'}

CLARIFICATION ANSWERS:
{answers_json if question_responses else 'No answers provided yet'}

CURRENT REQUEST MODE:
{final_instruction}

Requirements:
1. Infer the actual intent and most suitable change type.
2. First determine whether critical information required to generate safe executable code is missing.
3. If critical information is missing, set ready_to_generate to false, return only the missing questions,
   and return empty strings for implementation_code, rollback_code, and implementation_procedure.
4. If all critical information is available, set ready_to_generate to true and generate complete,
   executable implementation and rollback code without Markdown fences.
5. Generate a concise implementation procedure, pre-checks, post-checks, and impact analysis.
6. Generate only questions whose answers are genuinely missing and required for safe execution.
7. Do not repeat questions that have a meaningful answer in the supplied answers.
8. Do not ask for values already stated in the title, description, or ServiceNow target.
9. If a target is supplied, do not ask the user to type the same target again.
10. Generate code appropriate for the supplied operating system or platform.
11. If the platform is missing and affects command syntax, ask for it rather than guessing.
12. Supported question types are text, select, multi_select, date_time, and confirmation.
    Use select or multi_select only when you provide explicit options.
13. Never include credentials, API keys, or invented production values.
14. Prefer idempotent commands and include verification and failure handling.
15. Format implementation_code and rollback_code as readable scripts with real newline
    characters. Put each executable command on its own line. Do not combine independent
    commands into a single line with semicolons or command-chain operators. Keep required
    language constructs such as loops, conditionals, and continuations correctly indented.
16. Do not return escaped newline text such as \\n inside the generated script content;
    encode newlines normally as part of the JSON string.

Return exactly one JSON object with this structure:
{{
  "ready_to_generate": true,
  "intent": "short intent name",
  "change_type": "network|server|database|cloud|application|security|container|monitoring",
  "language": "bash|powershell|sql|other",
  "implementation_code": "complete executable code",
  "rollback_code": "complete executable rollback code",
  "implementation_procedure": "concise ordered procedure",
  "pre_checks": [
    {{"name":"...", "description":"...", "command":"...", "expected_result":"..."}}
  ],
  "post_checks": [
    {{"name":"...", "description":"...", "command":"...", "expected_result":"..."}}
  ],
  "impact_analysis": {{
    "risk_level": "green|amber|red",
    "impact_summary": "...",
    "downtime_estimate": "...",
    "risk_factors": [],
    "mitigation_strategies": []
  }},
  "questions": [
    {{
      "question_key": "stable_snake_case_key",
      "question_text": "clear question",
      "question_type": "text|select|multi_select|date_time|confirmation",
      "category": "intent-specific category",
      "is_required": true,
      "options": null,
      "placeholder": "example answer or null"
    }}
  ]
}}
""".strip()
