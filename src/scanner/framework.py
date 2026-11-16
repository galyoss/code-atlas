"""The framework seam.

A web framework implements `FrameworkAdapter`. The CLI calls
`read_project`, which only uses the three methods below. The schema writer
and the three-field check never import an adapter.
"""

from __future__ import annotations

from typing import Protocol

from scanner.facts import AuthStepFact, DataAccessFact, RouteFact
from scanner.project import Project


class FrameworkAdapter(Protocol):
    """Reads one framework into route facts.

    v1 has a single implementation, `FastAPIAdapter`. A later framework
    implements these three methods and is passed to `read_project`.
    """

    framework: str

    def discover_routes(self, project: Project) -> list[RouteFact]:
        """External method and path, handler, entry params, and call graph."""

    def read_auth_steps(self, project: Project, route: RouteFact) -> list[AuthStepFact]:
        """Auth hooks for `route`, in execution order."""

    def read_data_accesses(self, project: Project, route: RouteFact) -> list[DataAccessFact]:
        """Loads and writes. `in_predicate` is already decided."""


def read_project(adapter: FrameworkAdapter, project: Project) -> list[RouteFact]:
    """Run the three adapter methods and attach their facts to each route."""
    routes = adapter.discover_routes(project)
    for route in routes:
        route.auth_steps = adapter.read_auth_steps(project, route)
        route.data_accesses = adapter.read_data_accesses(project, route)
    return routes
