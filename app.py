import os
import sys
from pathlib import Path


def iter_project_python_candidates(project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    env_dirs: list[Path] = []

    primary_env = project_root / ".venv"
    if primary_env.is_dir():
        env_dirs.append(primary_env)

    for env_dir in sorted(project_root.glob(".venv*")):
        if env_dir.is_dir():
            env_dirs.append(env_dir)

    for env_dir in env_dirs:
        candidate = (env_dir / "Scripts" / "python.exe").resolve()
        env_config = env_dir / "pyvenv.cfg"
        candidate_key = str(candidate).lower()
        if candidate_key in seen or not env_config.exists():
            continue
        seen.add(candidate_key)
        candidates.append(candidate)

    return candidates


def ensure_project_venv_python() -> None:
    if os.environ.get("RUNNING_IN_DOCKER") == "1":
        return

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

    expected_pythons = iter_project_python_candidates(project_root)
    current_python = Path(sys.executable).resolve()
    if current_python not in expected_pythons:
        expected_display = ", ".join(str(path) for path in expected_pythons) or "<no project venv found>"
        print(
            "[local-proxy] refused to start with non-project python: "
            f"current={current_python} expected_any={expected_display}",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(86)


if __name__ == "__main__":
    ensure_project_venv_python()
    from local_proxy.server import run_proxy_app

    run_proxy_app()
