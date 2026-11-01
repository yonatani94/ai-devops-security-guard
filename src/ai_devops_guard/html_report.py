"""An offline, script-free review surface derived only from validated run data."""
# ruff: noqa: E501

from html import escape

from ai_devops_guard.models import Assessment, AuditEvent

STYLE = """
:root{color-scheme:dark;--bg:#0b0d14;--panel:#121621;--line:#252b3b;--text:#eef0fa;
--muted:#a0a9c0;--mint:#79f4bd;--amber:#f3c16d;--purple:#b3a1ff;--red:#ff8799}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:auto;padding:32px 40px 70px}a{color:var(--mint)}
header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);
padding-bottom:25px;gap:16px;flex-wrap:wrap}.brand{font-weight:800;letter-spacing:4px;font-size:23px}
.mark{display:inline-grid;place-items:center;color:var(--bg);background:var(--mint);width:33px;
height:36px;clip-path:polygon(0 0,100% 0,100% 65%,50% 100%,0 65%);margin-right:12px}
.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.hero{padding:52px 0 34px;display:grid;grid-template-columns:1fr auto;align-items:end;gap:30px}
h1{font-size:clamp(36px,6vw,64px);line-height:1.08;letter-spacing:-2px;margin:10px 0 20px}
h2{font-size:22px;letter-spacing:-.5px;margin:0}h3{font-size:17px;margin:0 0 8px}
p{margin:0 0 15px}.muted{color:var(--muted)}.pill{border:1px solid var(--line);border-radius:99px;
padding:7px 13px;display:inline-block;font-size:12px}.decision{color:var(--amber);border-color:#654e2d}
.decision.pass{color:var(--mint);border-color:#285541}.decision.error{color:var(--red);border-color:#60323d}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:14px;
overflow:hidden;margin-bottom:38px}.stat{padding:22px;border-right:1px solid var(--line);min-width:0}
.stat:last-child{border:0}.stat b{display:block;font-size:29px;font-weight:600;letter-spacing:-1px}
.grid{display:grid;grid-template-columns:1.5fr 1fr;gap:24px}section{margin-bottom:24px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:24px}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.finding{padding:22px 0;border-top:1px solid var(--line);margin-top:20px}
.finding:last-child{padding-bottom:0}.tag{color:var(--amber);text-transform:uppercase;font-size:11px;
letter-spacing:1.5px}.critical{color:var(--red)}code{font-family:ui-monospace,monospace;
font-size:12px;overflow-wrap:anywhere;color:var(--purple)}details{margin-top:15px}summary{cursor:pointer;
color:var(--mint)}.path{padding:12px;background:var(--bg);border-radius:6px;margin:10px 0}
.note{border-left:2px solid var(--mint);padding-left:16px;margin-top:20px}
.event{display:grid;grid-template-columns:12px 1fr;gap:14px;padding:15px 0;border-bottom:1px solid var(--line)}
.dot{background:var(--mint);width:7px;height:7px;border-radius:50%;margin-top:8px}
.event small{display:block;color:var(--muted)}.event code{color:var(--text)}
footer{border-top:1px solid var(--line);padding-top:22px;display:flex;justify-content:space-between;
gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.full{overflow-wrap:anywhere}
nav{display:flex;gap:18px;flex-wrap:wrap}a:focus-visible,summary:focus-visible{outline:2px solid var(--mint);
outline-offset:5px}.safe{color:var(--mint)}@media(max-width:760px){main{padding:24px 20px}
.grid,.hero{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}
.stat:nth-child(2){border:0}.hero{padding-top:30px}.panel{padding:20px}}
"""


def render_html(assessment: Assessment, events: list[AuditEvent]) -> str:
    findings = []
    for finding in assessment.findings:
        findings.append(f"""<article class="finding">
<div class="row"><span class="tag {finding.severity}">{escape(finding.severity)} severity</span>
<code>{escape(finding.rule_id)}</code></div>
<h3>{escape(finding.summary)}</h3><code>{escape(finding.resource_address)}</code>
<details><summary>Inspect evidence &amp; remediation</summary>
<div class="path"><code>{escape(finding.evidence_path)}</code></div>
<p>{escape(finding.remediation)}</p></details></article>""")
    if not findings:
        findings.append(
            '<p class="note">No findings recorded. Review coverage before proceeding.</p>'
        )
    completed = [e for e in events if e.status in {"succeeded", "failed", "denied"}]
    model_calls = sum(e.caller == "model" for e in completed)
    explanation_event = next((e for e in completed if e.tool == "explain_assessment"), None)
    duration = (
        f"{explanation_event.duration_ms / 1000:.2f}s"
        if explanation_event and explanation_event.duration_ms is not None
        else "—"
    )
    timeline = []
    for event in completed:
        args = escape(str(event.sanitized_arguments))
        timeline.append(f"""<div class="event"><span class="dot"></span><div>
<code>{escape(event.tool)}</code><small>{event.caller} · {event.status} · {event.permission}</small>
<details><summary>Inspect call</summary><code>{event.call_id}</code><br>
<code>{args}</code><small>Output SHA256</small><code>{event.output_digest or "—"}</code>
</details></div></div>""")
    gaps = (
        "".join(f"<li>{escape(gap)}</li>" for gap in assessment.coverage_gaps)
        or "<li>No gaps within the supported rules. This is not a comprehensive security scan.</li>"
    )
    ai_label = (
        "LOCAL INFERENCE" if assessment.ai_status == "complete" else assessment.ai_status.upper()
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>GUARD · Infrastructure review {assessment.run_id}</title><style>{STYLE}</style></head>
<body><main><header><div class="brand"><span class="mark">G</span>GUARD</div>
<nav aria-label="Report navigation"><a href="#findings">Findings</a><a href="#agent">Agent trace</a>
<a href="report.json">JSON report</a></nav></header>
<div class="hero"><div><div class="eyebrow">AI DevOps Security Guard / {assessment.input_kind}</div>
<h1>Review the risk.<br>Own the decision.</h1><p class="muted">Evidence before deployment. Authority stays with you.</p>
</div><span class="pill decision {assessment.decision}">{assessment.decision.upper().replace("_", " ")}</span></div>
<div class="stats"><div class="stat"><span class="eyebrow">Findings</span><b>{len(assessment.findings):02d}</b></div>
<div class="stat"><span class="eyebrow">Coverage gaps</span><b>{len(assessment.coverage_gaps):02d}</b></div>
<div class="stat"><span class="eyebrow">Model tool calls</span><b>{model_calls:02d}</b></div>
<div class="stat"><span class="eyebrow">AI duration</span><b>{duration}</b></div></div>
<div class="grid"><div><section class="panel" id="findings"><div class="row"><h2>Security findings</h2>
<span class="pill">Deterministic rules</span></div>{"".join(findings)}</section>
<section class="panel"><div class="row"><h2>AI analyst notes</h2><span class="pill">{ai_label}</span></div>
<p class="muted">{escape(assessment.ai_provider or "legacy snapshot")} · {escape(assessment.ai_model or "Fake provider · no model inference")}</p>
<p class="note">{escape(assessment.ai_explanation or "Explanation unavailable.")}</p>
<p class="muted">Advisory text. Rule severities and policy decisions remain authoritative.</p></section></div>
<div><section class="panel" id="agent"><div class="eyebrow">Every capability is accountable</div>
<h2>Agent trace</h2>{"".join(timeline)}<p><a href="audit.jsonl">Open full audit log</a></p></section>
<section class="panel"><h2>Approval boundary</h2><p class="note">This report does not authorize deployment.</p>
<p class="muted">The local simulation requires a signed, unexpired approval of the exact input,
report and audit bundle. The AI has no signing or deployment tool.</p></section></div></div>
<section class="panel"><h2>Coverage &amp; provenance</h2><ul>{gaps}</ul>
<p class="eyebrow">Input SHA256</p><code class="full">{assessment.source_digest or "Unavailable"}</code></section>
<footer><span>Run {assessment.run_id}</span><span>Read only · no infrastructure operations · offline report</span></footer>
</main></body></html>"""
