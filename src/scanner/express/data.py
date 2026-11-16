"""Mongoose-shaped loads for one Express route."""

from __future__ import annotations

from scanner.express.routes import ExpressAnalysis
from scanner.facts import DataAccessFact, RouteFact
from scanner.model_access import read_model_accesses
from scanner.project import Project


def read_data_accesses(project: Project, route: RouteFact) -> list[DataAccessFact]:
    analysis: ExpressAnalysis = route.analysis
    return read_model_accesses(
        route,
        classes=analysis.classes,
        language="javascript",
        limit=project.limits.max_snippet_chars,
    )
