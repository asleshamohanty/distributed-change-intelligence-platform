from datetime import datetime

from pydantic import BaseModel, Field


class DeployEventIn(BaseModel):
    """Shape mirrors design-doc §5.1's commit+deploy event example."""

    service: str = Field(..., examples=["order-service"])
    commit_sha: str = Field(..., examples=["a82f91"])
    author: str = Field(..., examples=["developer"])
    files_changed: list[str] = Field(default_factory=list)
    timestamp: datetime | None = None


class DeployEventOut(BaseModel):
    change_id: str
    deployment_id: str
    service: str
    commit_sha: str
    author: str
    files_changed: list[str]
    timestamp: datetime
