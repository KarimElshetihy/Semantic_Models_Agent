"""Errors for new model creation (step 8)."""

from __future__ import annotations


class NewModelError(RuntimeError):
    """Base class for new model creation failures."""


class NewModelRefusedError(NewModelError):
    """The built model fails the static checks, or its output folder already exists. Nothing is written."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = tuple(reasons)
        super().__init__("; ".join(self.reasons))
