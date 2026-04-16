from pydantic import BaseModel, ConfigDict, Field


class CandidatePlanStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    step: int = Field(ge=1)
    action: str
    target: str | None = None
    parameters: dict = Field(default_factory=dict)


class LLMInterpretationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_summary: str
    candidate_plan: list[CandidatePlanStep]
    evidence_requirements: list[str] = Field(default_factory=list)
    retryability_assessment: str
    escalation_recommendation: str
