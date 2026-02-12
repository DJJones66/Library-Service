import subprocess
import sys
from pathlib import Path


DEFAULT_RUNTIME_REQUIREMENTS = [
    "fastapi",
    "uvicorn",
    "dulwich",
]


def _venv_python(root: Path) -> Path:
    if sys.platform.startswith("win"):
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    venv_python = _venv_python(root)
    requirements = root / "requirements.txt"

    if not venv_python.exists():
        create_script = root / "service_scripts" / "create_venv.py"
        subprocess.run([sys.executable, str(create_script)], check=True)

    subprocess.run([str(venv_python), "-m", "pip", "install", "-U", "pip"], check=True)

    if requirements.exists():
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(requirements)],
            check=True,
        )
        print(f"dependencies installed from {requirements}")
        return

    subprocess.run(
        [str(venv_python), "-m", "pip", "install", *DEFAULT_RUNTIME_REQUIREMENTS],
        check=True,
    )
    print("dependencies installed from default runtime requirements")


if __name__ == "__main__":
    main()
