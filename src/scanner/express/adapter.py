"""Express implementation of FrameworkAdapter."""

from __future__ import annotations

from scanner.express.auth import read_auth_steps
from scanner.express.data import read_data_accesses
from scanner.express.routes import discover_routes
from scanner.express.source import load_js
from scanner.facts import AuthStepFact, DataAccessFact, RouteFact
from scanner.project import Project


class ExpressAdapter:
    framework = "express"
    frontend = "javascript"

    def discover_routes(self, project: Project) -> list[RouteFact]:
        return discover_routes(project, load_js(project.repo))

    def read_auth_steps(self, project: Project, route: RouteFact) -> list[AuthStepFact]:
        return read_auth_steps(project, route)

    def read_data_accesses(self, project: Project, route: RouteFact) -> list[DataAccessFact]:
        return read_data_accesses(project, route)
