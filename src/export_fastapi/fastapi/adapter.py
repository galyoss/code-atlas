"""FastAPI implementation of FrameworkAdapter.

Route decorators, Depends, and SQLAlchemy where/filter text are read here.
The schema writer does not import this module.
"""

from __future__ import annotations

from export_fastapi.facts import AuthStepFact, DataAccessFact, RouteFact
from export_fastapi.fastapi.auth import read_auth_steps
from export_fastapi.fastapi.routes import discover_routes
from export_fastapi.fastapi.sql import read_data_accesses
from export_fastapi.project import Project


class FastAPIAdapter:
    framework = "fastapi"

    def __init__(self) -> None:
        self.notes: list[str] = []

    def discover_routes(self, project: Project) -> list[RouteFact]:
        return discover_routes(project, self.notes)

    def read_auth_steps(self, project: Project, route: RouteFact) -> list[AuthStepFact]:
        return read_auth_steps(project, route)

    def read_data_accesses(self, project: Project, route: RouteFact) -> list[DataAccessFact]:
        return read_data_accesses(project, route)
