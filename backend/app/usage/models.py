from pydantic import BaseModel, Field


class UsageSummary(BaseModel):
    request_count: int = Field(ge=0)
    input_units: float = Field(ge=0)
    output_units: float = Field(ge=0)
    failures: int = Field(ge=0)
    degraded_responses: int = Field(ge=0)
