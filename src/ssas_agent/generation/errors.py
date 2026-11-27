"""Errors for candidate generation. A refused candidate is never staged or written."""


class GenerationError(RuntimeError):
    """A candidate could not be generated from the request."""


class CandidateRefusedError(GenerationError):
    """The candidate failed the checks, so nothing was staged. `reasons` lists why, one per line."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("candidate refused: " + "; ".join(reasons))
