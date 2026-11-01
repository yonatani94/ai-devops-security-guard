"""Synthetic GitHub approval demo helpers. No production infrastructure support."""

import argparse
import json
import os
import shutil
from pathlib import Path

from ai_devops_guard.approval import review_bundle
from ai_devops_guard.pipeline import run_review
from ai_devops_guard.storage import write_private


def validate_environment(data: dict) -> None:
    rules = data.get("protection_rules", [])
    if not any(
        rule.get("type") == "required_reviewers"
        and rule.get("reviewers")
        and rule.get("prevent_self_review") is True
        for rule in rules
    ):
        raise ValueError("security-review must require reviewers and prevent self-review")


def prepare(kind: str, output: Path) -> str:
    source = Path(
        "examples/terraform/risky.plan.json"
        if kind == "terraform"
        else "examples/kubernetes/risky.yaml"
    )
    output.mkdir(mode=0o700)
    assessment, run = run_review(source, output / "runs", input_kind=kind)
    if assessment.decision != "review_required":
        raise ValueError("synthetic fixture must produce findings requiring review")
    shutil.copytree(run, output / "review")
    write_private(output / "input", source.read_bytes())
    _, digest = review_bundle(output / "review", output / "input")
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"digest={digest}\n")
    return digest


def verify(output: Path, expected: str) -> None:
    assessment, digest = review_bundle(output / "review", output / "input")
    if digest != expected or assessment.decision != "review_required":
        raise ValueError("artifact differs from the reviewed bundle")
    write_private(
        output / "github-simulation-receipt.json",
        json.dumps(
            {
                "simulation_only": True,
                "bundle_digest": digest,
                "authorization": "GitHub security-review environment",
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_sha": os.environ.get("GITHUB_SHA"),
                "infrastructure_operations": 0,
            },
            indent=2,
        ).encode(),
    )


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-environment")
    check.add_argument("path", type=Path)
    build = commands.add_parser("prepare")
    build.add_argument("--kind", choices=["terraform", "kubernetes"], required=True)
    build.add_argument("--output", type=Path, required=True)
    gate = commands.add_parser("verify")
    gate.add_argument("--output", type=Path, required=True)
    gate.add_argument("--expected-digest", required=True)
    args = parser.parse_args()
    if args.command == "check-environment":
        validate_environment(json.loads(args.path.read_text()))
        print("Required-reviewer protection verified; self-review is disabled.")
    elif args.command == "prepare":
        print(prepare(args.kind, args.output))
    else:
        verify(args.output, args.expected_digest)
        print("Exact reviewed artifact verified. SIMULATION ONLY; zero infrastructure operations.")


if __name__ == "__main__":
    main()
