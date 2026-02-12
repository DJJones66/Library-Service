import os
import signal
import time
from pathlib import Path


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
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"killed pid={pid}")
        except ProcessLookupError:
            pass

    try:
        pid_file.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
