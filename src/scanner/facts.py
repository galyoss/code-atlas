"""Neutral facts a framework adapter hands to the schema writer.

Nothing in this module names a web framework. Adapters fill these records.
The writer turns them into a schema document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SymbolFact:
    key: str
    language: str
    kind: str
    name: str
    qualname: str
    signature: str
    file: str
    start: int
    end: int


@dataclass
class ReadFact:
    file: str
    start: int
    end: int
    symbol_key: str
    expression: str


@dataclass
class EntryParamFact:
    name: str
    location: str
    path_in_request: str
    presence: str
    value_shape: str
    names_object: str
    type_symbol_key: str | None
    reads: list[ReadFact]


@dataclass
class BindingFact:
    name: str
    kind: str
    presence: str
    expression: str
    file: str
    start: int
    end: int
    produced_by_qualname: str | None
    type_symbol_key: str | None


@dataclass
class CallFact:
    key: str
    callee_name: str
    qualname: str
    resolution: str
    symbol_key: str | None
    candidates: list[str] | None
    touches: str
    expanded: str
    file: str
    line: int
    end_line: int
    excerpt: str
    code: str = ""
    children: list[CallFact] = field(default_factory=list)
    omission: tuple[str, str] | None = None


@dataclass
class AuthStepFact:
    key: str
    symbol_key: str
    qualname: str
    file: str
    start: int
    end: int
    kind: str
    mechanism: str
    scope: str
    applicability: str
    on_failure: str
    binds_object_to_caller: str
    expanded: str
    calls: list[CallFact]
    call_key: str | None
    snippet: str
    snippet_truncated: bool


@dataclass
class ParamFlowFact:
    entry_param_name: str
    field: str
    confidence: str


@dataclass
class WrittenFieldFact:
    field: str
    source: str
    entry_param_name: str | None = None
    binding_name: str | None = None
    source_access_key: str | None = None


@dataclass
class DataAccessFact:
    key: str
    call_key: str
    operation: str
    persistence_api: str
    object_name: str
    object_symbol_key: str | None
    store: str | None
    param_flows: list[ParamFlowFact]
    in_predicate: str
    stamped_on_write: str
    owner_fields: list[str]
    identity_names: list[str]
    written_fields: list[WrittenFieldFact]
    snippet: str
    snippet_file: str
    snippet_start: int
    snippet_end: int
    snippet_truncated: bool


@dataclass
class RouteFact:
    """One route after the adapter has read it. `analysis` is adapter-private."""

    http_method: str
    path: str
    framework: str
    language: str
    registration_file: str
    registration_start: int
    registration_end: int
    registration_text: str
    registration_truncated: bool
    handler_symbol_key: str
    handler_qualname: str
    handler_file: str
    handler_start: int
    handler_end: int
    registration_mechanism: str = "decorator"
    entry_params: list[EntryParamFact] = field(default_factory=list)
    bindings: list[BindingFact] = field(default_factory=list)
    auth_steps: list[AuthStepFact] = field(default_factory=list)
    call_graph: list[CallFact] = field(default_factory=list)
    data_accesses: list[DataAccessFact] = field(default_factory=list)
    symbols: dict[str, SymbolFact] = field(default_factory=dict)
    analysis: Any = None


@dataclass
class RepoFact:
    name: str
    revision: str
    vcs: str
    remote: str | None = None


@dataclass
class Limits:
    max_call_depth: int = 4
    max_call_nodes: int = 400
    max_snippet_chars: int = 480
