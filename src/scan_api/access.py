"""Check GitHub access and clone one revision. Failures here happen before a scan starts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

_OWNER = r"[A-Za-z0-9_.-]+"
_HTTPS = re.compile(rf"^https://github\.com/(?P<owner>{_OWNER})/(?P<repo>{_OWNER}?)(?:\.git)?/?$")
_SSH = re.compile(rf"^git@github\.com:(?P<owner>{_OWNER})/(?P<repo>{_OWNER}?)(?:\.git)?$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,40}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_UNSAFE_REVISION = re.compile(r"[\s\x00-\x1f~^:?*\[\\]|@{|\.\.")


class AccessError(Exception):
    """The repository or revision cannot be scanned. The scan was not started."""


class ProbeFailure(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Revision:
    repository_url: str
    owner: str
    repo: str
    revision: str
    resolved_sha: str


@dataclass
class RemoteRefs:
    head_branch: str | None
    head_sha: str | None
    heads: dict[str, str]
    tags: dict[str, str]

    def match(self, revision: str) -> str | None:
        if revision in self.heads:
            return self.heads[revision]
        if revision in self.tags:
            return self.tags[revision]
        if _SHA.fullmatch(revision):
            needle = revision.lower()
            found = {
                sha
                for sha in (*self.heads.values(), *self.tags.values(), self.head_sha or "")
                if sha.startswith(needle)
            }
            found.discard("")
            if len(found) == 1:
                return next(iter(found))
        return None


def parse_github_url(value: object) -> tuple[str, str, str]:
    if not isinstance(value, str) or not value.strip():
        raise AccessError(
            "repositoryUrl is required and must be a GitHub repository URL such as "
            "https://github.com/owner/name."
        )
    text = value.strip()
    if "://" in text and "@" in text.split("://", 1)[1].split("/", 1)[0]:
        raise AccessError("repositoryUrl must not include credentials. The scan was not started.")
    if text.startswith("http://github.com/"):
        text = "https://" + text[len("http://") :]
    elif text.startswith("github.com/"):
        text = "https://" + text
    match = _HTTPS.fullmatch(text) or _SSH.fullmatch(text)
    if match is None:
        raise AccessError(
            "repositoryUrl must be a GitHub repository URL such as "
            "https://github.com/owner/name. Put the branch, tag, or commit in revision, "
            "not in the repository path. The scan was not started."
        )
    owner = match.group("owner")
    repo = match.group("repo")
    if owner in {".", ".."} or repo in {".", ".."} or owner.startswith("-") or repo.startswith("-"):
        raise AccessError("repositoryUrl is not a valid GitHub repository. The scan was not started.")
    return f"https://github.com/{owner}/{repo}", owner, repo


def resolve_revision(
    repository_url: str,
    revision: str | None,
    *,
    run=None,
    lookup_commit=None,
) -> Revision:
    url, owner, repo = parse_github_url(repository_url)
    if revision is not None:
        if not isinstance(revision, str) or not revision.strip():
            raise AccessError("revision must be a branch, tag, or commit SHA. The scan was not started.")
        revision = revision.strip()
        if len(revision) > 255 or revision.startswith("-") or _UNSAFE_REVISION.search(revision):
            raise AccessError(
                "revision must be a branch name, tag, or commit SHA. The scan was not started."
            )
    runner = run or _git_ls_remote
    try:
        output = runner(url)
    except ProbeFailure as exc:
        raise AccessError(_access_message(url, exc.detail)) from exc
    refs = _parse_refs(output)
    if not refs.head_sha or not refs.head_branch:
        raise AccessError(
            f"Cannot read HEAD for {url}. The repository may be empty. The scan was not started."
        )
    if revision is None:
        return Revision(url, owner, repo, refs.head_branch, refs.head_sha)
    found = refs.match(revision)
    if found is not None:
        shown = found if _SHA.fullmatch(revision) else revision
        return Revision(url, owner, repo, shown, found)
    if _SHA.fullmatch(revision):
        lookup = lookup_commit or _github_commit
        try:
            commit = lookup(owner, repo, revision)
        except ProbeFailure as exc:
            raise AccessError(
                f"Could not verify commit {revision} on {url}. {exc.detail} The scan was not started."
            ) from exc
        if commit is not None:
            return Revision(url, owner, repo, revision, commit)
    raise AccessError(
        f"Revision {revision!r} was not found on {url}. "
        "Expected a branch, a tag, or a commit that GitHub can serve. The scan was not started."
    )


def clone_at(url: str, sha: str, dest) -> None:
    """Clone `sha` into an empty directory. `sha` must already have been resolved."""
    if not _FULL_SHA.fullmatch(sha):
        raise RuntimeError(f"Refusing to fetch unresolved revision {sha!r}.")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    commands = [
        ["git", "init", str(dest)],
        ["git", "-C", str(dest), "remote", "add", "origin", url],
        ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", sha],
        ["git", "-C", str(dest), "checkout", "--detach", "FETCH_HEAD"],
    ]
    env = _git_env()
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                env=env,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"git failed while cloning {url} at {sha}: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "git failed").strip()
            raise RuntimeError(f"git failed while cloning {url} at {sha}: {detail[-1000:]}")


_MANIFEST_LIMIT = 20_000


def list_files(checkout) -> dict | None:
    """Tracked paths of the checkout, so the report can show the whole project tree."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), "ls-files", "-z"],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    paths = sorted(path for path in completed.stdout.decode("utf-8", "replace").split("\0") if path)
    return {"paths": paths[:_MANIFEST_LIMIT], "total": len(paths), "truncated": len(paths) > _MANIFEST_LIMIT}


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    token = env.get("GITHUB_TOKEN", "").strip()
    if token:
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraheader"
        env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: bearer {token}"
    return env


def _git_ls_remote(url: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "ls-remote", "--symref", url],
            capture_output=True,
            text=True,
            timeout=30,
            env=_git_env(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProbeFailure(str(exc)) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ProbeFailure(detail or f"git ls-remote exited {completed.returncode}")
    return completed.stdout


def _github_commit(owner: str, repo: str, revision: str) -> str | None:
    quoted = urllib.request.quote(revision, safe="")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/commits/{quoted}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "code-atlas-scan-api",
        },
    )
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 422}:
            return None
        raise ProbeFailure(f"GitHub API returned {exc.code} while checking commit {revision}.") from exc
    except urllib.error.URLError as exc:
        raise ProbeFailure(f"GitHub API could not be reached: {exc.reason}") from exc
    sha = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(sha, str) or not _FULL_SHA.fullmatch(sha):
        raise ProbeFailure("GitHub API returned a commit without a SHA.")
    return sha


def _parse_refs(output: str) -> RemoteRefs:
    head_branch = None
    head_sha = None
    heads: dict[str, str] = {}
    tags: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("ref: "):
            ref, _, name = line[5:].partition("\t")
            if name == "HEAD" and ref.startswith("refs/heads/"):
                head_branch = ref[len("refs/heads/") :]
            continue
        sha, separator, ref = line.partition("\t")
        if not separator or not _FULL_SHA.fullmatch(sha):
            continue
        if ref == "HEAD":
            head_sha = sha
        elif ref.startswith("refs/heads/"):
            heads[ref[len("refs/heads/") :]] = sha
        elif ref.startswith("refs/tags/"):
            peeled = ref.endswith("^{}")
            name = ref[len("refs/tags/") : -3] if peeled else ref[len("refs/tags/") :]
            if peeled or name not in tags:
                tags[name] = sha
    if head_sha is None and head_branch is not None:
        head_sha = heads.get(head_branch)
    return RemoteRefs(head_branch=head_branch, head_sha=head_sha, heads=heads, tags=tags)


def _access_message(url: str, detail: str) -> str:
    lowered = detail.lower()
    if "not found" in lowered:
        reason = (
            "GitHub reported the repository as not found. It may be private, deleted, "
            "or the owner or name may be wrong. This service has no credentials for it."
        )
    elif "authentication" in lowered or "permission denied" in lowered or "could not read username" in lowered:
        reason = "Authentication failed. This service cannot read that repository."
    elif "timed out" in lowered or "timeout" in lowered or "could not resolve" in lowered or "unable to access" in lowered:
        reason = "The remote could not be reached."
    else:
        reason = "git could not read the repository."
    clipped = detail.replace("\n", " ")[:500]
    return f"Cannot access {url}. {reason} {clipped} The scan was not started."
