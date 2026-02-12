from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StepResult:
    name: str
    passed: bool
    details: str = ""


class ApiClient:
    def __init__(self, base_url: str | None, library_root: Path) -> None:
        self._base_url = base_url
        self._library_root = library_root
        self._http: httpx.Client | None = None
        self._test_client = None

        if base_url:
            self._http = httpx.Client(base_url=base_url, timeout=10.0)
        else:
            os.environ["BRAINDRIVE_LIBRARY_PATH"] = str(library_root)
            from fastapi.testclient import TestClient

            from app.main import create_app

            app = create_app()
            self._test_client = TestClient(app)

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
        if self._test_client is not None:
            self._test_client.close()

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if self._http is not None:
            response = self._http.post(path, json=payload)
        else:
            if self._test_client is None:
                raise RuntimeError("Test client is not initialized.")
            response = self._test_client.post(path, json=payload)

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"{path} returned non-JSON response (status {response.status_code})."
            ) from exc

        if response.status_code != 200 or not body.get("ok"):
            raise RuntimeError(
                f"{path} failed with status {response.status_code}: {body}"
            )
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"{path} returned unexpected payload: {body}")
        return data


def _timestamp_slug() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d-%H%M%S")


def _resolve_library_root(
    requested_root: Path | None, base_url: str | None
) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if base_url and requested_root is None:
        raise RuntimeError("--library-root is required when using --base-url.")

    if requested_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="workflow-test-")
        return Path(temp_dir.name), temp_dir

    root = requested_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root, None


def _create_project(project_root: Path) -> None:
    if project_root.exists():
        raise RuntimeError(f"Project already exists: {project_root}")
    project_root.mkdir(parents=True, exist_ok=False)


def _seed_files(spec_path: Path, notes_path: Path) -> None:
    spec_content = "\n".join(
        [
            "# Workflow Test Project",
            "",
            "## Scope",
            "Initial scope.",
            "",
        ]
    )
    notes_content = "\n".join(
        [
            "# Notes",
            "",
            "Initial note.",
            "",
        ]
    )
    spec_path.write_text(spec_content + "\n", encoding="utf-8")
    notes_path.write_text(notes_content + "\n", encoding="utf-8")


def _list_files(client: ApiClient, project_rel: str) -> list[str]:
    data = client.post("/tool:list_markdown_files", {"path": project_rel})
    files = data.get("files")
    if not isinstance(files, list):
        raise RuntimeError("list_markdown_files returned unexpected data.")
    return [str(item) for item in files]


def _write_notes(client: ApiClient, notes_rel: str) -> str:
    data = client.post(
        "/tool:write_markdown",
        {
            "path": notes_rel,
            "operation": {
                "type": "append",
                "content": "Second note added via workflow test.\n",
            },
        },
    )
    commit_sha = data.get("commitSha")
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise RuntimeError("write_markdown did not return a valid commit sha.")
    return commit_sha


def _edit_notes(client: ApiClient, notes_rel: str) -> str:
    data = client.post(
        "/tool:edit_markdown",
        {
            "path": notes_rel,
            "operation": {
                "type": "replace_section",
                "target": "Initial note.",
                "content": "Initial note (edited).\n",
            },
        },
    )
    commit_sha = data.get("commitSha")
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise RuntimeError("edit_markdown did not return a valid commit sha.")
    return commit_sha


def _read_markdown(client: ApiClient, path_rel: str) -> str:
    data = client.post("/tool:read_markdown", {"path": path_rel})
    content = data.get("content")
    if not isinstance(content, str):
        raise RuntimeError("read_markdown returned unexpected data.")
    return content


def _delete_notes(client: ApiClient, notes_rel: str) -> str:
    data = client.post(
        "/tool:delete_markdown",
        {"path": notes_rel, "confirm": True},
    )
    commit_sha = data.get("commitSha")
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise RuntimeError("delete_markdown did not return a valid commit sha.")
    return commit_sha


def _confirm(prompt: str, auto_approve: bool) -> None:
    if auto_approve:
        return
    response = input(f"{prompt} [y/N]: ").strip().lower()
    if response not in {"y", "yes"}:
        raise RuntimeError("User declined permission.")


def _run_step(
    results: list[StepResult],
    name: str,
    action,
    verbose: bool,
) -> None:
    try:
        action()
        results.append(StepResult(name=name, passed=True))
    except Exception as exc:
        if verbose:
            traceback.print_exc()
        results.append(
            StepResult(name=name, passed=False, details=str(exc))
        )


def _summarize(results: list[StepResult]) -> int:
    failures = 0
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        line = f"{status}: {result.name}"
        if result.details:
            line = f"{line} - {result.details}"
        print(line)
        if not result.passed:
            failures += 1

    if failures:
        print(f"\nWorkflow FAILED ({failures}/{len(results)} steps failed).")
        return 1
    print(f"\nWorkflow PASSED ({len(results)} steps).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an approval-gated workflow test against the Library Service."
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        help="Path to the library root (required for --base-url).",
    )
    parser.add_argument(
        "--base-url",
        help="Base URL of a running server (e.g. http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--project",
        help="Project name to create (defaults to a unique workflow-test name).",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the created project directory after the workflow.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip approval prompts and execute all steps.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print stack traces for failures.",
    )
    args = parser.parse_args()

    try:
        library_root, temp_dir = _resolve_library_root(
            args.library_root, args.base_url
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    project_name = args.project or f"workflow-test-{_timestamp_slug()}"
    project_root = (
        library_root / "projects" / "active" / project_name
    )
    spec_path = project_root / "spec.md"
    notes_path = project_root / "notes.md"

    client = ApiClient(args.base_url, library_root)
    results: list[StepResult] = []

    project_rel = project_root.relative_to(library_root).as_posix()
    notes_rel = notes_path.relative_to(library_root).as_posix()

    _run_step(
        results,
        "Create project",
        lambda: _create_project(project_root),
        args.verbose,
    )
    _run_step(
        results,
        "Add files",
        lambda: _seed_files(spec_path, notes_path),
        args.verbose,
    )
    _run_step(
        results,
        "List files",
        lambda: _assert_files_present(
            _list_files(client, project_rel),
            [
                spec_path.relative_to(library_root).as_posix(),
                notes_rel,
            ],
        ),
        args.verbose,
    )
    _run_step(
        results,
        "Write notes (approval required)",
        lambda: _approved_action(
            "Allow writing to notes.md?",
            args.auto_approve,
            lambda: _write_notes(client, notes_rel),
        ),
        args.verbose,
    )
    _run_step(
        results,
        "Edit notes (approval required)",
        lambda: _approved_action(
            "Allow editing notes.md?",
            args.auto_approve,
            lambda: _edit_notes(client, notes_rel),
        ),
        args.verbose,
    )
    _run_step(
        results,
        "Read notes",
        lambda: _assert_content(
            _read_markdown(client, notes_rel),
            "Initial note (edited).",
        ),
        args.verbose,
    )
    _run_step(
        results,
        "Delete notes (approval required)",
        lambda: _approved_action(
            "Allow deleting notes.md?",
            args.auto_approve,
            lambda: _delete_notes(client, notes_rel),
        ),
        args.verbose,
    )
    _run_step(
        results,
        "Verify deletion",
        lambda: _assert_files_absent(
            _list_files(client, project_rel),
            [notes_rel],
        ),
        args.verbose,
    )

    exit_code = _summarize(results)

    if args.cleanup:
        try:
            if project_root.exists():
                for child in project_root.rglob("*"):
                    if child.is_file():
                        child.unlink()
                for child in sorted(
                    project_root.rglob("*"),
                    reverse=True,
                ):
                    if child.is_dir():
                        child.rmdir()
                project_root.rmdir()
        except OSError as exc:
            print(f"Cleanup failed: {exc}", file=sys.stderr)
            if exit_code == 0:
                exit_code = 1

    client.close()
    if temp_dir is not None:
        temp_dir.cleanup()
    return exit_code


def _approved_action(prompt: str, auto_approve: bool, action) -> None:
    _confirm(prompt, auto_approve)
    action()


def _assert_files_present(files: list[str], expected: list[str]) -> None:
    missing = sorted(set(expected) - set(files))
    if missing:
        raise RuntimeError(f"Missing files: {missing}")


def _assert_files_absent(files: list[str], unexpected: list[str]) -> None:
    present = sorted(set(unexpected) & set(files))
    if present:
        raise RuntimeError(f"Files still present: {present}")


def _assert_content(content: str, expected_snippet: str) -> None:
    if expected_snippet not in content:
        raise RuntimeError(
            f"Expected content not found: {expected_snippet}"
        )


if __name__ == "__main__":
    sys.exit(main())
