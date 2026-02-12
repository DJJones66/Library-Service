import os
import shutil
import subprocess
import sys
from pathlib import Path


def _force_recreate_enabled() -> bool:
    return os.getenv("VENV_FORCE_RECREATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    venv_dir = root / ".venv"

    if _force_recreate_enabled() and venv_dir.exists():
        shutil.rmtree(venv_dir)

    if not venv_dir.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    print(f"venv ready: {venv_dir}")


if __name__ == "__main__":
    main()
