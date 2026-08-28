"""
models.py
=========
Pydantic schemas that validate the LLM's structured output *before* any scoring
logic sees it. This turns "the model should return JSON" into a hard guarantee:
out-of-range numbers are clamped, missing fields get safe defaults, and malformed
responses raise a ValidationError the engine can catch and fall back on.
"""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field, field_validator


class TranscriptSignals(BaseModel):
    """Semantic signals extracted from a single support transcript."""

    churn_intent: float = Field(0.0, description="0=stay, 1=explicitly leaving")
    frustration: float = Field(0.0, description="emotional intensity 0-1")
    competitor_mention: bool = False
    feature_gap: bool = False
    billing_issue: bool = False
    passive_dissatisfaction: bool = False
    sentiment: float = Field(0.0, description="-1 negative .. +1 positive")
    confidence: float = Field(0.7, description="model's confidence in this read 0-1")
    key_phrases: List[str] = Field(default_factory=list,
                                   description="evidence quotes from the transcript")

    # ---- coerce/clamp instead of crashing on a slightly off value ----
    @field_validator("churn_intent", "frustration", "confidence", mode="before")
    @classmethod
    def _clamp_unit(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("sentiment", mode="before")
    @classmethod
    def _clamp_signed(cls, v):
        try:
            return max(-1.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("competitor_mention", "feature_gap", "billing_issue",
                     "passive_dissatisfaction", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        return bool(v)

    @field_validator("key_phrases", mode="before")
    @classmethod
    def _cap_phrases(cls, v):
        if not isinstance(v, list):
            return []
        return [str(x) for x in v][:3]
