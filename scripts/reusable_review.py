"""Trusted entry point for the secret-free reusable CI workflow.

The caller checkout supplies data only. Do not import or execute its code.
"""

import argparse
import json
import os
from pathlib import Path

from ai_devops_guard.pipeline import run_review

EXIT_CODES = {"pass": 0, "review_required": 1, "error": 2}


def confined_input(workspace: Path, relative: str) -> Path:
    root = workspace.resolve(strict=True)
    requested = Path(relative)
    if not relative or requested.is_absolute() or ".." in requested.parts:
        raise ValueError("input must be a relative path within the caller checkout")
    current = root
    for part in requested.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("input path must not contain symlinks")
    current.resolve(strict=True).relative_to(root)
    if not current.is_file():
        raise ValueError("input must be a regular file")
    return current


def review(workspace: Path, relative: str, kind: str, output: Path) -> dict:
    if kind not in {"terraform", "kubernetes"}:
        raise ValueError("unsupported input kind")
    source = confined_input(workspace, relative)
    report, directory = run_review(source, output, input_kind=kind)
    return {
        "decision": report.decision,
        "exit-code": str(EXIT_CODES[report.decision]),
        "run-id": str(report.run_id),
        "input-digest": report.source_digest or "",
        "finding-count": str(len(report.findings)),
        "coverage-gap-count": str(len(report.coverage_gaps)),
        "report-directory": str(directory),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--kind", choices=["terraform", "kubernetes"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = review(args.workspace, args.input_path, args.kind, args.output)
    except (OSError, ValueError):
        # Never echo an untrusted path, manifest, exception, or model response.
        result = {"decision": "error", "exit-code": "2"}
    outputs = {key: value for key, value in result.items() if key != "report-directory"}
    if target := os.environ.get("GITHUB_OUTPUT"):
        with Path(target).open("a") as stream:
            for key, value in outputs.items():
                stream.write(f"{key}={value}\n")
    if target := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(target).open("a") as stream:
            stream.write("## GUARD infrastructure review\n\n")
            stream.write(f"Decision: **{result['decision']}**\n\n")
            stream.write(f"Findings: {result.get('finding-count', 'unavailable')}\n\n")
            stream.write(f"Coverage gaps: {result.get('coverage-gap-count', 'unavailable')}\n\n")
            stream.write("Offline template explanation. No model request or deployment.\n")
    print(json.dumps(outputs, sort_keys=True))
    return int(result["exit-code"])


if __name__ == "__main__":
    raise SystemExit(main())
