from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.resource_ops import AIEstimate, DailyWorkPlan
from app.llm.provider import get_llm
from app.llm.structured import parse_and_validate_llm_output

logger = logging.getLogger(__name__)


class AIEstimateLLMResponse(BaseModel):
    baseline_hours: float = Field(..., description="Estimated baseline hours based on inputs")
    optimistic_hours: float = Field(..., description="Best case effort in hours")
    most_likely_hours: float = Field(..., description="Most probable effort in hours")
    pessimistic_hours: float = Field(..., description="Worst case effort in hours")
    confidence_score: float = Field(..., description="Confidence score from 0.0 to 1.0")
    assumptions: str = Field(..., description="Assumptions made for the estimate")
    risk_factors: str = Field(..., description="Identified risk factors that could delay execution")
    suggested_breakdown: dict[str, float] = Field(..., description="Suggested breakdown of sub-activities and their hours")


# Baseline templates for various QA tasks
BASELINE_TEMPLATES = {
    "Requirement Analysis": {"baseline": 4.0, "complexity_mult": {"Low": 0.8, "Medium": 1.0, "High": 1.5}},
    "Test Planning": {"baseline": 8.0, "complexity_mult": {"Low": 0.7, "Medium": 1.0, "High": 1.8}},
    "Test Scenario Design": {"baseline": 6.0, "complexity_mult": {"Low": 0.8, "Medium": 1.0, "High": 1.6}},
    "Test Case Design": {"baseline": 8.0, "complexity_mult": {"Low": 0.8, "Medium": 1.0, "High": 1.6}},
    "Test Case Review": {"baseline": 2.0, "complexity_mult": {"Low": 0.5, "Medium": 1.0, "High": 2.0}},
    "Manual Test Execution": {"baseline": 8.0, "complexity_mult": {"Low": 0.6, "Medium": 1.0, "High": 2.0}},
    "Automation Development": {"baseline": 12.0, "complexity_mult": {"Low": 0.7, "Medium": 1.0, "High": 2.2}},
    "Automation Execution": {"baseline": 2.0, "complexity_mult": {"Low": 0.5, "Medium": 1.0, "High": 2.0}},
    "Defect Analysis": {"baseline": 3.0, "complexity_mult": {"Low": 0.6, "Medium": 1.0, "High": 1.8}},
    "Environment Validation": {"baseline": 4.0, "complexity_mult": {"Low": 0.5, "Medium": 1.0, "High": 1.8}},
    "Database Validation": {"baseline": 6.0, "complexity_mult": {"Low": 0.7, "Medium": 1.0, "High": 1.8}},
    "Release Readiness": {"baseline": 8.0, "complexity_mult": {"Low": 0.5, "Medium": 1.0, "High": 2.0}},
    "Meeting / Planning": {"baseline": 2.0, "complexity_mult": {"Low": 1.0, "Medium": 1.0, "High": 1.0}},
    "Other": {"baseline": 4.0, "complexity_mult": {"Low": 0.8, "Medium": 1.0, "High": 1.5}},
}


class AIEstimateService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_estimate(
        self,
        project_id: int,
        activity_type: str,
        complexity: str,
        inputs: dict,
    ) -> AIEstimate:
        # 1. Fetch template base
        template = BASELINE_TEMPLATES.get(activity_type, BASELINE_TEMPLATES["Other"])
        base_val = template["baseline"]
        mult = template["complexity_mult"].get(complexity, 1.0)
        baseline_hours = base_val * mult

        # 2. Historical similarity lookup
        past_actuals = await self.db.execute(
            select(func.avg(DailyWorkPlan.achieved_effort)).where(
                and_(
                    DailyWorkPlan.project_id == project_id,
                    DailyWorkPlan.task_type == activity_type,
                    DailyWorkPlan.status == "Done",
                    DailyWorkPlan.achieved_effort > 0
                )
            )
        )
        avg_past_actual = past_actuals.scalar()
        historical_hours_adj = 0.0
        if avg_past_actual is not None:
            # Shift towards historical average by 30%
            historical_hours_adj = (float(avg_past_actual) - baseline_hours) * 0.3

        # 3. LLM reasoning layer
        from app.config import get_settings
        settings = get_settings()
        llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
        system_prompt = (
            "You are nxtQA Estimate Intelligence, an AI module designed to estimate Software Quality QA task efforts.\n"
            "Analyze the inputs and provide a JSON response mapping strictly to the schema properties:\n"
            "- baseline_hours\n"
            "- optimistic_hours\n"
            "- most_likely_hours\n"
            "- pessimistic_hours\n"
            "- confidence_score (between 0.0 and 1.0)\n"
            "- assumptions\n"
            "- risk_factors\n"
            "- suggested_breakdown (dict of sub-task names to float hour values)"
        )
        
        user_prompt = (
            f"Estimate the effort for the following QA activity:\n"
            f"- Project ID: {project_id}\n"
            f"- Activity Type: {activity_type}\n"
            f"- Complexity: {complexity}\n"
            f"- Base Calculated Hours: {baseline_hours:.2f} hrs\n"
            f"- Historical Actual Shift: {historical_hours_adj:.2f} hrs\n"
            f"- Details: {inputs}\n\n"
            f"Ensure output is clean JSON format without prefix code blocks."
        )

        try:
            llm_text = await llm.generate(system=system_prompt, user=user_prompt)
            parsed = parse_and_validate_llm_output(llm_text, AIEstimateLLMResponse)
        except Exception as exc:
            logger.warning("LLM estimation failed or returned invalid schema, falling back: %s", exc)
            # Safe Fallback values
            parsed = AIEstimateLLMResponse(
                baseline_hours=baseline_hours,
                optimistic_hours=max(1.0, baseline_hours * 0.8),
                most_likely_hours=baseline_hours,
                pessimistic_hours=baseline_hours * 1.4,
                confidence_score=0.7,
                assumptions="Calculated using default template values due to LLM fallback.",
                risk_factors="None identified in fallback mode.",
                suggested_breakdown={"setup": baseline_hours * 0.25, "execution": baseline_hours * 0.5, "reporting": baseline_hours * 0.25}
            )

        # 4. PERT Calculation: (Optimistic + 4 * Likely + Pessimistic) / 6
        pert_val = (parsed.optimistic_hours + (4.0 * parsed.most_likely_hours) + parsed.pessimistic_hours) / 6.0
        
        # Risk / Dependency adjustment
        risk_adjustment = (parsed.pessimistic_hours - parsed.most_likely_hours) * 0.1
        
        # Save to database
        ai_estimate = AIEstimate(
            project_id=project_id,
            activity_type=activity_type,
            complexity=complexity,
            inputs=inputs,
            baseline_hours=parsed.baseline_hours,
            historical_hours_adj=historical_hours_adj,
            complexity_hours_adj=parsed.most_likely_hours - parsed.baseline_hours,
            risk_hours_adj=risk_adjustment,
            team_env_hours_adj=0.0,
            optimistic_hours=parsed.optimistic_hours,
            most_likely_hours=parsed.most_likely_hours,
            pessimistic_hours=parsed.pessimistic_hours,
            recommended_hours=round(pert_val + risk_adjustment, 1),
            pert_hours=round(pert_val, 1),
            confidence_score=parsed.confidence_score,
            assumptions=parsed.assumptions,
            risk_factors=parsed.risk_factors,
            historical_context={"avg_past_actual": avg_past_actual},
            suggested_breakdown=parsed.suggested_breakdown,
            status="suggested",
        )
        self.db.add(ai_estimate)
        await self.db.flush()
        return ai_estimate

    async def get_calibration_metrics(self, project_id: int) -> dict[str, Any]:
        """
        Compare AI recommended estimates against actual achieved hours for calibration.
        """
        result = await self.db.execute(
            select(
                DailyWorkPlan.task_type,
                func.avg(DailyWorkPlan.estimated_effort),
                func.avg(DailyWorkPlan.achieved_effort)
            ).where(
                and_(
                    DailyWorkPlan.project_id == project_id,
                    DailyWorkPlan.status == "Done"
                )
            ).group_by(DailyWorkPlan.task_type)
        )
        
        metrics = []
        for row in result.fetchall():
            task_type, est, act = row[0], float(row[1] or 0.0), float(row[2] or 0.0)
            diff = act - est
            metrics.append({
                "activity_type": task_type,
                "average_estimated_hours": est,
                "average_actual_hours": act,
                "variance": diff,
                "accuracy_percentage": max(0.0, 100.0 - (abs(diff) / est * 100.0)) if est > 0 else 100.0
            })
            
        return {"project_id": project_id, "calibration_metrics": metrics}
