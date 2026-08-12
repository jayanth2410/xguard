"""AI generation API endpoints."""
import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import WorkPackage
from app.core.clarification_questions import get_questions_for_change_type
from app.models.enums import ChangeType
from app.services.ai_generation_service import AIGenerationService

router = APIRouter()


class GenerateScriptRequest(BaseModel):
    work_package_id: Optional[UUID] = None
    change_type: str = ""
    title: str = ""
    description: str = ""
    target_hosts: List[str] = Field(default_factory=list)
    target_host: str = ""
    platform: str = ""
    question_responses: List[dict] = Field(default_factory=list)


class GenerateScriptResponse(BaseModel):
    ready_to_generate: bool
    script: str
    rollback: str
    language: str
    intent: str
    detected_change_type: str
    implementation_procedure: str
    pre_checks: dict
    post_checks: dict
    impact_analysis: dict
    questions: List[dict]


@router.post("/generate-script", response_model=GenerateScriptResponse)
async def generate_script(
    request: GenerateScriptRequest,
    db: Session = Depends(get_db),
):
    """Generate and optionally persist implementation content using Groq."""
    work_package = None
    if request.work_package_id:
        work_package = db.query(WorkPackage).filter(
            WorkPackage.id == request.work_package_id
        ).first()
        if not work_package:
            raise HTTPException(status_code=404, detail="Work package not found")

    try:
        title = request.title or (work_package.title if work_package else "")
        description = request.description or (
            work_package.description if work_package else ""
        )
        change_type = request.change_type or (
            work_package.change_type.value if work_package else ""
        )
        target_host = request.target_host
        if not target_host and request.target_hosts:
            target_host = request.target_hosts[0]
        if not target_host and work_package and work_package.target_hosts:
            target_host = work_package.target_hosts[0]

        variables = dict(work_package.variables or {}) if work_package else {}
        platform = (
            request.platform
            or variables.get("platform", "")
            or variables.get("operating_system", "")
        )
        if not platform and work_package and work_package.target_infrastructure:
            infrastructure = work_package.target_infrastructure
            platform = infrastructure[0] if isinstance(infrastructure, list) else str(infrastructure)

        service = AIGenerationService()
        result = await asyncio.to_thread(
            service.generate,
            title=title,
            description=description,
            change_type=change_type,
            target_host=target_host,
            platform=platform,
            question_responses=request.question_responses,
            force_final_generation=bool(request.question_responses),
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    ai_questions = [question.model_dump(mode="json") for question in result.questions]
    try:
        resolved_change_type = ChangeType(result.change_type or change_type)
    except ValueError:
        resolved_change_type = work_package.change_type if work_package else ChangeType.SERVER
    database_questions = get_questions_for_change_type(
        resolved_change_type,
        description=description,
        title=title,
        ci_info={"ci_name": target_host} if target_host else None,
    )
    questions = []
    seen_keys = set()
    existing_questions = list(work_package.ai_questions or []) if work_package else []
    seen_texts = set()
    sourced_questions = (
        [(question, "database") for question in database_questions]
        + [(question, question.get("source", "ai")) for question in existing_questions]
        + [(question, "ai") for question in ai_questions]
    )
    for question, source in sourced_questions:
        item = dict(question)
        item["source"] = source
        item["question_type"] = getattr(item.get("question_type"), "value", item.get("question_type", "text"))
        normalized_text = " ".join(item.get("question_text", "").lower().split())
        if item["question_key"] not in seen_keys and normalized_text not in seen_texts:
            seen_keys.add(item["question_key"])
            seen_texts.add(normalized_text)
            questions.append(item)

    answers_by_key = {
        answer.get("question_key"): answer
        for answer in request.question_responses
        if answer.get("question_key")
        and str(answer.get("response_text", answer.get("response", ""))).strip()
    }
    unanswered_required = [
        question for question in questions
        if question.get("source") == "ai"
        and question.get("is_required", True)
        and question["question_key"] not in answers_by_key
    ]
    ready_to_generate = result.ready_to_generate and not unanswered_required
    pre_checks = {"checks": [check.model_dump() for check in result.pre_checks]}
    post_checks = {"checks": [check.model_dump() for check in result.post_checks]}

    if work_package:
        work_package.tokens_used = (work_package.tokens_used or 0) + service.last_total_tokens
        current_month = datetime.utcnow().strftime("%Y-%m")
        if work_package.token_usage_month != current_month:
            work_package.token_usage_month = current_month
            work_package.monthly_tokens_used = 0
        work_package.monthly_tokens_used = (
            work_package.monthly_tokens_used or 0
        ) + service.last_total_tokens
        if ready_to_generate:
            work_package.generated_code = result.implementation_code
            work_package.rollback_procedure = result.rollback_code
            work_package.generated_procedure = result.implementation_procedure
            work_package.pre_checks = pre_checks
            work_package.post_checks = post_checks
            work_package.impact_analysis = result.impact_analysis
        work_package.ai_questions = questions
        work_package.ai_question_responses = list(answers_by_key.values())
        variables.update({
            "ai_generated": True,
            "ai_intent": result.intent,
            "ai_model": service.model,
        })
        if platform:
            variables["platform"] = platform
        work_package.variables = variables
        db.commit()

    return GenerateScriptResponse(
        ready_to_generate=ready_to_generate,
        script=result.implementation_code if ready_to_generate else "",
        rollback=result.rollback_code if ready_to_generate else "",
        language=result.language,
        intent=result.intent,
        detected_change_type=result.change_type,
        implementation_procedure=result.implementation_procedure,
        pre_checks=pre_checks,
        post_checks=post_checks,
        impact_analysis=result.impact_analysis,
        questions=questions,
    )
