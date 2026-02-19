import os
import subprocess
import sys
from pathlib import Path


DEFAULT_PROCESS_HOST = "127.0.0.1"
DEFAULT_PROCESS_PORT = "18170"


def _venv_python(root: Path) -> Path:
    if sys.platform.startswith("win"):
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    venv_python = _venv_python(root)
    if not venv_python.exists():
        raise SystemExit(f"venv python not found: {venv_python}. Run install_with_venv.py first.")

    process_host = os.getenv("PROCESS_HOST", DEFAULT_PROCESS_HOST).strip() or DEFAULT_PROCESS_HOST
    process_port = os.getenv("PROCESS_PORT", DEFAULT_PROCESS_PORT).strip() or DEFAULT_PROCESS_PORT

    env = os.environ.copy()
    env.setdefault("BRAINDRIVE_LIBRARY_PATH", str(root / "library"))
    env.setdefault(
        "BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH",
        str(root / "library_templates" / "Base_Library"),
    )

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    pid_file = data_dir / "service.pid"
    log_file = root / "service_runtime.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _pid_is_running(existing_pid):
                print(f"service already running pid={existing_pid}")
                return
        except (ValueError, OSError):
            pass
        try:
            pid_file.unlink()
        except OSError:
            pass

    cmd = [
        str(venv_python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        process_host,
        "--port",
        process_port,
    ]

    with log_file.open("ab") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log_handle,
            stderr=log_handle,
            env=env,
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    print(f"started pid={proc.pid} host={process_host} port={process_port}")


if __name__ == "__main__":
    main()
