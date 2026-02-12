"""Git helpers for MCP endpoints."""

from __future__ import annotations

from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

from app.errors import McpError
from app.mcp_utils import _atomic_write, _atomic_write_bytes


def _resolve_git_head(library_root: Path) -> str | None:
    git_dir = library_root / ".git"
    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return None

    try:
        head_contents = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if head_contents.startswith("ref:"):
        ref_name = head_contents.partition("ref:")[2].strip()
        if not ref_name:
            return None
        ref_path = git_dir / ref_name
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding="utf-8").strip() or None
            except OSError:
                return None
        packed_refs = git_dir / "packed-refs"
        return _lookup_packed_ref(packed_refs, ref_name)

    return head_contents or None


def _read_head_state(library_root: Path) -> tuple[Path | None, str | None]:
    git_dir = library_root / ".git"
    head_path = git_dir / "HEAD"
    if not head_path.exists():
        return None, None

    try:
        head_contents = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, None

    if head_contents.startswith("ref:"):
        ref_name = head_contents.partition("ref:")[2].strip()
        if not ref_name:
            return None, None
        ref_path = git_dir / ref_name
        if ref_path.exists():
            try:
                return (
                    ref_path,
                    ref_path.read_text(encoding="utf-8").strip() or None,
                )
            except OSError:
                return ref_path, None
        packed_refs = git_dir / "packed-refs"
        return ref_path, _lookup_packed_ref(packed_refs, ref_name)

    return None, head_contents or None


def _restore_git_head(
    library_root: Path,
    ref_path: Path | None,
    previous_head: str | None,
) -> None:
    head_path = library_root / ".git" / "HEAD"

    if ref_path is None:
        if previous_head is None or not head_path.exists():
            return
        try:
            if previous_head:
                head_path.write_text(f"{previous_head}\n", encoding="utf-8")
            else:
                head_path.write_text("", encoding="utf-8")
        except OSError:
            return
        return

    try:
        if previous_head is None:
            if ref_path.exists():
                ref_path.unlink()
        else:
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(f"{previous_head}\n", encoding="utf-8")
    except OSError:
        return


def _ensure_git_repo(library_root: Path) -> Repo:
    git_dir = library_root / ".git"
    try:
        if git_dir.exists():
            return Repo(library_root)
        return porcelain.init(library_root)
    except Exception as exc:
        raise McpError(
            "GIT_ERROR",
            "Git repository could not be initialized.",
            {"path": str(library_root)},
        ) from exc


def _commit_markdown_change(
    repo: Repo, relative_path: Path, operation: str
) -> str:
    repo.get_worktree().stage([str(relative_path)])
    commit_message = f"{operation}: {relative_path.as_posix()}"
    commit_sha = porcelain.commit(repo, message=commit_message)
    if isinstance(commit_sha, bytes):
        return commit_sha.decode("ascii")
    return str(commit_sha)


def _commit_markdown_changes(
    repo: Repo,
    relative_paths: list[Path],
    operation: str,
    target: Path,
) -> str:
    repo.get_worktree().stage([str(path) for path in relative_paths])
    commit_message = f"{operation}: {target.as_posix()}"
    commit_sha = porcelain.commit(repo, message=commit_message)
    if isinstance(commit_sha, bytes):
        return commit_sha.decode("ascii")
    return str(commit_sha)


def _rollback_markdown_change(
    repo: Repo | None,
    target_path: Path,
    relative_path: Path,
    original_content: str | bytes,
) -> None:
    if isinstance(original_content, bytes):
        _atomic_write_bytes(target_path, original_content)
    else:
        _atomic_write(target_path, original_content)
    if repo is None:
        return
    try:
        repo.get_worktree().stage([str(relative_path)])
    except Exception:
        pass


def _rollback_created_file(
    repo: Repo | None,
    target_path: Path,
    relative_path: Path,
) -> None:
    try:
        if target_path.exists():
            target_path.unlink()
    except OSError:
        pass
    if repo is None:
        return
    try:
        repo.get_worktree().stage([str(relative_path)])
    except Exception:
        pass


def _rollback_created_project(
    repo: Repo | None,
    created_files: list[Path],
    project_root: Path,
    relative_paths: list[Path] | None = None,
) -> None:
    for created_file in created_files:
        try:
            if created_file.exists():
                created_file.unlink()
        except OSError:
            pass

    for path in sorted(project_root.rglob("*"), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        project_root.rmdir()
    except OSError:
        pass

    if repo is None:
        return
    try:
        paths = relative_paths or []
        repo.get_worktree().stage([str(path) for path in paths])
    except Exception:
        pass


def _lookup_packed_ref(packed_refs: Path, ref_name: str) -> str | None:
    if not packed_refs.exists():
        return None
    try:
        contents = packed_refs.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in contents.splitlines():
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        sha, _, name = line.partition(" ")
        if name.strip() == ref_name:
            return sha
    return None
