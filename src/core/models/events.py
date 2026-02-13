# src/core/models/events.py
"""Event framework for probabilistic coherence."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from .enums import EventType, SSPScenario, DataSource
from .geometry import DataLineage



class EventContext(BaseModel):
    """
    Event context ensuring probabilistic coherence.
    Acute events use return periods, chronic use time horizons.
    """
    event_type: EventType = Field(..., description="Event classification")
    return_period: Optional[int] = Field(
        None,
        ge=10,
        le=500,
        description="For acute events (years)"
    )
    time_horizon: Optional[int] = Field(
        None,
        ge=2024,
        le=2100,
        description="For chronic events (year)"
    )
    slr_scenario: SSPScenario = Field(
        default=SSPScenario.SSP245,
        description="SSP scenario"
    )
    percentile: Optional[int] = Field(
        None,
        ge=1,
        le=99,
        description="Percentile for chronic hazards"
    )
    # Gap 4.3: Data lineage (optional for context but good practice)
    lineage: Optional[DataLineage] = None

    @model_validator(mode='after')
    def validate_event_requirements(self):
        if self.event_type == EventType.ACUTE and self.return_period is None:
            raise ValueError("Acute events require return_period")
        if self.event_type == EventType.CHRONIC and self.time_horizon is None:
            raise ValueError("Chronic events require time_horizon")
        return self

    model_config = {"use_enum_values": True}
