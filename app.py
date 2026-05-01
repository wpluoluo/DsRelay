import os
import sys
from pathlib import Path

def ensure_project_venv_python() -> None:
    project_root = Path(__file__).resolve().parent
    spoofed_python = os.environ.get("PYTHONEXECUTABLE")
    if spoofed_python:
        print(
            "[local-proxy] refused to start with PYTHONEXECUTABLE set: "
            f"{spoofed_python}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(86)

    expected_python = (project_root / ".venv" / "Scripts" / "python.exe").resolve()
    current_python = Path(sys.executable).resolve()
    if current_python != expected_python:
        print(
            "[local-proxy] refused to start with non-project python: "
            f"current={current_python} expected={expected_python}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(86)


if __name__ == "__main__":
    ensure_project_venv_python()
    from local_proxy.server import run_proxy_app

    run_proxy_app()
