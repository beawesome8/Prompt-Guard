"""
Generates an HTML report and a Markdown PR comment from a completed eval run.
Reads results from SQLite by run_id and produces two output files in storage/artifacts/.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage.init_db import DB_PATH

ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "artifacts")


def fetch_run_results(run_id: str) -> dict:
    """Fetches all baseline and candidate results for a given run_id from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM eval_runs WHERE run_id = ? ORDER BY run_type, case_id
    """, (run_id,))
    rows = cursor.fetchall()
    conn.close()

    baseline = [dict(r) for r in rows if r["run_type"] == "baseline"]
    candidate = [dict(r) for r in rows if r["run_type"] == "candidate"]

    return {"baseline": baseline, "candidate": candidate}


def compute_metrics(results: list) -> dict:
    """Computes aggregate metrics from a list of result rows."""
    total = len(results)
    if total == 0:
        return {}
    valid = sum(r["schema_valid"] for r in results)
    sentiment = sum(r["sentiment_correct"] or 0 for r in results)
    urgency = sum(r["urgency_correct"] or 0 for r in results)
    avg_latency = sum(r["latency_ms"] or 0 for r in results) / total
    total_cost = sum(r["cost_usd"] or 0 for r in results)
    return {
        "schema_valid_pct": round(valid / total * 100, 1),
        "sentiment_acc_pct": round(sentiment / total * 100, 1),
        "urgency_acc_pct": round(urgency / total * 100, 1),
        "avg_latency_ms": round(avg_latency, 1),
        "total_cost_usd": round(total_cost, 6),
        "total_cases": total,
    }


def get_decision(b: dict, c: dict) -> tuple[str, list]:
    """Returns the gate decision and a list of flagged metrics."""
    flags = []
    decision = "PASSED"

    checks = [
        ("Schema Validity", "schema_valid_pct", -2.0, -5.0, "%"),
        ("Sentiment Accuracy", "sentiment_acc_pct", -2.0, -5.0, "%"),
        ("Urgency Accuracy", "urgency_acc_pct", -2.0, -5.0, "%"),
    ]

    for label, key, warn_threshold, block_threshold, unit in checks:
        delta = round(c[key] - b[key], 1)
        sign = "+" if delta >= 0 else ""
        if delta <= block_threshold:
            flags.append({"metric": label, "delta": f"{sign}{delta}{unit}", "status": "BLOCK"})
            decision = "BLOCKED"
        elif delta <= warn_threshold:
            flags.append({"metric": label, "delta": f"{sign}{delta}{unit}", "status": "WARN"})
            if decision != "BLOCKED":
                decision = "WARNING"

    return decision, flags


def find_regressions(baseline: list, candidate: list) -> list:
    """Finds individual cases that regressed between baseline and candidate."""
    baseline_map = {r["case_id"]: r for r in baseline}
    candidate_map = {r["case_id"]: r for r in candidate}
    regressions = []

    for case_id, b in baseline_map.items():
        c = candidate_map.get(case_id)
        if not c:
            continue
        issues = []
        if b["schema_valid"] and not c["schema_valid"]:
            issues.append("schema broke")
        if b["sentiment_correct"] and not c["sentiment_correct"]:
            issues.append(f"sentiment: expected {b['parsed_sentiment']} got {c['parsed_sentiment']}")
        if b["urgency_correct"] and not c["urgency_correct"]:
            issues.append(f"urgency: expected {b['parsed_urgency']} got {c['parsed_urgency']}")
        if issues:
            regressions.append({"case_id": case_id, "issues": issues})

    return regressions[:5]


def generate_markdown_comment(run_id: str, b_metrics: dict, c_metrics: dict,
                               decision: str, flags: list, regressions: list) -> str:
    """Generates a Markdown string formatted as a GitHub PR comment."""
    lines = [
        "## PromptGuard Report",
        "",
        f"**Run ID:** `{run_id}`  ",
        f"**Decision:** `{decision}`",
        "",
        "| Metric | Baseline | Candidate | Delta | Status |",
        "|---|---|---|---|---|",
    ]

    rows = [
        ("Schema Validity", "schema_valid_pct", "%"),
        ("Sentiment Accuracy", "sentiment_acc_pct", "%"),
        ("Urgency Accuracy", "urgency_acc_pct", "%"),
        ("Avg Latency (ms)", "avg_latency_ms", "ms"),
        ("Total Cost (USD)", "total_cost_usd", "$"),
    ]

    flag_map = {f["metric"]: f["status"] for f in flags}

    for label, key, unit in rows:
        b_val = b_metrics[key]
        c_val = c_metrics[key]
        delta = round(c_val - b_val, 2)
        sign = "+" if delta >= 0 else ""
        status = flag_map.get(label, "PASS")
        if unit == "$":
            lines.append(f"| {label} | ${b_val} | ${c_val} | {sign}{delta} | {status} |")
        else:
            lines.append(f"| {label} | {b_val}{unit} | {c_val}{unit} | {sign}{delta}{unit} | {status} |")

    if regressions:
        lines += ["", "**Top regressions:**", ""]
        for r in regressions:
            issues_str = ", ".join(r["issues"])
            lines.append(f"- `{r['case_id']}`: {issues_str}")

    lines += ["", f"*Generated by PromptGuard at {datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M UTC')}*"]
    return "\n".join(lines)


def generate_html_report(run_id: str, b_metrics: dict, c_metrics: dict,
                          decision: str, baseline: list, candidate: list) -> str:
    """Generates a full HTML report with a per-case diff table."""
    baseline_map = {r["case_id"]: r for r in baseline}
    candidate_map = {r["case_id"]: r for r in candidate}

    rows_html = ""
    for case_id in sorted(baseline_map.keys()):
        b = baseline_map[case_id]
        c = candidate_map.get(case_id, {})
        schema_changed = b["schema_valid"] != c.get("schema_valid", 0)
        sentiment_changed = b["sentiment_correct"] != c.get("sentiment_correct", 0)
        urgency_changed = b["urgency_correct"] != c.get("urgency_correct", 0)
        row_class = "regression" if (schema_changed or sentiment_changed or urgency_changed) else ""

        rows_html += f"""
        <tr class="{row_class}">
            <td>{case_id}</td>
            <td>{'PASS' if b['schema_valid'] else 'FAIL'} → {'PASS' if c.get('schema_valid') else 'FAIL'}</td>
            <td>{b.get('parsed_sentiment','—')} → {c.get('parsed_sentiment','—')}</td>
            <td>{b.get('parsed_urgency','—')} → {c.get('parsed_urgency','—')}</td>
            <td>{b['latency_ms']}ms → {c.get('latency_ms','—')}ms</td>
        </tr>"""

    decision_colour = "#d73a49" if decision == "BLOCKED" else "#f9c513" if decision == "WARNING" else "#28a745"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PromptGuard Report — {run_id}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1000px; margin: 40px auto; padding: 0 20px; color: #24292e; }}
  h1 {{ border-bottom: 2px solid #e1e4e8; padding-bottom: 10px; }}
  .decision {{ display: inline-block; padding: 8px 20px; border-radius: 6px;
               background: {decision_colour}; color: white; font-weight: bold;
               font-size: 1.1em; margin: 10px 0 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
  th {{ background: #f6f8fa; text-align: left; padding: 10px 12px;
        border: 1px solid #e1e4e8; }}
  td {{ padding: 8px 12px; border: 1px solid #e1e4e8; font-size: 0.9em; }}
  tr.regression {{ background: #fff5f5; }}
  tr.regression td {{ border-color: #fdb8c0; }}
  .metric-table td:nth-child(4) {{ font-weight: bold; }}
  .run-meta {{ color: #586069; font-size: 0.9em; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>PromptGuard Regression Report</h1>
<p class="run-meta">Run ID: <code>{run_id}</code> &nbsp;|&nbsp;
Generated: {datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M UTC')}</p>
<div class="decision">{decision}</div>

<h2>Metric Summary</h2>
<table class="metric-table">
  <tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr>
  <tr><td>Schema Validity</td><td>{b_metrics['schema_valid_pct']}%</td>
      <td>{c_metrics['schema_valid_pct']}%</td>
      <td>{round(c_metrics['schema_valid_pct'] - b_metrics['schema_valid_pct'], 1)}%</td></tr>
  <tr><td>Sentiment Accuracy</td><td>{b_metrics['sentiment_acc_pct']}%</td>
      <td>{c_metrics['sentiment_acc_pct']}%</td>
      <td>{round(c_metrics['sentiment_acc_pct'] - b_metrics['sentiment_acc_pct'], 1)}%</td></tr>
  <tr><td>Urgency Accuracy</td><td>{b_metrics['urgency_acc_pct']}%</td>
      <td>{c_metrics['urgency_acc_pct']}%</td>
      <td>{round(c_metrics['urgency_acc_pct'] - b_metrics['urgency_acc_pct'], 1)}%</td></tr>
  <tr><td>Avg Latency</td><td>{b_metrics['avg_latency_ms']}ms</td>
      <td>{c_metrics['avg_latency_ms']}ms</td>
      <td>{round(c_metrics['avg_latency_ms'] - b_metrics['avg_latency_ms'], 1)}ms</td></tr>
  <tr><td>Total Cost (USD)</td><td>${b_metrics['total_cost_usd']}</td>
      <td>${c_metrics['total_cost_usd']}</td>
      <td>${round(c_metrics['total_cost_usd'] - b_metrics['total_cost_usd'], 6)}</td></tr>
</table>

<h2>Per-Case Diff (red rows = regressions)</h2>
<table>
  <tr><th>Case</th><th>Schema</th><th>Sentiment</th><th>Urgency</th><th>Latency</th></tr>
  {rows_html}
</table>
</body>
</html>"""


def generate_reports(run_id: str):
    """Main entry point — fetches run data and writes both report files."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    data = fetch_run_results(run_id)
    baseline = data["baseline"]
    candidate = data["candidate"]

    if not baseline or not candidate:
        print(f"No results found for run_id: {run_id}")
        return

    b_metrics = compute_metrics(baseline)
    c_metrics = compute_metrics(candidate)
    decision, flags = get_decision(b_metrics, c_metrics)
    regressions = find_regressions(baseline, candidate)

    md = generate_markdown_comment(run_id, b_metrics, c_metrics, decision, flags, regressions)
    html = generate_html_report(run_id, b_metrics, c_metrics, decision, baseline, candidate)

    md_path = os.path.join(ARTIFACTS_DIR, f"report_{run_id}.md")
    html_path = os.path.join(ARTIFACTS_DIR, f"report_{run_id}.html")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nReports written:")
    print(f"  Markdown : {md_path}")
    print(f"  HTML     : {html_path}")
    print(f"\nDecision : {decision}")
    print(f"\n--- PR Comment Preview ---\n")
    print(md)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, help="Run ID from eval_runner output")
    args = parser.parse_args()
    generate_reports(args.run_id)