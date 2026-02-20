import os
import signal
import sys
import time
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


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    pid_file = root / "data" / "service.pid"

    if not pid_file.exists():
        print("pid file not found")
        raise SystemExit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        print("pid file invalid")
        try:
            pid_file.unlink()
        except OSError:
            pass
        raise SystemExit(0)

    if not _pid_is_running(pid):
        print("process not found")
        try:
            pid_file.unlink()
        except OSError:
            pass
        raise SystemExit(0)

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped pid={pid}")
    except ProcessLookupError:
        print("process not found")

    deadline = time.time() + 5
    while time.time() < deadline:
        if not _pid_is_running(pid):
            break
        time.sleep(0.1)

    if _pid_is_running(pid):
        force_signal = signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
        try:
            os.kill(pid, force_signal)
            print(f"killed pid={pid}")
        except ProcessLookupError:
            pass

    try:
        pid_file.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
