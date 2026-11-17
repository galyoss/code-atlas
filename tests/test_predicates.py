"""Predicate and path decisions, without Joern."""

from scanner.fastapi.paths import is_schema_path, join_paths, normalize_path
from scanner.fastapi.predicates import instance_owner_compare, predicate_from_cpg


def test_owner_comparison_is_yes():
    decision, owners, idents = predicate_from_cpg(
        'select(ThreadORM).where(ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity)',
        {"ThreadORM": "Thread"},
    )
    assert decision == "yes"
    assert owners == ["Thread.user_id"]
    assert idents == ["user"]


def test_primary_key_only_is_no():
    decision, owners, idents = predicate_from_cpg(
        "select(ThreadORM).where(ThreadORM.thread_id == thread_id)",
        {"ThreadORM": "Thread"},
    )
    assert decision == "no"
    assert owners == []
    assert idents == []


def test_named_filter_is_unknown():
    decision, owners, _idents = predicate_from_cpg("stmt.where(auth_filter)")
    assert decision == "unknown"
    assert owners == []


def test_empty_predicate_is_unknown():
    assert predicate_from_cpg("")[0] == "unknown"
    assert predicate_from_cpg(None)[0] == "unknown"


def test_instance_compare_is_not_a_column_predicate():
    classes = {"Thread", "ThreadORM"}
    assert instance_owner_compare("existing_thread.user_id != user.identity", classes)
    assert not instance_owner_compare("ThreadORM.user_id == user.identity", classes)


def test_path_converter_and_prefix():
    assert normalize_path("/files/{file_path:path}") == "/files/{file_path}"
    assert join_paths("/api", "/v1/", "/items/{item_id}") == "/api/v1/items/{item_id}"
    assert is_schema_path("/api/v1/items/{item_id}")
    assert not is_schema_path("/api/v1/items/{item_id}/")


def test_reexport_cycle_leaves_name_unresolved(tmp_path):
    from scanner.source_index import load_index

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("from pkg.b import thing\n")
    (pkg / "b.py").write_text("from pkg.a import thing\n")
    index = load_index(tmp_path)
    module = next(name for name in index.modules if name.endswith("a"))
    assert index.resolve_name(module, "thing") is None
