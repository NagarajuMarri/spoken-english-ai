from pydantic import BaseModel, Field


class MemorySignalInput(BaseModel):
    category: str = Field(pattern="^(grammar|vocabulary|pronunciation|fluency|confidence|topic)$")
    value: str = Field(min_length=1, max_length=200)
    trend_value: float | None = Field(default=None, ge=0, le=100)
