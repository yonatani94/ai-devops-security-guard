"""Reproducible proof from real CLI executions and an explicitly automated gate demo."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_devops_guard.approval import GateDenied, approve, generate_keys, simulate_deploy
from ai_devops_guard.audit import AuditWriter
from ai_devops_guard.models import Assessment
from ai_devops_guard.tools import ToolDenied, ToolDispatcher

ROOT = Path(__file__).resolve().parents[1]


def verify(output: Path, provider: str, config: Path | None = None) -> dict:
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    proof = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": provider,
        "runs": [],
        "deployment_scope": "simulation only",
        "remote_ci_verified": False,
    }
    cases = [
        ("terraform-safe", "--plan", "examples/terraform/safe.plan.json", 0),
        ("terraform-risky", "--plan", "examples/terraform/risky.plan.json", 1),
        ("terraform-unknown", "--plan", "examples/terraform/unknown.plan.json", 2),
        ("kubernetes-safe", "--manifest", "examples/kubernetes/safe.yaml", 0),
        ("kubernetes-risky", "--manifest", "examples/kubernetes/risky.yaml", 1),
    ]
    for label, flag, source, expected in cases:
        destination = output / label
        command = [
            "-m",
            "ai_devops_guard",
            "review",
            flag,
            source,
            "--ai-provider",
            provider,
            "--output-dir",
            str(destination),
        ]
        if config is not None:
            command.extend(["--ai-config", str(config.resolve())])
        start = time.monotonic()
        completed = subprocess.run(
            [sys.executable, *command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if completed.returncode != expected:
            raise RuntimeError(f"unexpected CLI result for {label}: {completed.returncode}")
        run = next(destination.iterdir())
        report = Assessment.model_validate_json((run / "report.json").read_text())
        expected_ai = (
            "not_run"
            if label == "terraform-unknown"
            else "complete"
            if provider != "fake"
            else "simulated"
        )
        if report.ai_status != expected_ai:
            raise RuntimeError(f"inference did not complete for {label}")
        records = [json.loads(line) for line in (run / "audit.jsonl").read_text().splitlines()]
        model_calls = sum(e["caller"] == "model" and e["status"] == "succeeded" for e in records)
        if provider != "fake" and report.findings and model_calls != 1:
            raise RuntimeError("expected one real model-requested read-only tool call")
        proof["runs"].append(
            {
                "label": label,
                "source": source,
                "run_dir": str(run.relative_to(output)),
                "run_id": str(report.run_id),
                "exit_code": completed.returncode,
                "decision": report.decision,
                "findings": len(report.findings),
                "coverage_gaps": len(report.coverage_gaps),
                "ai_status": report.ai_status,
                "model": report.ai_model,
                "ai_provider": report.ai_provider,
                "request_ids": report.ai_request_ids,
                "model_tool_calls": model_calls,
                "audit_events": len(records),
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "source_digest": report.source_digest,
            }
        )
        print(
            f"VERIFIED {label}: exit={completed.returncode}; AI={report.ai_status}; "
            f"findings={len(report.findings)}; model_tool_calls={model_calls}",
            flush=True,
        )
    risky = proof["runs"][1]
    run = output / risky["run_dir"]
    source = ROOT / risky["source"]
    gate_checks = {}
    with tempfile.TemporaryDirectory(prefix="guard-demo-") as temp:
        keys = Path(temp) / "keys"
        generate_keys(keys)
        try:
            simulate_deploy(run, source, keys / "reviewer.pub", run / "approval.json")
        except GateDenied:
            gate_checks["unsigned_blocked"] = True
        else:
            raise RuntimeError("unsigned simulation was not blocked")
        approval = approve(
            run,
            source,
            keys / "reviewer.key",
            "Automated demo operator (not human approval)",
            "Synthetic fixture; demonstrate signature verification only",
            confirm=lambda prompt: re.search(r"APPROVE [a-f0-9]{12}", prompt)[0],
        )
        altered = Path(temp) / "changed.plan.json"
        altered.write_bytes(source.read_bytes() + b"\n")
        try:
            simulate_deploy(run, altered, keys / "reviewer.pub", approval)
        except GateDenied:
            gate_checks["changed_input_blocked"] = True
        else:
            raise RuntimeError("changed input was not blocked")
        # Export public verification material only; the private key is destroyed with temp.
        shutil.copyfile(keys / "reviewer.pub", output / "demo-reviewer.pub")
        receipt = simulate_deploy(run, source, keys / "reviewer.pub", approval)
        gate_checks["signed_simulation_verified"] = json.loads(receipt.read_text())[
            "simulation_only"
        ]
        try:
            simulate_deploy(run, source, keys / "reviewer.pub", approval)
        except GateDenied:
            gate_checks["replay_blocked"] = True
        else:
            raise RuntimeError("replay was not blocked")
    log = output / "attack-probe.audit.jsonl"
    with AuditWriter(log) as audit:
        dispatcher = ToolDispatcher(source, audit, uuid4())
        try:
            dispatcher.call("simulate_deploy", {}, caller="model")
        except ToolDenied:
            gate_checks["model_deployment_tool_denied"] = True
        else:
            raise RuntimeError("model deployment capability was not denied")
    proof["gate_checks"] = gate_checks
    proof["approval_identity"] = "automated demonstration; not a real human approval"
    (output / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(f"VERIFIED {len(gate_checks)} gate checks. Evidence: {output / 'proof.json'}", flush=True)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--provider", choices=["fake", "ollama", "openai-compatible"], default="fake"
    )
    parser.add_argument("--ai-config", type=Path)
    args = parser.parse_args()
    verify(args.output.resolve(), args.provider, args.ai_config)


if __name__ == "__main__":
    main()
