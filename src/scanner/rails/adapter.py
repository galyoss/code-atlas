"""Rails implementation of FrameworkAdapter."""

from __future__ import annotations

from scanner.facts import AuthStepFact, DataAccessFact, RouteFact
from scanner.project import Project
from scanner.rails.auth import read_auth_steps
from scanner.rails.data import read_data_accesses
from scanner.rails.routes import discover_routes
from scanner.rails.source import load_ruby


class RailsAdapter:
    framework = "rails"
    frontend = "ruby"

    def discover_routes(self, project: Project) -> list[RouteFact]:
        return discover_routes(project, load_ruby(project.repo))

    def read_auth_steps(self, project: Project, route: RouteFact) -> list[AuthStepFact]:
        return read_auth_steps(project, route)

    def read_data_accesses(self, project: Project, route: RouteFact) -> list[DataAccessFact]:
        return read_data_accesses(project, route)
