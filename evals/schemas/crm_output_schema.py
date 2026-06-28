from pydantic import BaseModel, Field
from typing import Literal


class CRMSummary(BaseModel):
    """Validated output schema for the CRM summary AI feature."""

    summary: str = Field(min_length=10, max_length=300)
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    next_action: str = Field(min_length=5)
    urgency: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)