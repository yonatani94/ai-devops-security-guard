"""Synthetic GitHub approval demo helpers. No production infrastructure support."""

import argparse
import json
import os
import shutil
from pathlib import Path

from ai_devops_guard.approval import review_bundle
from ai_devops_guard.pipeline import run_review
from ai_devops_guard.storage import write_private

ENVIRONMENTS = {"independent": "security-review", "solo-demo": "security-review-solo-demo"}


def environment_for(mode: str) -> str:
    if mode not in ENVIRONMENTS:
        raise ValueError("unknown approval mode")
    return ENVIRONMENTS[mode]


def validate_environment(
    data: dict, mode: str = "independent", expected_reviewer: str | None = None
) -> None:
    if data.get("name") != environment_for(mode):
        raise ValueError("approval mode and environment name do not match")
    if mode == "solo-demo" and not expected_reviewer:
        raise ValueError("solo demo requires an explicit expected reviewer")
    rules = data.get("protection_rules", [])
    if not any(
        rule.get("type") == "required_reviewers"
        and rule.get("reviewers")
        and rule.get("prevent_self_review") is (mode == "independent")
        and (
            mode == "independent"
            or any(
                item.get("type") == "User"
                and item.get("reviewer", {}).get("login", "").casefold()
                == expected_reviewer.casefold()
                for item in rule["reviewers"]
            )
        )
        for rule in rules
    ):
        raise ValueError("required reviewers and self-review policy do not match the selected mode")


def prepare(kind: str, output: Path, mode: str = "independent") -> str:
    environment_for(mode)
    if kind not in {"terraform", "kubernetes"}:
        raise ValueError("only synthetic Terraform/Kubernetes fixtures are supported")
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
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"## Approval mode: {mode}\n\n")
            if mode == "solo-demo":
                stream.write(
                    "Self-review is permitted for this synthetic-only demonstration. "
                    "No infrastructure operations or cloud credentials are used.\n\n"
                )
            stream.write(f"Reviewed bundle SHA256: `{digest}`\n\n")
            stream.write((run / "report.md").read_text())
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"digest={digest}\n")
    return digest


def verify(output: Path, expected: str, mode: str = "independent") -> None:
    environment = environment_for(mode)
    assessment, digest = review_bundle(output / "review", output / "input")
    if digest != expected or assessment.decision != "review_required":
        raise ValueError("artifact differs from the reviewed bundle")
    if mode == "solo-demo":
        fixture = Path(
            "examples/terraform/risky.plan.json"
            if assessment.input_kind == "terraform"
            else "examples/kubernetes/risky.yaml"
        )
        if (
            assessment.ai_status != "simulated"
            or (output / "input").read_bytes() != fixture.read_bytes()
        ):
            raise ValueError(
                "solo demo permits only the exact synthetic fixture and fake inference"
            )
    write_private(
        output / "github-simulation-receipt.json",
        json.dumps(
            {
                "simulation_only": True,
                "bundle_digest": digest,
                "authorization": f"GitHub {environment} environment",
                "approval_mode": mode,
                "self_review_permitted": mode == "solo-demo",
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
    check.add_argument("--mode", choices=list(ENVIRONMENTS), default="independent")
    check.add_argument("--expected-reviewer")
    build = commands.add_parser("prepare")
    build.add_argument("--kind", choices=["terraform", "kubernetes"], required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--mode", choices=list(ENVIRONMENTS), default="independent")
    gate = commands.add_parser("verify")
    gate.add_argument("--output", type=Path, required=True)
    gate.add_argument("--expected-digest", required=True)
    gate.add_argument("--mode", choices=list(ENVIRONMENTS), default="independent")
    args = parser.parse_args()
    if args.command == "check-environment":
        validate_environment(json.loads(args.path.read_text()), args.mode, args.expected_reviewer)
        print(f"Required-reviewer policy verified for {args.mode} mode.")
    elif args.command == "prepare":
        print(prepare(args.kind, args.output, args.mode))
    else:
        verify(args.output, args.expected_digest, args.mode)
        print("Exact reviewed artifact verified. SIMULATION ONLY; zero infrastructure operations.")


if __name__ == "__main__":
    main()
