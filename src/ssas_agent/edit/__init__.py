"""Typed edits to Tabular model objects. Each edit returns a new document; nothing is written here."""

from ssas_agent.edit.measure_edit import MeasureEditError, add_measure, replace_measure_expression

__all__ = ["MeasureEditError", "add_measure", "replace_measure_expression"]
