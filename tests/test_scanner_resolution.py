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
