"""Confine the static exporter and its parser children after the anonymous checkout."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


class SandboxError(Exception):
    """An isolation or tooling error suitable for the project owner."""


def sandbox_command(checkout: Path, work: Path, command: list[str]) -> tuple[list[str], dict[str, str]]:
    from scanner.joern_runner import find_home

    checkout = checkout.resolve()
    work = work.resolve()
    temp, home = work / "tmp", work / "home"
    source = Path(__file__).resolve().parents[1]
    env = {key: os.environ[key] for key in ("JAVA_HOME", "JOERN_HOME") if key in os.environ}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"})
    # JVM properties default to the OS user's home/temp independently of HOME.
    env.update({
        "HOME": str(home), "TMPDIR": str(temp), "PYTHONPATH": str(source),
        "PYTHONDONTWRITEBYTECODE": "1", "BUN_RUNTIME_TRANSPILER_CACHE_PATH": "0",
        "JAVA_TOOL_OPTIONS": f'"-Duser.home={home}" "-Djava.io.tmpdir={temp}" -XX:-UsePerfData',
    })
    readable = [
        checkout, source / "scanner", Path(__file__).resolve(), Path(sys.executable).resolve(),
        Path(sysconfig.get_path("stdlib")).resolve(),
    ]
    bins = []
    for name in ("java", "git", "greadlink"):
        location = shutil.which(name)
        if location:
            bins.append(str(Path(location).parent))
            readable.extend([Path(location), Path(location).resolve()])
    joern = find_home()
    if joern:
        readable.append(joern.resolve())
        env["JOERN_HOME"] = str(joern.resolve())
    if not joern and env.get("JOERN_HOME"):
        readable.append(Path(env["JOERN_HOME"]).resolve())
    if env.get("JAVA_HOME"):
        java_home = Path(env["JAVA_HOME"]).resolve()
        readable.append(java_home)
        env["JAVA_HOME"] = str(java_home)
        bins.insert(0, str(java_home / "bin"))
    env["PATH"] = os.pathsep.join(dict.fromkeys([*bins, "/usr/bin", "/bin"]))

    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
        # Homebrew Cellar is executable distribution content. Its etc/var and
        # the user's home, workspace database and sibling checkouts stay outside.
        readable.extend(map(Path, [
            "/usr/bin", "/bin", "/usr/sbin", "/Library/Developer/CommandLineTools/usr",
            "/opt/homebrew/Cellar", "/usr/local/Cellar", "/Library/Java/JavaVirtualMachines",
        ]))
        rules = [
            "(version 1)", "(deny default)", '(import "system.sb")', "(deny network*)",
            "(allow process-fork)", "(allow signal (target self) (target children))",
            '(allow file-read-metadata (subpath "/opt/homebrew/opt") (subpath "/usr/local/opt"))',
            '(allow file-read* (subpath "/dev/fd"))',
            "(allow process-exec* file-map-executable (subpath \"/System\"))",
        ]
        rules.append(f"(allow file-read* (literal {json.dumps(str(source), ensure_ascii=False)}))")
        for path in [*readable, home, temp]:
            rules.append(f"(allow file-read-metadata (path-ancestors {json.dumps(str(path), ensure_ascii=False)}))")
        for path in readable:
            target = json.dumps(str(path), ensure_ascii=False)
            rules.append(f"(allow file-read* file-map-executable process-exec* (subpath {target}))")
        for path in [home, temp]:
            target = json.dumps(str(path), ensure_ascii=False)
            rules.append(f"(allow file-read* file-write* file-map-executable process-exec* (subpath {target}))")
        # Submitted source can only be read, including when a parser starts children.
        rules.append(f"(deny process-exec* file-map-executable (subpath {json.dumps(str(checkout), ensure_ascii=False)}))")
        return ["/usr/bin/sandbox-exec", "-p", "\n".join(rules), *command], env

    if sys.platform.startswith("linux") and (bwrap := shutil.which("bwrap")):
        readable.extend(map(Path, [
            "/usr/bin", "/bin", "/usr/lib", "/usr/lib64", "/lib", "/lib64", "/usr/share",
            "/etc/ld.so.cache", "/etc/alternatives",
        ]))
        libdir = Path(sysconfig.get_config_var("LIBDIR") or "/usr/lib")
        readable.extend(libdir.glob("libpython*.so*"))
        args = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp"]
        for path in sorted(set(readable), key=lambda item: (len(item.parts), str(item))):
            if path.exists():
                args.extend(["--ro-bind", str(path), str(path)])
        for path in [home, temp]:
            args.extend(["--bind", str(path), str(path)])
        return [*args, "--chdir", str(temp), "--", *command], env

    raise SandboxError("The static exporter needs sandbox-exec on macOS or bubblewrap (bwrap with user namespaces) on Linux.")


def export_confined(checkout: Path, work: Path) -> dict:
    python = str(Path(sys.executable).resolve())
    command, env = sandbox_command(checkout, work, [python, "-P", "-S", str(Path(__file__).resolve()), str(checkout)])
    result = subprocess.run(command, env=env, cwd=work / "tmp", capture_output=True)
    if result.returncode:
        raise SandboxError("The isolated static exporter failed. Check the local sandbox, Joern and Java installation.")
    return json.loads(result.stdout)


if __name__ == "__main__":
    from scanner.scan import export_repository

    json.dump(export_repository(Path(sys.argv[1]), cache=False), sys.stdout)
