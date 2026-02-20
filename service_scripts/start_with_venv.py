import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

if sys.platform.startswith("win"):
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _OPEN_PROCESS = _KERNEL32.OpenProcess
    _OPEN_PROCESS.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _OPEN_PROCESS.restype = wintypes.HANDLE
    _GET_EXIT_CODE_PROCESS = _KERNEL32.GetExitCodeProcess
    _GET_EXIT_CODE_PROCESS.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _GET_EXIT_CODE_PROCESS.restype = wintypes.BOOL
    _CLOSE_HANDLE = _KERNEL32.CloseHandle
    _CLOSE_HANDLE.argtypes = [wintypes.HANDLE]
    _CLOSE_HANDLE.restype = wintypes.BOOL
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5


DEFAULT_PROCESS_HOST = "127.0.0.1"
DEFAULT_PROCESS_PORT = "18170"


def _venv_python(root: Path) -> Path:
    if sys.platform.startswith("win"):
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False

    if sys.platform.startswith("win"):
        handle = _OPEN_PROCESS(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Access denied still means the PID exists.
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED

        try:
            exit_code = wintypes.DWORD()
            if not _GET_EXIT_CODE_PROCESS(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == _STILL_ACTIVE
        finally:
            _CLOSE_HANDLE(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    except SystemError:
        return False
    return True


def _runtime_log_line(log_file: Path, message: str) -> None:
    """Append a timestamped diagnostic line to service_runtime.log."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    line = f"[{timestamp}] {message}\n"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            # Best-effort durability; some filesystems may not support fsync.
            pass


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    log_file = root / "service_runtime.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    venv_python = _venv_python(root)
    if not venv_python.exists():
        message = f"venv python not found: {venv_python}. Run install_with_venv.py first."
        _runtime_log_line(log_file, message)
        raise SystemExit(message)

    process_host = os.getenv("PROCESS_HOST", DEFAULT_PROCESS_HOST).strip() or DEFAULT_PROCESS_HOST
    process_port = os.getenv("PROCESS_PORT", DEFAULT_PROCESS_PORT).strip() or DEFAULT_PROCESS_PORT

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("BRAINDRIVE_LIBRARY_PATH", str(root / "library"))
    env.setdefault(
        "BRAINDRIVE_LIBRARY_BASE_TEMPLATE_PATH",
        str(root / "library_templates" / "Base_Library"),
    )

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    pid_file = data_dir / "service.pid"

    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text(encoding="utf-8").strip())
            if _pid_is_running(existing_pid):
                _runtime_log_line(log_file, f"service already running pid={existing_pid}")
                print(f"service already running pid={existing_pid}")
                return
        except (ValueError, OSError):
            pass
        try:
            pid_file.unlink()
            _runtime_log_line(log_file, "removed stale pid file before startup")
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

    _runtime_log_line(
        log_file,
        (
            "starting library service "
            f"host={process_host} port={process_port} cwd={root} python={venv_python}"
        ),
    )
    _runtime_log_line(log_file, f"launch command: {' '.join(cmd)}")

    try:
        with log_file.open("ab") as log_handle:
            proc = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                env=env,
            )
    except Exception as exc:
        _runtime_log_line(log_file, f"failed to spawn process: {exc!r}")
        raise

    # Catch fast failures to avoid "started" false positives.
    time.sleep(0.4)
    exit_code = proc.poll()
    if exit_code is not None:
        _runtime_log_line(
            log_file,
            f"service exited immediately after launch (exit_code={exit_code})",
        )
        raise SystemExit(
            f"service failed to start (exit_code={exit_code}); see {log_file}"
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    _runtime_log_line(log_file, f"service started pid={proc.pid}")
    print(f"started pid={proc.pid} host={process_host} port={process_port}")


if __name__ == "__main__":
    main()
