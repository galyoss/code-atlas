"""AST index for facts pysrc2cpg does not keep.

Joern's Python frontend drops parameter defaults, so ``Depends(...)`` on a
handler parameter is read here. Import aliases and ORM models are read here
too. Predicate yes/no decisions do not use this module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "tests",
    "test",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    ".eggs",
    "workspace",
    ".cache",
}

HTTP_METHODS = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
    "api_route",
    "websocket",
)


@dataclass
class ParamInfo:
    name: str
    annotation: str
    default_src: str
    depends: list[str]
    line: int


@dataclass
class FuncInfo:
    name: str
    qualname: str
    file: str
    line: int
    end_line: int
    signature: str
    params: list[ParamInfo]
    is_method: bool
    module: str
    # Local name -> the constructor it was assigned from (`svc = Service(session)`).
    local_types: dict[str, str] = field(default_factory=dict)


@dataclass
class ClassInfo:
    name: str
    qualname: str
    file: str
    line: int
    end_line: int
    signature: str
    module: str
    bases: list[str]
    tablename: str | None
    columns: list[str]
    is_orm: bool


@dataclass
class DepList:
    module: str
    name: str
    targets: list[str]


@dataclass
class ModuleInfo:
    qual: str
    file: str
    text: str
    lines: list[str]
    imports: dict[str, tuple[str, str]]
    functions: list[FuncInfo]
    classes: list[ClassInfo]
    dep_lists: dict[str, list[str]]
    # Module-level name -> the constructor it was assigned from (`Files = FilesTable()`).
    instances: dict[str, str] = field(default_factory=dict)


def iter_python_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo.rglob("*.py"):
        rel_parts = path.relative_to(repo).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts):
            continue
        files.append(path)
    files.sort()
    return files


def _is_package(directory: Path) -> bool:
    """A regular package, or a namespace subpackage inside one.

    Open WebUI keeps `open_webui/__init__.py` but no `__init__.py` in `models/` or
    `routers/`. Stopping at `models/` would name both `models/files.py` and
    `routers/files.py` plain `files`, and one would replace the other in the index.
    """
    return (directory / "__init__.py").exists() or (directory.parent / "__init__.py").exists()


def _module_qual(repo: Path, path: Path) -> str:
    # Walk up while the directory is a package.
    parts = [path.stem]
    cursor = path.parent
    while cursor != repo and _is_package(cursor):
        parts.append(cursor.name)
        cursor = cursor.parent
    parts.reverse()
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else path.stem


def _segment(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not start:
        return ""
    chunk = lines[start - 1 : (end or start)]
    return " ".join(part.strip() for part in chunk)


def _signature(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    body = getattr(node, "body", None)
    if body:
        end = body[0].lineno
        if end <= start:
            end = getattr(node, "end_lineno", start)
    else:
        end = getattr(node, "end_lineno", start)
    chunk = " ".join(line.strip() for line in lines[start - 1 : end])
    chunk = chunk.strip()
    if len(chunk) > 300:
        chunk = chunk[:297] + "..."
    return chunk or f"def {getattr(node, 'name', 'fn')}"


def _depends(node: ast.AST | None) -> list[str]:
    found: list[str] = []
    if node is None:
        return found

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            func = call.func
            name = func.id if isinstance(func, ast.Name) else None
            if name == "Depends" and call.args:
                arg = call.args[0]
                if isinstance(arg, ast.Name):
                    found.append(arg.id)
                elif isinstance(arg, ast.Attribute):
                    found.append(arg.attr)
            self.generic_visit(call)

    Visitor().visit(node)
    return found


def _annotation(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        return node.value.id
    return ""


def _dotted(node: ast.AST | None) -> str:
    """`Service` or `pkg.Service` for a name or attribute chain; empty for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""


def _annotation_class(node: ast.AST | None) -> str:
    """The one class an annotation names: `Service`, `Optional[Service]`, `Service | None`,
    `Annotated[Service, ...]` or `"Service"`. Containers and unions of two classes name none."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return _annotation_class(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return ""
    if isinstance(node, ast.Subscript):
        wrapper = _dotted(node.value).rsplit(".", 1)[-1]
        if wrapper not in {"Optional", "Annotated"}:
            return ""
        inner = node.slice.elts[0] if isinstance(node.slice, ast.Tuple) and node.slice.elts else node.slice
        return _annotation_class(inner)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        sides = [side for side in (node.left, node.right) if not (isinstance(side, ast.Constant) and side.value is None)]
        return _annotation_class(sides[0]) if len(sides) == 1 else ""
    return _dotted(node)


def _sqlmodel_table(node: ast.ClassDef) -> bool:
    """SQLModel marks mapped classes with `table=True` in the class keywords."""
    return any(
        keyword.arg == "table" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for keyword in node.keywords
    )


def _is_orm(bases: list[str], tablename: str | None, columns: list[str]) -> bool:
    if tablename:
        return True
    if any(base in {"Base", "DeclarativeBase"} or base.endswith("Base") for base in bases):
        return bool(columns) or True
    return False


def _class_signature(name: str, bases: list[str], columns: list[tuple[str, str]]) -> str:
    base = bases[0] if bases else "object"
    bits = []
    for col, ann in columns[:8]:
        bits.append(f"{col}: {ann}" if ann else col)
    body = "; ".join(bits)
    text = f"class {name}({base})"
    if body:
        text = f"{text}: {body}"
    if len(text) > 300:
        text = text[:297] + "..."
    return text


class _ModuleParser(ast.NodeVisitor):
    def __init__(self, module: str, file: str, lines: list[str]) -> None:
        self.module = module
        self.file = file
        self.lines = lines
        self.imports: dict[str, tuple[str, str]] = {}
        self.functions: list[FuncInfo] = []
        self.classes: list[ClassInfo] = []
        self.dep_lists: dict[str, list[str]] = {}
        self.instances: dict[str, str] = {}
        self._class_stack: list[str] = []
        self._func_stack: list[str] = []
        self._func_infos: list[FuncInfo] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.imports[local] = (alias.name, "")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = "." * (node.level or 0) + (node.module or "")
        if node.level:
            parts = self.module.split(".")
            up = node.level
            if parts and parts[-1] != Path(self.file).stem:
                # module is the package path of this file's module, so drop the
                # module name itself before applying relative levels.
                pass
            pkg = self.module.split(".")[:-1]
            if up > len(pkg):
                pkg = []
            else:
                pkg = pkg[: len(pkg) - (up - 1) if up else len(pkg)]
                if up:
                    pkg = self.module.split(".")[:-1]
                    pkg = pkg[: len(pkg) - (up - 1)] if up > 1 else pkg
                    # level 1: stay in the package (parent of this module)
                    pkg = self.module.split(".")[:-up]
            prefix = ".".join(p for p in [ ".".join(pkg), node.module or ""] if p).strip(".")
            base = prefix
        for alias in node.names:
            local = alias.asname or alias.name
            self.imports[local] = (base, alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if len(targets) == 1 and isinstance(node.value, (ast.List, ast.Tuple)):
            deps = _depends(node.value)
            if deps:
                self.dep_lists[targets[0]] = deps
        if len(targets) == 1:
            value = node.value.value if isinstance(node.value, ast.Await) else node.value
            if isinstance(value, ast.Call):
                self._record_type(targets[0], _dotted(value.func))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            value = node.value.value if isinstance(node.value, ast.Await) else node.value
            if isinstance(value, ast.Call):
                self._record_type(node.target.id, _dotted(value.func))
            else:
                self._record_type(node.target.id, _annotation_class(node.annotation))
        self.generic_visit(node)

    def _record_type(self, name: str, constructor: str) -> None:
        """The first assignment wins; a later rebinding to something else is not tracked."""
        if not constructor:
            return
        if self._func_infos:
            self._func_infos[-1].local_types.setdefault(name, constructor)
        elif not self._class_stack:
            self.instances.setdefault(name, constructor)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_func(node, is_async=True)

    def _add_func(self, node: ast.AST, is_async: bool) -> None:
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if self._class_stack:
            qual = ".".join([self.module, self._class_stack[-1], node.name])
            is_method = True
        elif self._func_stack:
            qual = ".".join([self.module, *self._func_stack, node.name])
            is_method = False
        else:
            qual = f"{self.module}.{node.name}"
            is_method = False
        params: list[ParamInfo] = []
        args = node.args
        defaults = list(args.defaults)
        positional = list(args.args)
        # defaults align to the tail of positional args
        missing = len(positional) - len(defaults)
        padded: list[ast.AST | None] = [None] * missing + list(defaults)
        for arg, default in zip(positional, padded, strict=False):
            if arg.arg in {"self", "cls"}:
                continue
            default_src = _segment(self.lines, default) if default is not None else ""
            params.append(
                ParamInfo(
                    name=arg.arg,
                    annotation=_annotation(arg.annotation),
                    default_src=default_src,
                    depends=_depends(default),
                    line=arg.lineno,
                )
            )
        info = FuncInfo(
            name=node.name,
            qualname=qual,
            file=self.file,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=_signature(self.lines, node),
            params=params,
            is_method=is_method,
            module=self.module,
        )
        for arg in [*args.args, *args.kwonlyargs]:
            annotated = _annotation_class(arg.annotation)
            if annotated and arg.arg not in {"self", "cls"}:
                info.local_types[arg.arg] = annotated
        self.functions.append(info)
        self._func_stack.append(node.name)
        self._func_infos.append(info)
        self.generic_visit(node)
        self._func_infos.pop()
        self._func_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)
        columns: list[tuple[str, str]] = []
        tablename = None
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                ann = _annotation(stmt.annotation)
                columns.append((stmt.target.id, ann))
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                            tablename = stmt.value.value
                    elif isinstance(target, ast.Name) and target.id != "__tablename__":
                        columns.append((target.id, ""))
        col_names = [name for name, _ann in columns if name != "__tablename__"]
        info = ClassInfo(
            name=node.name,
            qualname=f"{self.module}.{node.name}",
            file=self.file,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=_class_signature(node.name, bases, columns),
            module=self.module,
            bases=bases,
            tablename=tablename,
            columns=col_names,
            is_orm=_is_orm(bases, tablename, col_names) or _sqlmodel_table(node),
        )
        self.classes.append(info)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()


@dataclass
class SourceIndex:
    repo: Path
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    functions_by_qual: dict[str, FuncInfo] = field(default_factory=dict)
    classes_by_qual: dict[str, ClassInfo] = field(default_factory=dict)
    file_text: dict[str, str] = field(default_factory=dict)

    def function_at(self, file: str, name: str, line: int) -> FuncInfo | None:
        best: FuncInfo | None = None
        best_dist = 10**9
        for mod in self.modules.values():
            if mod.file != file:
                continue
            for func in mod.functions:
                if func.name != name:
                    continue
                dist = abs(func.line - line)
                if dist < best_dist:
                    best = func
                    best_dist = dist
        if best is not None and best_dist <= 5:
            return best
        named = [
            func
            for mod in self.modules.values()
            if mod.file == file
            for func in mod.functions
            if func.name == name
        ]
        if len(named) == 1:
            return named[0]
        return None

    def classes_in_file(self, file: str) -> list[ClassInfo]:
        found: list[ClassInfo] = []
        for mod in self.modules.values():
            if mod.file == file:
                found.extend(mod.classes)
        return found

    def module_for_file(self, file: str) -> ModuleInfo | None:
        for mod in self.modules.values():
            if mod.file == file:
                return mod
        return None

    def resolve_name(
        self, module_qual: str, name: str, _seen: frozenset[tuple[str, str]] = frozenset()
    ) -> tuple[str, str] | None:
        """Resolve ``name`` in ``module_qual`` to ``(kind, qualname)``.

        kind is ``function``, ``class``, or ``external``. A re-export cycle between
        modules leaves the name unresolved.
        """
        if (module_qual, name) in _seen:
            return None
        mod = self.modules.get(module_qual)
        if mod is None:
            return None
        dotted = name.split(".")
        head = dotted[0]
        for func in mod.functions:
            if func.name == head and not func.qualname.count(".") > module_qual.count(".") + 1:
                # Prefer the module-level function over a nested one when names collide.
                if func.qualname == f"{module_qual}.{head}":
                    return ("function", func.qualname)
        for func in mod.functions:
            if func.name == head and func.qualname == f"{module_qual}.{head}":
                return ("function", func.qualname)
        for cls in mod.classes:
            if cls.name == head:
                return ("class", cls.qualname)
        imported = mod.imports.get(head)
        if imported is None:
            return None
        src_mod, src_name = imported
        target_name = src_name or head
        if src_mod in self.modules:
            return self.resolve_name(src_mod, target_name, _seen | {(module_qual, name)})
        return ("external", f"{src_mod}.{target_name}" if src_mod else target_name)

    def class_named(self, module_qual: str, name: str) -> str | None:
        """The in-repo class `name` refers to in `module_qual`, or None."""
        if "." not in name:
            resolved = self.resolve_name(module_qual, name)
        else:
            # `models.FilesTable`: resolve the module alias, then the class in that module.
            head, attr = name.rsplit(".", 1)
            mod = self.modules.get(module_qual)
            imported = mod.imports.get(head) if mod else None
            target = ".".join(part for part in imported if part) if imported else head
            resolved = self.resolve_name(target, attr) if target in self.modules else None
        if resolved is not None and resolved[0] == "class":
            return resolved[1]
        return None

    def instance_class(
        self,
        module_qual: str,
        name: str,
        func: FuncInfo | None = None,
        _seen: frozenset[tuple[str, str]] = frozenset(),
    ) -> str | None:
        """The in-repo class `name` is an instance of: a local or parameter of `func`,
        or a module-level instance, possibly imported from another module."""
        if func is not None and name in func.local_types:
            return self.class_named(module_qual, func.local_types[name])
        if (module_qual, name) in _seen:
            return None
        mod = self.modules.get(module_qual)
        if mod is None:
            return None
        if name in mod.instances:
            return self.class_named(module_qual, mod.instances[name])
        imported = mod.imports.get(name)
        if imported is not None and imported[0] in self.modules and imported[1]:
            return self.instance_class(imported[0], imported[1], None, _seen | {(module_qual, name)})
        return None

    def method_of(self, class_qual: str, name: str, _depth: int = 0) -> FuncInfo | None:
        """`name` defined on the class or inherited from an in-repo base."""
        func = self.functions_by_qual.get(f"{class_qual}.{name}")
        if func is not None:
            return func
        cls = self.classes_by_qual.get(class_qual)
        if cls is None or _depth >= 4:
            return None
        for base in cls.bases:
            base_qual = self.class_named(cls.module, base)
            if base_qual is not None and base_qual != class_qual:
                found = self.method_of(base_qual, name, _depth + 1)
                if found is not None:
                    return found
        return None

    def dependency_targets(self, module_qual: str, expr_or_name: str) -> list[str]:
        """Resolve a dependencies= expression to function qualnames."""
        text = expr_or_name.strip()
        mod = self.modules.get(module_qual)
        if mod is None:
            return []
        direct = []
        for match in _DEPENDS_NAME.finditer(text):
            resolved = self.resolve_name(module_qual, match.group(1))
            if resolved and resolved[0] == "function":
                direct.append(resolved[1])
        if direct:
            return direct
        if re_full_name(text) and text in mod.dep_lists:
            out = []
            for item in mod.dep_lists[text]:
                resolved = self.resolve_name(module_qual, item)
                if resolved and resolved[0] == "function":
                    out.append(resolved[1])
            return out
        if re_full_name(text):
            resolved = self.resolve_name(module_qual, text)
            if resolved and resolved[0] == "function":
                return [resolved[1]]
            if resolved and resolved[0] == "external":
                return []
            imported = mod.imports.get(text)
            if imported and imported[0] in self.modules:
                src_mod, src_name = imported
                key = src_name or text
                return self.dependency_targets(src_mod, key)
        return []

    def alias_map(self, module_qual: str) -> dict[str, str]:
        """Map a local class alias to the class name (not the module)."""
        mod = self.modules.get(module_qual)
        if mod is None:
            return {}
        out: dict[str, str] = {}
        for local, (src_mod, src_name) in mod.imports.items():
            if src_mod in self.modules and src_name:
                for cls in self.modules[src_mod].classes:
                    if cls.name == src_name:
                        out[local] = cls.name
        for cls in mod.classes:
            out.setdefault(cls.name, cls.name)
        return out

    def class_names(self, module_qual: str) -> set[str]:
        names = set(self.alias_map(module_qual))
        mod = self.modules.get(module_qual)
        if mod:
            names.update(cls.name for cls in mod.classes)
        return names

    def find_class(self, qual_or_name: str) -> ClassInfo | None:
        if qual_or_name in self.classes_by_qual:
            return self.classes_by_qual[qual_or_name]
        matches = [c for q, c in self.classes_by_qual.items() if q.endswith("." + qual_or_name) or c.name == qual_or_name]
        if len(matches) == 1:
            return matches[0]
        return None

    def snippet(self, file: str, start: int, end: int, limit: int = 480) -> tuple[str, bool]:
        text = self.file_text.get(file, "")
        lines = text.splitlines()
        if start < 1:
            start = 1
        if end < start:
            end = start
        raw = "\n".join(lines[start - 1 : end]).strip("\n")
        if not raw:
            return "", False
        if len(raw) <= limit:
            return raw, False
        return raw[:limit], True


_DEPENDS_NAME = __import__("re").compile(r"Depends\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)")


def re_full_name(text: str) -> bool:
    import re

    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) is not None


def load_index(repo: Path) -> SourceIndex:
    index = SourceIndex(repo=repo)
    for path in iter_python_files(repo):
        rel = path.relative_to(repo).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        lines = text.splitlines()
        qual = _module_qual(repo, path)
        parser = _ModuleParser(qual, rel, lines)
        parser.visit(tree)
        info = ModuleInfo(
            qual=qual,
            file=rel,
            text=text,
            lines=lines,
            imports=parser.imports,
            functions=parser.functions,
            classes=parser.classes,
            dep_lists=parser.dep_lists,
            instances=parser.instances,
        )
        index.modules[qual] = info
        index.file_text[rel] = text
        for func in parser.functions:
            index.functions_by_qual[func.qualname] = func
        for cls in parser.classes:
            index.classes_by_qual[cls.qualname] = cls
    return index
