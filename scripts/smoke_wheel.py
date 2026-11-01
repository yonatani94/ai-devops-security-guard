"""Install the built wheel with locked constraints, then run outside the checkout."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    uv = root / ".venv/bin/uv"
    wheel = root / "dist/ai_devops_security_guard-0.2.0-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="guard-wheel-smoke-") as temp:
        directory = Path(temp)
        environment = directory / "env"
        constraints = directory / "runtime.txt"
        subprocess.run(
            [
                str(uv),
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--format",
                "requirements-txt",
                "--output-file",
                str(constraints),
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        subprocess.run(
            [
                str(uv),
                "pip",
                "install",
                "--python",
                str(environment / "bin/python"),
                "--index-url",
                "https://pypi.org/simple",
                "--cache-dir",
                "/private/tmp/ai-devops-guard-uv-cache",
                "--constraint",
                str(constraints),
                str(wheel),
            ],
            check=True,
        )
        clean = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        completed = subprocess.run(
            [
                str(environment / "bin/ai-devops-guard"),
                "review",
                "--plan",
                str(root / "examples/terraform/safe.plan.json"),
                "--output-dir",
                str(directory / "output"),
            ],
            cwd=directory,
            env=clean,
            capture_output=True,
            text=True,
            check=True,
        )
        if "Decision: pass" not in completed.stdout:
            raise RuntimeError("installed CLI smoke review did not pass")
        print("Built wheel installed successfully; CLI verified outside the source checkout.")


if __name__ == "__main__":
    main()
