"""Candidate generation (step 7): DAX measures and Oracle SQL drafted by the model, checked before anything is staged."""

from ssas_agent.generation.context import model_context
from ssas_agent.generation.errors import CandidateRefusedError, GenerationError
from ssas_agent.generation.measure_proposal import MeasureProposal, draft_measure, propose_measure
from ssas_agent.generation.sql_candidate import (
    CHECKS_FILE_NAME,
    SQL_FILE_NAME,
    SqlCandidate,
    draft_sql,
    record_sql_candidate,
)
from ssas_agent.generation.sql_checks import SqlFinding, SqlReport, SqlRule, check_sql

__all__ = [
    "CHECKS_FILE_NAME",
    "SQL_FILE_NAME",
    "CandidateRefusedError",
    "GenerationError",
    "MeasureProposal",
    "SqlCandidate",
    "SqlFinding",
    "SqlReport",
    "SqlRule",
    "check_sql",
    "draft_measure",
    "draft_sql",
    "model_context",
    "propose_measure",
    "record_sql_candidate",
]
