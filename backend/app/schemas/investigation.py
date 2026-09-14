"""Structured LLM output schema (design-doc §5.10 / §18 appendix), verbatim.

This is what keeps the model honest: there is no "root_cause" field
anywhere in this schema, so the LLM structurally cannot claim to have found
one — every hypothesis must carry its own supporting evidence *and* its own
limitations.
"""
from pydantic import BaseModel


class Evidence(BaseModel):
    source: str
    detail: str


class Hypothesis(BaseModel):
    statement: str
    supporting_evidence: list[Evidence]
    limitations: list[str]


class InvestigationResult(BaseModel):
    summary: str
    hypotheses: list[Hypothesis]
