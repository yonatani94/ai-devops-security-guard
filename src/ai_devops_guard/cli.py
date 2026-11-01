import argparse
import sys
from pathlib import Path

from ai_devops_guard.ai.config import AISettings, create_provider, load_settings
from ai_devops_guard.approval import GateDenied, approve, generate_keys, simulate_deploy
from ai_devops_guard.audit import AuditError
from ai_devops_guard.pipeline import run_review

EXIT_CODES = {"pass": 0, "review_required": 1, "error": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Terraform and Kubernetes risk review.")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    source = review.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", type=Path)
    source.add_argument("--manifest", type=Path)
    review.add_argument("--ai-config", type=Path, help="TOML provider configuration (no secrets)")
    review.add_argument("--ai-provider", choices=["fake", "ollama", "openai-compatible"])
    review.add_argument("--model")
    review.add_argument("--timeout", type=float)
    review.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    keys = commands.add_parser("keygen", help="Create local demo reviewer keys")
    keys.add_argument("--output-dir", required=True, type=Path)
    sign = commands.add_parser("approve", help="Interactively sign an exact reviewed bundle")
    sign.add_argument("--run-dir", required=True, type=Path)
    sign.add_argument("--input", required=True, type=Path)
    sign.add_argument("--private-key", required=True, type=Path)
    sign.add_argument("--reviewer", required=True)
    sign.add_argument("--reason", required=True)
    gate = commands.add_parser(
        "simulate-deploy", help="Verify approval and write a simulation receipt"
    )
    gate.add_argument("--run-dir", required=True, type=Path)
    gate.add_argument("--input", required=True, type=Path)
    gate.add_argument("--public-key", required=True, type=Path)
    gate.add_argument("--approval", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            fingerprint = generate_keys(args.output_dir)
            print(f"Demo reviewer keys created. Public key SHA256: {fingerprint}")
            return 0
        if args.command == "approve":
            path = approve(
                args.run_dir,
                args.input,
                args.private_key,
                args.reviewer,
                args.reason,
                confirm=input,
            )
            print(f"Signed local simulation approval: {path}")
            return 0
        if args.command == "simulate-deploy":
            path = simulate_deploy(
                args.run_dir,
                args.input,
                args.public_key,
                args.approval or args.run_dir / "approval.json",
            )
            print(
                "Approval verified. SIMULATION ONLY; zero infrastructure operations. "
                f"Receipt: {path}"
            )
            return 0
        overrides = {
            key: value
            for key, value in {
                "provider": args.ai_provider,
                "model": args.model,
                "timeout_seconds": args.timeout,
            }.items()
            if value is not None
        }
        settings = AISettings(**(load_settings(args.ai_config).model_dump() | overrides))
        provider = create_provider(settings)
        assessment, directory = run_review(
            args.plan or args.manifest,
            args.output_dir,
            input_kind="terraform" if args.plan else "kubernetes",
            provider=provider,
        )
    except GateDenied:
        print("Approval gate denied the operation. No infrastructure was changed.", file=sys.stderr)
        return 2
    except (AuditError, OSError, ValueError, EOFError):
        print(
            "Review aborted: audit or report persistence failed. No usable result.", file=sys.stderr
        )
        return 2
    # Never print plan fields or provider text to a CI log.
    print(f"Decision: {assessment.decision}; AI: {assessment.ai_status}; run: {assessment.run_id}")
    print(f"Reports and audit: {directory}")
    return EXIT_CODES[assessment.decision]


if __name__ == "__main__":
    raise SystemExit(main())
