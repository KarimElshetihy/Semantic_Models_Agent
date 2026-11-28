"""Phase 1 exit gate demonstration: a new sample model, a safe edit to an existing model, and the refusals."""

from ssas_agent.demo.exit_gate import DemoRefusedError, run_exit_gate
from ssas_agent.demo.records import EditOutcome, ExitGateResult, NewModelOutcome, RefusalRecord

__all__ = [
    "DemoRefusedError",
    "EditOutcome",
    "ExitGateResult",
    "NewModelOutcome",
    "RefusalRecord",
    "run_exit_gate",
]
