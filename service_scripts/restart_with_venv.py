import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    shutdown = root / "service_scripts" / "shutdown_with_venv.py"
    start = root / "service_scripts" / "start_with_venv.py"

    subprocess.run([sys.executable, str(shutdown)], check=False)
    subprocess.run([sys.executable, str(start)], check=True)


if __name__ == "__main__":
    main()
