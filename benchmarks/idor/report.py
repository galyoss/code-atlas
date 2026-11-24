"""Render benchmark run reports as one HTML page.

    python benchmarks/idor/report.py .work/idor-benchmark/reports/<run>.json [<other run>.json ...] -o report.html

The first report is shown in full: summary, where vulnerable routes were lost, each
repository, and every advisory route with its votes. Further reports appear in the
model comparison. Repository text in vote reasons is escaped.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path

CASES = Path(__file__).with_name("cases.json")
# USD per 1M tokens: input, cached input, output. OpenAI list prices.
PRICES = {
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
}
_GATE_WORDS = ("Slice coverage", "unresolved call", "did not cite", "snippet this check needs", "snippet with a range")
_FAILURE_WORDS = ("timed out", "call failed", "did not return", "different route", "unknown verdict", "key is not configured")

OUTCOMES = {
    "tp": ("Found", "Vulnerable route with a finding"),
    "fn": ("Missed", "Vulnerable route without a finding"),
    "fp": ("False alarm", "Fixed route with a finding"),
    "tn": ("Clean", "Fixed route without a finding"),
    "skip": ("Not scored", "Route not in the graph or not reviewed"),
}

# Why a vulnerable route has no finding, in pipeline order.
CAUSES = {
    "not_found": "Route not in the graph",
    "no_access": "No data access recorded",
    "gate": "Scanner evidence blocks a present vote",
    "failed": "Model call failed (not scored)",
    "downgraded": "Model said present; the runner downgraded it",
    "split": "Agents split; below the agreement threshold",
    "inconclusive": "Model said inconclusive",
    "absent": "Model said absent",
    "not_reviewed": "Not reviewed (out of credit)",
}


def cost(model: str | None, usage: dict | None) -> float | None:
    if not usage or model not in PRICES:
        return None
    fresh, cached, out = PRICES[model]
    prompt, hit = usage["promptTokens"], usage["cachedPromptTokens"]
    return ((prompt - hit) * fresh + hit * cached + usage["completionTokens"] * out) / 1e6


def votes_of(row: dict) -> list[dict]:
    return [vote for match in row.get("matches", []) for vote in match.get("votes", [])]


def classify(row: dict, threshold: int) -> tuple[str, str | None]:
    """The outcome and, for a missed vulnerable route, why."""
    if not row["found"]:
        return ("skip", "not_found") if not row["vulnerable"] else ("fn", "not_found")
    if "notReviewed" in row:
        return "skip", "not_reviewed"
    if "finding" not in row:
        return "skip", None
    if not row["vulnerable"]:
        return ("fp" if row["finding"] else "tn"), None
    if row["finding"]:
        return "tp", None
    matches = row["matches"]
    if all(match["accesses"] == 0 for match in matches):
        return "fn", "no_access"
    if not any(match["eligible"] for match in matches):
        return "fn", "gate"
    votes = votes_of(row)
    reasons = [vote.get("reason", "") for vote in votes]
    if votes and all(any(word in reason for word in _FAILURE_WORDS) for reason in reasons):
        # A call that never returned a verdict is not a model miss.
        return "skip", "failed"
    if any(vote["verdict"] == "present" for vote in votes):
        return "fn", "split"
    if any(any(word in reason for word in _GATE_WORDS) for reason in reasons):
        return "fn", "downgraded"
    if any(vote["verdict"] == "inconclusive" for vote in votes):
        return "fn", "inconclusive"
    return "fn", "absent"


def repository(target: str, cases: dict) -> str:
    for item in cases["targets"]:
        if item["id"] == target:
            return item["repository"].rstrip("/").split("/")[-1]
    return target


def metrics(rows: list[dict], threshold: int) -> dict:
    counts = Counter(classify(row, threshold)[0] for row in rows)
    tp, fn, fp, tn = counts["tp"], counts["fn"], counts["fp"], counts["tn"]
    recall = tp / (tp + fn) if tp + fn else None
    precision = tp / (tp + fp) if tp + fp else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "skip": counts["skip"], "recall": recall, "precision": precision, "f1": f1}


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def render(reports: list[dict], cases: dict, notes: list[str] | None = None) -> str:
    main = reports[0]
    threshold = main.get("threshold", 2)
    rows = main["rows"]
    scored = [row for row in rows if "finding" in row or not row["found"] or "notReviewed" in row]
    no_gaps = [row for row in scored if not row["gap"]]
    every, clean = metrics(scored, threshold), metrics(no_gaps, threshold)
    spend = cost(main.get("model"), main.get("usage"))
    usage = main.get("usage") or {}
    advisories = {item["id"]: item for item in cases["advisories"]}

    parts = [_HEAD]
    parts.append('<header class="masthead"><div class="wrap">')
    parts.append('<p class="eyebrow">CodeAtlas · IDOR review benchmark</p>')
    parts.append(f'<h1>{every["tp"]} of {every["tp"] + every["fn"]} vulnerable routes found, {every["fp"]} false alarms</h1>')
    parts.append(
        f'<p class="lede">{len({row["advisory"] for row in rows})} published advisories across '
        f'{len({repository(row["target"], cases) for row in rows})} repositories, each checked on the vulnerable and the fixed '
        f'revision. Model <code>{esc(main.get("model"))}</code>, {main.get("agents")} agents (hunter and skeptic), '
        f'agreement threshold {threshold}. Scanner <code>{esc(main.get("scannerFingerprint"))}</code>, run '
        f'{esc(main.get("generatedAt", "")[:16].replace("T", " "))} UTC.</p>'
    )
    parts.append("</div></header>")

    parts.append('<main class="wrap">')
    # Summary
    parts.append('<section aria-labelledby="summary"><h2 id="summary">Summary</h2><div class="tiles">')
    for label, value, note in (
        ("Recall", pct(every["recall"]), f'{every["tp"]} of {every["tp"] + every["fn"]} vulnerable routes'),
        ("Precision", pct(every["precision"]), f'{every["fp"]} findings on fixed routes'),
        ("F1", "n/a" if every["f1"] is None else f'{every["f1"]:.2f}', "harmonic mean"),
        ("Recall without known gaps", pct(clean["recall"]), f'{clean["tp"]} of {clean["tp"] + clean["fn"]}'),
        ("Cost of this run", "n/a" if spend is None else f"${spend:,.2f}",
         f'{usage.get("calls", 0)} calls · {usage.get("promptTokens", 0) / 1e6:.1f}M input tokens'),
    ):
        parts.append(f'<div class="tile"><span class="tile-label">{label}</span><span class="tile-value">{value}</span>'
                     f'<span class="tile-note">{esc(note)}</span></div>')
    parts.append("</div>")
    parts.append('<div class="confusion" role="table" aria-label="Confusion matrix">'
                 '<div role="row" class="cm-head"><span role="columnheader"></span><span role="columnheader">Finding</span>'
                 '<span role="columnheader">No finding</span></div>'
                 f'<div role="row"><span role="rowheader">Vulnerable revision</span><span class="cm tp">{every["tp"]}<small>true positives</small></span>'
                 f'<span class="cm fn">{every["fn"]}<small>false negatives</small></span></div>'
                 f'<div role="row"><span role="rowheader">Fixed revision</span><span class="cm fp">{every["fp"]}<small>false positives</small></span>'
                 f'<span class="cm tn">{every["tn"]}<small>true negatives</small></span></div></div>')
    if usage.get("quotaExhausted"):
        parts.append(f'<p class="warn">The account ran out of credit during the run. {every["skip"]} routes were not reviewed and are left out of the metrics.</p>')
    parts.append("</section>")

    if notes:
        # Plain-text paragraphs written after reading the votes; escaped like everything else.
        parts.append('<section aria-labelledby="analysis"><h2 id="analysis">Analysis</h2><div class="analysis">')
        parts.extend(f"<p>{esc(paragraph)}</p>" for paragraph in notes)
        parts.append("</div></section>")

    # Funnel
    positives = [row for row in rows if row["vulnerable"]]
    causes = Counter(classify(row, threshold)[1] for row in positives if classify(row, threshold)[0] == "fn")
    parts.append('<section aria-labelledby="funnel"><h2 id="funnel">Where vulnerable routes were lost</h2>'
                 f'<p class="section-note">All {len(positives)} vulnerable advisory routes, in pipeline order. '
                 'Scanner stages decide whether a vote can count at all; model stages decide the vote.</p><div class="funnel">')
    total = max(len(positives), 1)
    found = sum(classify(row, threshold)[0] == "tp" for row in positives)
    for key in ("tp", *CAUSES):
        count = found if key == "tp" else causes.get(key, 0)
        if key != "tp" and not count:
            continue
        label = "Found" if key == "tp" else CAUSES[key]
        stage = "found" if key == "tp" else ("scanner" if key in {"not_found", "no_access", "gate"} else "model")
        parts.append(f'<div class="bar-row"><span class="bar-label">{esc(label)}<em>{stage}</em></span>'
                     f'<span class="bar-track"><span class="bar {stage}" style="width:{count / total * 100:.1f}%"></span></span>'
                     f'<span class="bar-count">{count}</span></div>')
    parts.append("</div></section>")

    # Per repository
    parts.append('<section aria-labelledby="repos"><h2 id="repos">By repository</h2><div class="scroll"><table class="grid">'
                 '<thead><tr><th>Repository</th><th>Vulnerable routes</th><th>Found</th><th>Missed</th>'
                 '<th>Fixed routes</th><th>False alarms</th><th>Recall</th><th>Known gaps</th></tr></thead><tbody>')
    for name in dict.fromkeys(repository(row["target"], cases) for row in rows):
        group = [row for row in scored if repository(row["target"], cases) == name]
        result = metrics(group, threshold)
        gaps = sum(row["gap"] for row in group if row["vulnerable"])
        parts.append(f'<tr><th scope="row">{esc(name)}</th><td>{result["tp"] + result["fn"]}</td><td>{result["tp"]}</td>'
                     f'<td>{result["fn"]}</td><td>{result["fp"] + result["tn"]}</td><td>{result["fp"]}</td>'
                     f'<td>{pct(result["recall"])}</td><td>{gaps or ""}</td></tr>')
    parts.append("</tbody></table></div></section>")

    # Model comparison
    if len(reports) > 1:
        def key(row):
            return row["target"], row["advisory"], row["route"]

        def judged(report):
            return {key(row) for row in report["rows"] if classify(row, report.get("threshold", 2))[0] != "skip"}

        common = set.intersection(*(judged(report) for report in reports))
        parts.append('<section aria-labelledby="models-common"><h2 id="models-common">Models on the same routes</h2>'
                     f'<p class="section-note">Only the {len(common)} routes every run reviewed, so the runs compare like for like.</p>'
                     '<div class="scroll"><table class="grid"><thead><tr><th>Model</th><th>Recall</th><th>Precision</th>'
                     '<th>TP</th><th>FN</th><th>FP</th><th>TN</th></tr></thead><tbody>')
        for report in reports:
            same = metrics([row for row in report["rows"] if key(row) in common], report.get("threshold", 2))
            parts.append(f'<tr><th scope="row"><code>{esc(report.get("model"))}</code></th><td>{pct(same["recall"])}</td>'
                         f'<td>{pct(same["precision"])}</td><td>{same["tp"]}</td><td>{same["fn"]}</td><td>{same["fp"]}</td>'
                         f'<td>{same["tn"]}</td></tr>')
        parts.append("</tbody></table></div></section>")
        parts.append('<section aria-labelledby="models"><h2 id="models">Each run in full</h2><div class="scroll"><table class="grid">'
                     '<thead><tr><th>Model</th><th>Recall</th><th>Precision</th><th>F1</th><th>TP</th><th>FN</th><th>FP</th>'
                     '<th>Recall without gaps</th><th>Calls</th><th>Input tokens</th><th>Cost</th></tr></thead><tbody>')
        for report in reports:
            got = [row for row in report["rows"] if "finding" in row or not row["found"] or "notReviewed" in row]
            result = metrics(got, report.get("threshold", 2))
            without = metrics([row for row in got if not row["gap"]], report.get("threshold", 2))
            spent = cost(report.get("model"), report.get("usage"))
            used = report.get("usage") or {}
            f1 = "n/a" if result["f1"] is None else f'{result["f1"]:.2f}'
            parts.append(f'<tr><th scope="row"><code>{esc(report.get("model"))}</code></th><td>{pct(result["recall"])}</td>'
                         f'<td>{pct(result["precision"])}</td><td>{f1}</td>'
                         f'<td>{result["tp"]}</td><td>{result["fn"]}</td><td>{result["fp"]}</td><td>{pct(without["recall"])}</td>'
                         f'<td>{used.get("calls", 0)}</td><td>{used.get("promptTokens", 0) / 1e6:.1f}M</td>'
                         f'<td>{"n/a" if spent is None else f"${spent:,.2f}"}</td></tr>')
        parts.append("</tbody></table></div></section>")

    # Every route
    parts.append('<section aria-labelledby="routes"><h2 id="routes">Every advisory route</h2>'
                 '<div class="filters" role="group" aria-label="Filter routes">'
                 '<button type="button" class="chip" data-filter="all" aria-pressed="true">All</button>')
    for key, (label, _title) in OUTCOMES.items():
        parts.append(f'<button type="button" class="chip" data-filter="{key}" aria-pressed="false">{label}</button>')
    parts.append("</div>")
    for advisory_id in dict.fromkeys(row["advisory"] for row in rows):
        advisory = advisories.get(advisory_id, {})
        group = [row for row in rows if row["advisory"] == advisory_id]
        gap = advisory.get("gap")
        parts.append(f'<article class="advisory"><header><h3><a href="https://github.com/advisories/{esc(advisory_id)}">{esc(advisory_id)}</a></h3>'
                     f'<p>{esc(advisory.get("title", ""))}</p>' + (f'<p class="gap">Known gap: {esc(gap)}</p>' if gap else "") + "</header>")
        for row in group:
            outcome, cause = classify(row, threshold)
            label, title = OUTCOMES[outcome]
            parts.append(f'<details class="route" data-outcome="{outcome}"><summary>'
                         f'<span class="pill {outcome}" title="{esc(title)}">{label}</span>'
                         f'<span class="rev {"vuln" if row["vulnerable"] else "fixed"}">{"vulnerable" if row["vulnerable"] else "fixed"}</span>'
                         f'<code class="target">{esc(row["target"])}</code><code class="path">{esc(row["route"])}</code>'
                         + (f'<span class="cause">{esc(CAUSES[cause])}</span>' if cause else "") + "</summary>")
            if not row["found"]:
                parts.append('<p class="detail">The scanner did not discover this route.</p></details>')
                continue
            for match in row["matches"]:
                coverage = match.get("coverage") or {}
                parts.append(f'<div class="match"><p class="meta"><code>{esc(match.get("path"))}</code> · '
                             f'{match["accesses"]} data accesses, {len(match["eligible"])} could carry a present vote · '
                             f'coverage {esc(coverage.get("callGraph", "?"))} · ~{match["promptChars"] // 4000}k tokens per call</p>')
                for reason, count in (match.get("blockers") or {}).items():
                    parts.append(f'<p class="blocker">Blocked {count}×: {esc(reason)}</p>')
                for vote in match.get("votes", []):
                    cited = f' · cites <code>{esc(vote["dataAccessId"])}</code>' if vote.get("dataAccessId") else ""
                    parts.append(f'<div class="vote"><span class="role">{esc(vote["role"])}</span>'
                                 f'<span class="verdict {esc(vote["verdict"])}">{esc(vote["verdict"])}</span>'
                                 f'<p>{esc(vote.get("reason", ""))}{cited}</p></div>')
                parts.append("</div>")
            parts.append("</details>")
        parts.append("</article>")
    parts.append("</section>")

    # Method
    parts.append('<section aria-labelledby="method"><h2 id="method">How to read this</h2><ul class="notes">'
                 '<li>A vulnerable route counts as found when hunter and skeptic votes reach the agreement threshold on that route. '
                 'A finding on the same route in the fixed revision is a false alarm.</li>'
                 '<li>Precision covers only the advisory routes on their fixed revisions. It is not a false-positive rate for the other routes in these repositories.</li>'
                 '<li>Known gaps are cases the scanner does not model yet (file or vector storage, Django ORM, a Rails app loaded through its gemspec). They are counted in the headline and shown separately.</li>'
                 '<li>This is a single run per model. Model votes vary between runs, so small differences are within noise.</li>'
                 f'<li>Cost uses OpenAI list prices per 1M tokens and the token counts the API returned.</li>'
                 "</ul></section></main>")
    parts.append(_SCRIPT)
    return "\n".join(parts)


_HEAD = """<title>CodeAtlas IDOR Benchmark</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Layout: an audit ledger. Summary first, then the loss funnel, then every case as an expandable line. */
:root {
  --bg: #f5f7f8; --surface: #ffffff; --ink: #14202a; --muted: #5a6b78; --rule: #d7dee3; --accent: #1f5f7a;
  --tp: #1d7a4d; --tp-bg: #e3f3ea; --fn: #b2541a; --fn-bg: #fbeadf; --fp: #b3263a; --fp-bg: #f9e1e5;
  --tn: #51606c; --tn-bg: #e8edf0; --scanner: #8a6f2e; --model: #1f5f7a;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f161b; --surface: #16212a; --ink: #e4ebf0; --muted: #93a4b1; --rule: #2a3843; --accent: #6db3d1;
  --tp: #5fcf93; --tp-bg: #173a29; --fn: #f0a26b; --fn-bg: #43291a; --fp: #f07a8c; --fp-bg: #46202a;
  --tn: #a7b5c0; --tn-bg: #22303a; --scanner: #d6b768; --model: #6db3d1; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0f161b; --surface: #16212a; --ink: #e4ebf0; --muted: #93a4b1; --rule: #2a3843; --accent: #6db3d1;
  --tp: #5fcf93; --tp-bg: #173a29; --fn: #f0a26b; --fn-bg: #43291a; --fp: #f07a8c; --fp-bg: #46202a;
  --tn: #a7b5c0; --tn-bg: #22303a; --scanner: #d6b768; --model: #6db3d1; color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 400 1rem/1.55 var(--body); }
.wrap { max-width: 72rem; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.masthead { border-bottom: 1px solid var(--rule); background: var(--surface); }
.masthead .wrap { padding-block: 2.25rem 2rem; display: grid; gap: .6rem; }
.eyebrow { margin: 0; font: 600 .78rem/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { margin: 0; font: 800 clamp(1.7rem, 4vw, 2.6rem)/1.1 var(--display); letter-spacing: -.01em; text-wrap: balance; }
.lede { margin: 0; max-width: 65ch; color: var(--muted); }
main.wrap { padding-block: 1.5rem 4rem; display: grid; gap: 2.75rem; }
h2 { margin: 0 0 1rem; font: 700 1.3rem/1.2 var(--display); text-wrap: balance; }
h3 { margin: 0; font: 700 1rem/1.3 var(--display); }
h3 a { color: var(--accent); text-decoration: none; } h3 a:hover { text-decoration: underline; }
code { font-family: var(--mono); font-size: .85em; }
.section-note { margin: -.5rem 0 1rem; color: var(--muted); max-width: 65ch; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .75rem; }
.tile { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; padding: 1rem; display: grid; gap: .25rem; }
.tile-label { font: 600 .75rem/1.2 var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.tile-value { font: 800 2rem/1 var(--display); font-variant-numeric: tabular-nums; }
.tile-note { color: var(--muted); font-size: .88rem; }
.confusion { margin-top: 1rem; display: grid; gap: .4rem; max-width: 36rem; }
.confusion [role=row] { display: grid; grid-template-columns: 9.5rem 1fr 1fr; gap: .4rem; align-items: stretch; }
.cm-head span { font: 600 .75rem/1 var(--mono); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); padding: .25rem; }
[role=rowheader] { font-weight: 600; align-self: center; }
.cm { display: grid; padding: .6rem .75rem; border-radius: 6px; font: 800 1.5rem/1.1 var(--display); font-variant-numeric: tabular-nums; }
.cm small { font: 400 .78rem/1.2 var(--body); }
.cm.tp, .pill.tp { background: var(--tp-bg); color: var(--tp); } .cm.fn, .pill.fn { background: var(--fn-bg); color: var(--fn); }
.cm.fp, .pill.fp { background: var(--fp-bg); color: var(--fp); } .cm.tn, .pill.tn { background: var(--tn-bg); color: var(--tn); }
.pill.skip { background: var(--tn-bg); color: var(--muted); }
.warn { margin: 1rem 0 0; padding: .75rem 1rem; border-radius: 6px; background: var(--fn-bg); color: var(--fn); }
.funnel { display: grid; gap: .55rem; }
.bar-row { display: grid; grid-template-columns: minmax(10rem, 22rem) 1fr 2.5rem; gap: .75rem; align-items: center; }
.bar-label { font-size: .95rem; } .bar-label em { margin-left: .5rem; font: 600 .7rem/1 var(--mono); font-style: normal; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.bar-track { height: .9rem; background: var(--tn-bg); border-radius: 3px; overflow: hidden; }
.bar { display: block; height: 100%; border-radius: 3px; } .bar.found { background: var(--tp); } .bar.scanner { background: var(--scanner); } .bar.model { background: var(--model); }
.bar-count { font: 600 .95rem/1 var(--mono); font-variant-numeric: tabular-nums; text-align: right; }
.scroll { overflow-x: auto; }
table.grid { border-collapse: collapse; width: 100%; background: var(--surface); font-variant-numeric: tabular-nums; }
.grid th, .grid td { padding: .55rem .75rem; border-bottom: 1px solid var(--rule); text-align: right; white-space: nowrap; }
.grid th:first-child { text-align: left; } .grid thead th { font: 600 .74rem/1.2 var(--mono); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.filters { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1rem; }
.chip { font: 600 .85rem/1 var(--body); padding: .5rem .8rem; border-radius: 999px; border: 1px solid var(--rule); background: var(--surface); color: var(--ink); cursor: pointer; }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--surface); }
.chip:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.advisory { border-top: 1px solid var(--rule); padding-block: 1rem; display: grid; gap: .5rem; }
.advisory header { display: grid; gap: .2rem; } .advisory header p { margin: 0; color: var(--muted); max-width: 70ch; }
.advisory .gap { color: var(--scanner); font-size: .9rem; }
.route { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; min-width: 0; }
.route summary { cursor: pointer; display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem; padding: .6rem .8rem; }
.pill, .rev { font: 600 .72rem/1 var(--mono); text-transform: uppercase; letter-spacing: .05em; padding: .3rem .5rem; border-radius: 4px; }
.rev { color: var(--muted); border: 1px solid var(--rule); }
.target { color: var(--muted); } .path { font-weight: 600; overflow-wrap: anywhere; }
.cause { color: var(--muted); font-size: .88rem; }
.detail, .match { padding: 0 .8rem .8rem; margin: 0; }
.match { display: grid; gap: .5rem; border-top: 1px dashed var(--rule); padding-top: .7rem; }
.meta, .blocker { margin: 0; color: var(--muted); font-size: .88rem; overflow-wrap: anywhere; }
.blocker { color: var(--scanner); }
.vote { display: grid; grid-template-columns: 4.5rem 6.5rem 1fr; gap: .5rem; align-items: baseline; }
.vote p { margin: 0; min-width: 0; overflow-wrap: anywhere; font-size: .92rem; }
.role { font: 600 .75rem/1 var(--mono); text-transform: uppercase; color: var(--muted); }
.verdict { font: 600 .78rem/1 var(--mono); } .verdict.present { color: var(--fp); } .verdict.absent { color: var(--tp); } .verdict.inconclusive { color: var(--muted); }
.analysis { display: grid; gap: .75rem; max-width: 70ch; } .analysis p { margin: 0; }
.notes { margin: 0; padding-left: 1.2rem; display: grid; gap: .5rem; max-width: 70ch; color: var(--muted); }
@media (max-width: 40rem) {
  .bar-row { grid-template-columns: 1fr 2.5rem; } .bar-track { grid-column: 1 / -1; grid-row: 2; }
  .vote { grid-template-columns: 4.5rem 1fr; } .vote p { grid-column: 1 / -1; }
  .confusion [role=row] { grid-template-columns: 6.5rem 1fr 1fr; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>"""

_SCRIPT = """<script>
document.querySelectorAll('.chip').forEach(function (chip) {
  chip.addEventListener('click', function () {
    var want = chip.dataset.filter;
    document.querySelectorAll('.chip').forEach(function (other) { other.setAttribute('aria-pressed', String(other === chip)); });
    document.querySelectorAll('.route').forEach(function (route) { route.hidden = want !== 'all' && route.dataset.outcome !== want; });
    document.querySelectorAll('.advisory').forEach(function (block) {
      block.hidden = !block.querySelector('.route:not([hidden])');
    });
  });
});
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--notes", type=Path, help="plain-text analysis; paragraphs separated by blank lines")
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    notes = None
    if args.notes:
        notes = [block.strip() for block in args.notes.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    args.output.write_text(render(reports, cases, notes), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
