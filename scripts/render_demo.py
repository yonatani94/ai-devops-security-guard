"""Render a cinematic evidence replay, never fabricated UI or invented metrics."""

import argparse
import json
import math
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1280, 800, 12
BG, PANEL, LINE = "#0b0e18", "#111827", "#283247"
WHITE, MUTED, MINT, PURPLE, RED, AMBER = (
    "#f1f3ff",
    "#a4aec8",
    "#7cf4be",
    "#b8a4ff",
    "#ff8fa5",
    "#f3c77d",
)


def font(size, bold=False, mono=False):
    candidates = (
        ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
        if mono
        else [
            f"/System/Library/Fonts/Supplemental/Arial{' Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        ]
    )
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def text(draw, x, y, value, size=20, color=WHITE, bold=False, mono=False):
    draw.text((x, y), str(value), font=font(size, bold, mono), fill=color)


def wrap(draw, x, y, value, width, size=20, color=WHITE, leading=1.45):
    line = ""
    for word in value.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font(size)) > width and line:
            text(draw, x, y, line, size, color)
            y += int(size * leading)
            line = word
        else:
            line = trial
    if line:
        text(draw, x, y, line, size, color)
        y += int(size * leading)
    return y


def panel(draw, box):
    draw.rounded_rectangle(box, radius=18, fill=PANEL, outline=LINE, width=1)


def tag(draw, x, y, value, color=MINT):
    width = int(draw.textlength(value, font=font(12, bold=True))) + 26
    draw.rounded_rectangle((x, y, x + width, y + 29), radius=14, outline=color)
    text(draw, x + 13, y + 7, value, 12, color, bold=True)


def background():
    image = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(glow)
    draw.ellipse((680, -360, 1700, 600), fill="#191d42")
    draw.ellipse((-500, 500, 700, 1400), fill="#0d2428")
    image = Image.blend(image, glow.filter(ImageFilter.GaussianBlur(110)), 0.6)
    draw = ImageDraw.Draw(image)
    for x in range(0, W, 64):
        draw.line((x, 0, x, H), fill="#151b2b")
    for y in range(0, H, 64):
        draw.line((0, y, W, y), fill="#151b2b")
    return image


BASE = background()


def chrome(image, scene, t):
    draw = ImageDraw.Draw(image)
    draw.polygon([(64, 42), (92, 42), (92, 63), (78, 76), (64, 63)], fill=MINT)
    text(draw, 104, 41, "GUARD", 26, WHITE, bold=True)
    text(draw, 235, 49, "AI DEVOPS SECURITY GUARD", 12, MUTED, mono=True)
    tag(draw, 995, 43, "VERIFIED LOCAL RUNS")
    draw.line((64, 103, 1216, 103), fill=LINE)
    labels = ["INTRODUCE", "FIND RISK", "BOUND THE AGENT", "VERIFY APPROVAL", "REVIEW THE RESULT"]
    for index, label in enumerate(labels):
        x = 64 + index * 234
        draw.line((x, 731, x + 208, 731), fill=MINT if index <= scene else LINE, width=2)
        text(
            draw,
            x,
            744,
            f"0{index + 1}  {label}",
            10,
            WHITE if index == scene else MUTED,
            mono=True,
        )
    text(
        draw,
        64,
        777,
        "Evidence replay / synthetic infrastructure / zero deployment operations",
        10,
        MUTED,
    )
    text(draw, 1035, 777, "LOCAL RELEASE CANDIDATE", 10, MUTED, mono=True)
    # A restrained scan line connects the sequences visually.
    draw.line((int((t * 80) % W), 103, int((t * 80) % W) + 36, 103), fill=MINT, width=2)


def scene_intro(image, proof, phase):
    draw = ImageDraw.Draw(image)
    text(draw, 64, 152, "SECURITY SHOULD ARRIVE BEFORE THE DEPLOY.", 13, MINT, mono=True)
    text(draw, 58, 209, "Before the deploy.", 74, WHITE, bold=True)
    text(draw, 60, 296, "Beyond the diff.", 74, MINT, bold=True)
    text(draw, 64, 409, "Terraform + Kubernetes. Local AI. Human-controlled authority.", 22, MUTED)
    for i, (title, detail) in enumerate(
        [
            ("REVIEW", "Deterministic risk evidence"),
            ("EXPLAIN", "AI with read-only tools"),
            ("AUTHORIZE", "Signed, exact-artifact approval"),
        ]
    ):
        x = 64 + i * 384
        panel(draw, (x, 505, x + 360, 653))
        text(draw, x + 24, 531, f"0{i + 1}", 16, MINT, mono=True)
        text(draw, x + 24, 563, title, 26, WHITE, bold=True)
        text(draw, x + 24, 608, detail, 16, MUTED)


def scene_risk(image, proof, phase):
    draw = ImageDraw.Draw(image)
    text(draw, 64, 150, "01 / INFRASTRUCTURE REVIEW", 13, MINT, mono=True)
    text(draw, 61, 191, "A diff becomes evidence.", 52, WHITE, bold=True)
    for i, (label, title) in enumerate(
        [
            ("terraform-risky", "Terraform plan"),
            ("kubernetes-risky", "Kubernetes manifests"),
        ]
    ):
        run = next(r for r in proof["runs"] if r["label"] == label)
        report = proof["reports"][label]
        x = 64 + i * 588
        panel(draw, (x, 285, x + 564, 650))
        text(draw, x + 26, 310, title, 22, WHITE, bold=True)
        tag(draw, x + 354, 310, "REVIEW REQUIRED", AMBER)
        text(draw, x + 26, 350, f"{run['findings']:02d}", 70, AMBER, bold=True)
        text(draw, x + 124, 396, "findings with evidence", 18, MUTED)
        y = 459
        for finding in report["findings"][:2]:
            text(draw, x + 26, y, finding["rule_id"], 13, PURPLE, mono=True)
            label_text = {
                "TF-AWS-001": "Public SSH ingress",
                "TF-AWS-002": "Wildcard IAM permissions",
                "K8S-001": "Privileged container",
                "K8S-002": "Wildcard RBAC permissions",
            }[finding["rule_id"]]
            text(draw, x + 155, y - 2, label_text, 20)
            draw.line((x + 26, y + 40, x + 538, y + 40), fill=LINE)
            y += 69
        text(draw, x + 26, 620, f"SHA256 {run['source_digest'][:22]}…", 11, MUTED, mono=True)
    text(
        draw,
        64,
        681,
        "The rules establish findings. The model explains impact and remediation.",
        18,
        MUTED,
    )


def scene_agent(image, proof, phase):
    draw = ImageDraw.Draw(image)
    text(draw, 64, 150, "02 / BOUNDED AI AGENT", 13, MINT, mono=True)
    text(draw, 61, 191, "An agent with boundaries.", 52, WHITE, bold=True)
    run = next(r for r in proof["runs"] if r["label"] == "terraform-risky")
    panel(draw, (64, 285, 762, 675))
    text(draw, 90, 310, "ACTUAL AUDIT TRACE", 12, MUTED, mono=True)
    rows = [e for e in proof["audit"] if e["status"] == "succeeded"]
    for i, event in enumerate(rows):
        y = 367 + i * 82
        active = min(2, int(phase * 3.5)) >= i
        color = MINT if active else MUTED
        draw.ellipse((92, y + 7, 100, y + 15), fill=color)
        text(draw, 122, y, event["tool"], 23, WHITE if active else MUTED, mono=True)
        text(draw, 122, y + 34, f"{event['caller']} / allowed / succeeded", 15, color)
    text(draw, 90, 636, f"run {run['run_id'][:24]}…", 12, MUTED, mono=True)
    panel(draw, (790, 285, 1216, 470))
    text(draw, 816, 310, "MODEL CAPABILITY", 12, MUTED, mono=True)
    text(draw, 816, 348, "lookup_rules", 27, MINT, mono=True)
    text(draw, 816, 394, "Known rules. Read only. One call.", 18)
    panel(draw, (790, 491, 1216, 675))
    text(draw, 816, 518, "ADVERSARIAL TOOL PROBE", 12, MUTED, mono=True)
    text(draw, 816, 558, "simulate_deploy", 25, RED, mono=True)
    tag(draw, 816, 612, "DENIED BY DISPATCHER", RED)


def scene_approval(image, proof, phase):
    draw = ImageDraw.Draw(image)
    text(draw, 64, 150, "03 / APPROVAL ENFORCEMENT", 13, MINT, mono=True)
    text(draw, 61, 191, "No signature. No go.", 52, WHITE, bold=True)
    items = [
        ("Unsigned request", "unsigned_blocked", "BLOCKED", RED),
        ("Changed input", "changed_input_blocked", "BLOCKED", RED),
        ("Signed exact bundle", "signed_simulation_verified", "VERIFIED", MINT),
        ("Approval replay", "replay_blocked", "BLOCKED", RED),
    ]
    for i, (title, key, state, color) in enumerate(items):
        if proof["gate_checks"].get(key) is not True:
            raise ValueError("cannot render an unverified gate claim")
        x, y = 64 + (i % 2) * 588, 285 + (i // 2) * 165
        panel(draw, (x, y, x + 564, y + 141))
        text(draw, x + 26, y + 26, title, 23, WHITE, bold=True)
        tag(draw, x + 26, y + 81, state, color)
    text(draw, 64, 644, "Ed25519 signatures bind the input, report and audit bundle.", 21, WHITE)
    text(
        draw,
        64,
        681,
        "Automated demo signer — not a human approval. No infrastructure is deployed.",
        17,
        MUTED,
    )


def scene_result(image, proof, phase):
    draw = ImageDraw.Draw(image)
    text(draw, 64, 150, "04 / VERIFIED RELEASE CANDIDATE", 13, MINT, mono=True)
    text(draw, 59, 195, "AI explains.", 82, WHITE, bold=True)
    text(draw, 59, 286, "You authorize.", 82, MINT, bold=True)
    text(draw, 64, 405, "A practical security boundary, with proof you can inspect.", 24, MUTED)
    stats = [
        (str(len(proof["runs"])), "SCENARIOS VERIFIED"),
        (str(proof["tests_passed"]), "TESTS PASSED"),
        ("0", "INFRASTRUCTURE OPERATIONS"),
    ]
    for i, (value, label) in enumerate(stats):
        x = 64 + i * 384
        draw.line((x, 487, x + 340, 487), fill=LINE)
        text(draw, x, 508, value, 64, WHITE, bold=True)
        text(draw, x, 596, label, 12, MUTED, mono=True)
    tag(draw, 64, 657, "PYTHON / TERRAFORM / KUBERNETES / GITHUB ACTIONS", PURPLE)
    text(draw, 829, 666, "Remote CI pending publication", 16, MUTED)


SCENES = [scene_intro, scene_risk, scene_agent, scene_approval, scene_result]


def frame(proof, time):
    scene = min(4, int(time // 4))
    local = time - scene * 4
    image = BASE.copy()
    SCENES[scene](image, proof, min(1, local / 3))
    chrome(image, scene, time)
    # Crossfade at each cut; typography remains still and legible for the rest of the shot.
    if scene > 0 and local < 0.35:
        previous = BASE.copy()
        SCENES[scene - 1](previous, proof, 1)
        chrome(previous, scene - 1, time)
        blend = (1 - math.cos(math.pi * local / 0.35)) / 2
        image = Image.blend(previous, image, blend)
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = json.loads((args.evidence / "proof.json").read_text())
    if proof["provider"] != "ollama" or len(proof["runs"]) != 5:
        raise ValueError("movie requires verified real-inference evidence for all five scenarios")
    suites = ET.parse(args.junit).getroot().findall("testsuite")
    if not suites or any(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites):
        raise ValueError("passing test evidence required")
    proof["tests_passed"] = sum(int(s.get("tests", 0)) - int(s.get("skipped", 0)) for s in suites)
    proof["reports"] = {
        r["label"]: json.loads((args.evidence / r["run_dir"] / "report.json").read_text())
        for r in proof["runs"]
    }
    risky = next(r for r in proof["runs"] if r["label"] == "terraform-risky")
    proof["audit"] = [
        json.loads(line)
        for line in (args.evidence / risky["run_dir"] / "audit.jsonl").read_text().splitlines()
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to encode the demo")
    movie = args.output / "guard-demo.mp4"
    process = subprocess.Popen(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W}x{H}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(movie),
        ],
        stdin=subprocess.PIPE,
    )
    for index in range(22 * FPS):
        process.stdin.write(frame(proof, index / FPS).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("video encoder failed")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(movie),
            "-filter_complex",
            "fps=8,scale=960:-1:flags=lanczos,split[a][b];"
            "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a",
            "-loop",
            "0",
            str(args.output / "guard-demo.gif"),
        ],
        check=True,
    )
    frame(proof, 21).save(args.output / "guard-poster.png")
    frame(proof, 10.5).save(args.output / "guard-agent-trace.png")
    frame(proof, 14.5).save(args.output / "guard-approval.png")
    (args.output / "provenance.json").write_text(
        json.dumps(
            {
                "evidence": str(args.evidence),
                "tests_passed": proof["tests_passed"],
                "generated_at": proof["generated_at"],
                "rendering": "animated replay of actual run data",
                "not_a_screen_recording": True,
                "remote_ci_verified": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Rendered 22-second evidence replay: {movie}")


if __name__ == "__main__":
    main()
