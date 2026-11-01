import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_devops_guard.approval import (
    GateDenied,
    SignedApproval,
    _canonical,
    approve,
    generate_keys,
    review_bundle,
    simulate_deploy,
)
from ai_devops_guard.cli import main
from ai_devops_guard.pipeline import run_review

ROOT = Path(__file__).resolve().parents[1]


def confirm(prompt):
    # Automated test identity, never a real human approval.
    return re.search(r"APPROVE [a-f0-9]{12}", prompt)[0]


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "plan.json"
    source.write_bytes((ROOT / "examples/terraform/risky.plan.json").read_bytes())
    _, run = run_review(source, tmp_path / "runs")
    keys = tmp_path / "keys"
    generate_keys(keys)
    return run, source, keys


def sign(bundle):
    run, source, keys = bundle
    return approve(
        run,
        source,
        keys / "reviewer.key",
        "Automated test operator",
        "Synthetic fixture only",
        confirm=confirm,
    )


def test_requires_signed_approval_and_audits_denial(bundle):
    run, source, keys = bundle
    with pytest.raises(GateDenied):
        simulate_deploy(run, source, keys / "reviewer.pub", run / "approval.json")
    assert not (run / "simulation-receipt.json").exists()
    log = next(run.glob("gate-*.jsonl"))
    assert [json.loads(line)["status"] for line in log.read_text().splitlines()] == [
        "started",
        "failed",
    ]


def test_valid_signature_public_key_only_and_replay_denied(bundle):
    run, source, keys = bundle
    approval = sign(bundle)
    (keys / "reviewer.key").unlink()  # Verifier does not need or possess the signing key.
    receipt = simulate_deploy(run, source, keys / "reviewer.pub", approval)
    assert json.loads(receipt.read_text())["infrastructure_operations"] == 0
    with pytest.raises(GateDenied):
        simulate_deploy(run, source, keys / "reviewer.pub", approval)


@pytest.mark.parametrize("target", ["source", "report", "audit", "approval"])
def test_mutation_invalidates_approval(bundle, target):
    run, source, keys = bundle
    approval = sign(bundle)
    path = {
        "source": source,
        "report": run / "report.json",
        "audit": run / "audit.jsonl",
        "approval": approval,
    }[target]
    if target == "approval":
        data = json.loads(path.read_text())
        data["claims"]["reviewer"] = "Impersonated reviewer"
        path.write_text(json.dumps(data))
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(GateDenied):
        simulate_deploy(run, source, keys / "reviewer.pub", approval)
    assert not (run / "simulation-receipt.json").exists()


@pytest.mark.parametrize("window", ["expired", "future", "too_long"])
def test_valid_signature_with_invalid_time_is_denied(bundle, window):
    run, source, keys = bundle
    target = sign(bundle)
    signed = SignedApproval.model_validate_json(target.read_text())
    now = datetime.now(UTC)
    issued, expires = {
        "expired": (now - timedelta(hours=1), now - timedelta(minutes=30)),
        "future": (now + timedelta(minutes=10), now + timedelta(minutes=40)),
        "too_long": (now - timedelta(minutes=1), now + timedelta(hours=2)),
    }[window]
    signed.claims.issued_at, signed.claims.expires_at = issued, expires
    key = Ed25519PrivateKey.from_private_bytes((keys / "reviewer.key").read_bytes())
    signed.signature = key.sign(_canonical(signed.claims)).hex()
    target.write_text(signed.model_dump_json())
    with pytest.raises(GateDenied):
        simulate_deploy(run, source, keys / "reviewer.pub", target)


def test_wrong_public_key_is_denied(bundle, tmp_path):
    run, source, keys = bundle
    target = sign(bundle)
    other = tmp_path / "other-key"
    generate_keys(other)
    with pytest.raises(GateDenied):
        simulate_deploy(run, source, other / "reviewer.pub", target)


def test_explicit_confirmation_required(bundle):
    run, source, keys = bundle
    with pytest.raises(GateDenied, match="confirmation"):
        approve(run, source, keys / "reviewer.key", "Reviewer", "Reason", confirm=lambda _: "yes")
    assert not (run / "approval.json").exists()


def test_incomplete_review_cannot_be_signed(bundle, tmp_path):
    _, _, keys = bundle
    source = ROOT / "examples/terraform/unknown.plan.json"
    _, run = run_review(source, tmp_path / "unknown")
    with pytest.raises(GateDenied):
        approve(run, source, keys / "reviewer.key", "Reviewer", "Reason", confirm=confirm)


def test_permissive_private_key_rejected(bundle):
    run, source, keys = bundle
    (keys / "reviewer.key").chmod(0o644)
    with pytest.raises(GateDenied):
        sign(bundle)


def test_report_reanalysis_detects_preapproval_tampering(bundle):
    run, source, keys = bundle
    data = json.loads((run / "report.json").read_text())
    data["findings"] = []
    data["decision"] = "pass"
    (run / "report.json").write_text(json.dumps(data))
    with pytest.raises(GateDenied, match="reanalysis"):
        review_bundle(run, source)


def test_cli_confirmation_and_public_key_gate(bundle, monkeypatch):
    run, source, keys = bundle
    monkeypatch.setattr("builtins.input", confirm)
    assert (
        main(
            [
                "approve",
                "--run-dir",
                str(run),
                "--input",
                str(source),
                "--private-key",
                str(keys / "reviewer.key"),
                "--reviewer",
                "Test reviewer",
                "--reason",
                "Synthetic infrastructure only",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "simulate-deploy",
                "--run-dir",
                str(run),
                "--input",
                str(source),
                "--public-key",
                str(keys / "reviewer.pub"),
            ]
        )
        == 0
    )


def test_kubernetes_bundle_can_be_signed_and_verified(bundle, tmp_path):
    _, _, keys = bundle
    source = ROOT / "examples/kubernetes/risky.yaml"
    _, run = run_review(source, tmp_path / "kube-runs", input_kind="kubernetes")
    target = approve(run, source, keys / "reviewer.key", "Test reviewer", "Synthetic only", confirm)
    assert simulate_deploy(run, source, keys / "reviewer.pub", target).exists()
