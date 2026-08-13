"""AI generation API endpoints."""
import asyncio
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import Review, WorkPackage
from app.models.enums import WorkflowStatus
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

        review_feedback = {}
        if work_package and work_package.status == WorkflowStatus.REWORK_REQUIRED:
            latest_review = db.query(Review).filter(
                Review.work_package_id == work_package.id,
                Review.decision.in_(["rework_required", "rejected"]),
            ).order_by(Review.completed_at.desc(), Review.started_at.desc()).first()
            if latest_review:
                review_feedback = {
                    "decision": latest_review.decision,
                    "general_comments": latest_review.comments or "",
                    "implementation_review_notes": latest_review.code_review_notes or "",
                    "rollback_review_notes": latest_review.rollback_review_notes or "",
                    "security_review_notes": latest_review.security_review_notes or "",
                    "impact_review_notes": latest_review.impact_review_notes or "",
                }

        service = AIGenerationService()
        result = await asyncio.to_thread(
            service.generate,
            title=title,
            description=description,
            change_type=change_type,
            target_host=target_host,
            platform=platform,
            question_responses=request.question_responses,
            force_final_generation=bool(request.question_responses) or bool(review_feedback),
            review_feedback=review_feedback,
            previous_implementation_code=(work_package.generated_code or "") if review_feedback else "",
            previous_rollback_code=(work_package.rollback_procedure or "") if review_feedback else "",
            previous_implementation_procedure=(work_package.generated_procedure or "") if review_feedback else "",
            previous_impact_analysis=(work_package.impact_analysis or {}) if review_feedback else {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    ai_questions = [question.model_dump(mode="json") for question in result.questions]
    questions = []
    seen_keys = set()
    seen_texts = set()
    forbidden_question_terms = (
        "ip address", "hostname/ip", "target server", "emergency contact",
        "execution window", "timezone", "expected impact", "downtime",
        "rollback method", "restoration point", "successful execution be verified",
        "on-call", "monitoring team", "approval", "reference number",
    )
    request_text = f"{title} {description}".lower()
    is_kubernetes_request = any(
        term in request_text for term in ("kubernetes", "k8s", "namespace", "kubectl")
    )
    is_memory_alert = "memory" in request_text and any(
        term in request_text for term in ("utilization", "usage", "high memory", "oom")
    )
    for question in ai_questions:
        item = dict(question)
        item["source"] = "ai"
        item["question_type"] = getattr(item.get("question_type"), "value", item.get("question_type", "text"))
        normalized_text = " ".join(item.get("question_text", "").lower().split())
        if any(term in normalized_text for term in forbidden_question_terms):
            continue
        if not is_kubernetes_request and any(
            term in normalized_text
            for term in ("kubernetes", "cluster", "namespace", "replica", "resource limits")
        ):
            continue
        if is_memory_alert and any(
            term in normalized_text
            for term in ("linux distribution", "optimize memory", "memory utilization strategy", "services should be restarted")
        ):
            continue
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
