"""ActiveRecord loads for one Rails route."""

from __future__ import annotations

from scanner.facts import DataAccessFact, RouteFact
from scanner.model_access import read_model_accesses
from scanner.project import Project
from scanner.rails.routes import RailsAnalysis


def read_data_accesses(project: Project, route: RouteFact) -> list[DataAccessFact]:
    analysis: RailsAnalysis = route.analysis
    return read_model_accesses(
        route,
        classes=analysis.classes,
        language="ruby",
        limit=project.limits.max_snippet_chars,
    )
