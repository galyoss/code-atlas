"""Call resolution and data-access evidence details that decide route coverage."""

from types import SimpleNamespace

from scanner.fastapi.calls import _is_attribute, resolve_call
from scanner.fastapi.sql import _GET_RE, _snippet_with_guard
from scanner.facts import Limits
from scanner.overlay import CallRec


def _call(name: str, code: str) -> CallRec:
    return CallRec(name, "", code, "app.py", 3, "handler", "STATIC_DISPATCH", 1)


def test_chained_calls_are_methods_on_the_previous_result():
    assert _is_attribute(_call("where", "select(Thread).where(Thread.id == thread_id)"))
    assert _is_attribute(_call("values", "update(T).where(T.id == i).values(a=1)"))
    assert _is_attribute(_call("scalar", "await session.scalar(stmt)"))
    assert not _is_attribute(_call("select", "select(Thread).where(x)"))
    assert not _is_attribute(_call("handler", "handler(ctx = auth_ctx, value = value)"))


def test_unshadowed_builtins_are_external_and_unknown_names_stay_ambiguous():
    index = SimpleNamespace(resolve_name=lambda module, name: None)
    overlay = SimpleNamespace(methods_by_full={})
    assert resolve_call(_call("isinstance", "isinstance(x, str)"), "app", index, overlay, {}) == (
        "external",
        None,
        None,
        "builtins.isinstance",
    )
    assert resolve_call(_call("handler", "handler(x)"), "app", index, overlay, {})[0] == "ambiguous"


def test_session_get_matches_a_model_and_key():
    match = _GET_RE.search("await session.get(ApiKey, api_key_id)")
    assert match.group(1, 2) == ("ApiKey", "api_key_id")
    assert _GET_RE.search("payload.get('name')") is None


def test_load_snippet_includes_the_check_that_follows_it():
    source = "\n".join(
        [
            "async def create_run(thread_id, user, session):",
            '    """Create a run."""',
            "    thread = await session.scalar(select(Thread).where(Thread.id == thread_id))",
            "    if thread and thread.user_id != user.identity:",
            "        raise HTTPException(404)",
            "    return await prepare(thread_id)",
            "",
            "def other():",
            "    pass",
        ]
    )
    project = SimpleNamespace(
        limits=Limits(),
        overlay=SimpleNamespace(
            methods_by_file={"app.py": [SimpleNamespace(name="create_run", line=1, end_line=6)]}
        ),
        index=SimpleNamespace(
            snippet=lambda file, start, end, limit: (
                "\n".join(source.splitlines()[start - 1 : end]),
                False,
            )
        ),
    )
    node = SimpleNamespace(file="app.py", line=3)
    text, end, truncated = _snippet_with_guard(project, node, "select(Thread).where(Thread.id == thread_id)", "load")
    assert "thread.user_id != user.identity" in text
    assert end == 6 and not truncated
    assert "def other" not in text
    update = _snippet_with_guard(project, node, "update(Thread).where(Thread.id == thread_id)", "update")
    assert update == ("update(Thread).where(Thread.id == thread_id)", 3, False)


def test_later_query_refinements_join_the_access():
    from scanner.fastapi.sql import _refinements, _snippet_with_refinements

    source = "\n".join(
        [
            "async def builds(db, flow_id, user_id):",
            "    stmt = (",
            "        select(Build)",
            "        .where(Build.flow_id == flow_id)",
            "    )",
            "    stmt = stmt.join(Flow, Build.flow_id == Flow.id).where(",
            "        Flow.user_id == user_id",
            "    )",
            "    return await db.exec(stmt)",
        ]
    )
    project = SimpleNamespace(
        limits=Limits(),
        overlay=SimpleNamespace(methods_by_file={"app.py": [SimpleNamespace(name="builds", line=1, end_line=9)]}),
        index=SimpleNamespace(file_text={"app.py": source}),
    )
    refinements = _refinements(project, SimpleNamespace(file="app.py", line=3))
    assert [(start, end) for start, end, _ in refinements] == [(6, 8)]
    assert "Flow.user_id == user_id" in refinements[0][2]
    text, end, _ = _snippet_with_refinements(project, "select(Build).where(Build.flow_id == flow_id)", refinements)
    assert text.startswith("select(Build)") and "Flow.user_id == user_id" in text and end == 8
    assert _refinements(project, SimpleNamespace(file="app.py", line=9)) == []


def _package(tmp_path, files: dict[str, str]):
    from scanner.source_index import load_index

    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, text in files.items():
        (pkg / name).write_text(text)
    return load_index(tmp_path)


_SERVICE = """\
class Base:
    def delete(self, item_id):
        return self._session.delete(item_id)


class AgentService(Base):
    def __init__(self, session):
        self._session = session

    def get(self, agent_id):
        return self._session.get(Agent, agent_id)


class FilesTable:
    def get_file_by_id(self, file_id):
        return file_id


Files = FilesTable()
"""

_ROUTES = """\
from typing import Optional

from app.service import AgentService, Files


def by_local(session, agent_id):
    svc = AgentService(session)
    return svc.get(agent_id)


def by_param(svc: Optional[AgentService], agent_id):
    return svc.delete(agent_id)


def by_constructor(session, agent_id):
    return AgentService(session).get(agent_id)


def by_singleton(file_id):
    return Files.get_file_by_id(file_id)


def untyped(svc, agent_id):
    return svc.get(agent_id)
"""


def _resolve(index, func_name, name, code):
    overlay = SimpleNamespace(methods_by_full={})
    caller = index.functions_by_qual[f"app.routes.{func_name}"]
    return resolve_call(_call(name, code), "app.routes", index, overlay, {}, caller)[:2]


def test_methods_on_in_repo_instances_resolve(tmp_path):
    index = _package(tmp_path, {"service.py": _SERVICE, "routes.py": _ROUTES})
    assert _resolve(index, "by_local", "get", "svc.get(agent_id)") == ("resolved", "app.service.AgentService.get")
    assert _resolve(index, "by_param", "delete", "svc.delete(agent_id)") == ("resolved", "app.service.Base.delete")
    assert _resolve(index, "by_constructor", "get", "AgentService(session).get(agent_id)") == (
        "resolved",
        "app.service.AgentService.get",
    )
    assert _resolve(index, "by_singleton", "get_file_by_id", "Files.get_file_by_id(file_id)") == (
        "resolved",
        "app.service.FilesTable.get_file_by_id",
    )


def test_untyped_receivers_and_external_classes_stay_external(tmp_path):
    index = _package(tmp_path, {"service.py": _SERVICE, "routes.py": _ROUTES})
    assert _resolve(index, "untyped", "get", "svc.get(agent_id)")[0] == "external"
    assert _resolve(index, "by_local", "missing", "svc.missing(agent_id)")[0] == "external"


def test_namespace_subpackages_keep_their_package_path(tmp_path):
    from scanner.source_index import load_index

    root = tmp_path / "backend" / "app"
    for sub in ("models", "routers"):
        (root / sub).mkdir(parents=True)
        (root / sub / "files.py").write_text(f"NAME = '{sub}'\n")
    (root / "__init__.py").write_text("")
    index = load_index(tmp_path)
    assert {"app.models.files", "app.routers.files"} <= set(index.modules)
    assert "files" not in index.modules


def test_an_identity_parameter_names_its_dependency_as_producer(tmp_path):
    from scanner.fastapi.routes import _bindings

    index = _package(
        tmp_path,
        {
            "deps.py": "def require_workspace_member(workspace_id, user=None):\n    return user\n",
            "routes.py": (
                "from fastapi import Depends\n"
                "from app.deps import require_workspace_member\n\n"
                "def get_agent(workspace_id, agent_id, user = Depends(require_workspace_member)):\n"
                "    return agent_id\n"
            ),
        },
    )
    handler = index.functions_by_qual["app.routes.get_agent"]
    bindings = _bindings(handler, index, {})
    assert [(b.name, b.produced_by_qualname) for b in bindings] == [("user", "app.deps.require_workspace_member")]
