# PromptGuard

> **LLMOps | CI/CD | PromptOps | Regression Testing | Evals**

A production-grade CI/CD safety gate for LLM prompt changes. Whenever a prompt file changes in a pull request, PromptGuard runs a full regression suite, compares the candidate prompt against the current production prompt, and blocks the release if quality, cost, latency, or safety metrics degrade beyond defined thresholds.

---

## The Problem It Solves

Most teams treat prompts like config files — they change them, eyeball the output, and ship. That works until it doesn't.

Consider a real scenario: your team has an AI feature that reads messy customer support notes and converts them into structured CRM summaries. The production prompt (v1) is clean and precise. A teammate rewrites it (v2) to sound more "professional and comprehensive." Here is what actually ships to production without a safety gate:

| Metric | v1 Production | v2 Candidate | Change |
|---|---|---|---|
| Schema Validity | 100% | 6.7% | -93.3% |
| Sentiment Accuracy | 96.7% | 6.7% | -90.0% |
| Urgency Accuracy | 76.7% | 6.7% | -70.0% |
| Avg Latency | 1,417ms | 5,237ms | +269% |
| Total Cost | $0.015 | $0.033 | +122% |

28 out of 30 test cases break. The CRM fields fill with 300-word essays instead of structured JSON. Cost more than doubles. No one notices until it hits production.

**PromptGuard caught this automatically and blocked the merge.**

---

## Live Demo

The demo PR in this repository shows PromptGuard in action:

- PR: `demo/bad-prompt-rewrite` → `main`
- Result: **BLOCKED** — schema validity dropped 93.3%, latency tripled, cost doubled
- The merge button was blocked automatically by GitHub Actions
- Full regression report posted as a PR comment

---

## Architecture

```
PR Opens (prompt file changed)
         │
         ▼
┌─────────────────────┐
│  GitHub Actions CI  │   Triggered by changes to /prompts or /evals
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Eval Runner        │   Loads baseline + candidate prompt
│  (Python)           │   Runs both against 30-case golden test set
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Scoring Engine     │   Schema validity, sentiment accuracy,
│                     │   urgency accuracy, latency, cost
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Threshold Checker  │   Compares deltas — warns or blocks
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Report Generator   │   Markdown PR comment + HTML diff report
│  + React Dashboard  │   Run history, score trends, case-level diffs
└─────────────────────┘
```

---

## Tech Stack

| Component | Tool | Reason |
|---|---|---|
| Language | Python 3.12 | Eval runners, automation, CI compatibility |
| LLM Provider | Anthropic Claude (claude-haiku-4-5) | Native API, cost-efficient for eval runs |
| Prompt Format | YAML | Human-readable, diffs cleanly in PRs |
| Structured Output | Pydantic v2 | Testable, validated response contracts |
| Storage | SQLite + JSONL | Portable, inspectable, zero infrastructure |
| CI/CD | GitHub Actions | Native merge gate on PR events |
| Reporting | Markdown + HTML | PR comments and browser-viewable reports |
| Dashboard | React (Vite) | Interactive run history and score trends |

---

## Repository Structure

```
promptguard/
│
├── prompts/
│   ├── crm_summary_v1.yaml        # Production baseline prompt
│   └── crm_summary_v2.yaml        # Candidate (demo regression)
│
├── evals/
│   ├── golden_set.jsonl           # 30 hand-labelled test cases
│   ├── golden_set_changelog.md    # Dataset version history
│   └── schemas/
│       └── crm_output_schema.py   # Pydantic response contract
│
├── runner/
│   ├── eval_runner.py             # Core regression runner
│   ├── scorer.py                  # Multi-dimension scoring
│   ├── threshold_checker.py       # Warning/block decision logic
│   └── report_generator.py        # HTML + Markdown report builder
│
├── storage/
│   ├── init_db.py                 # SQLite schema setup
│   ├── runs.db                    # Run history
│   └── artifacts/                 # Per-run report files
│
├── dashboard/                     # React (Vite) frontend
│   └── src/components/
│       ├── RunHistory.jsx
│       ├── ScoreCard.jsx
│       ├── DiffViewer.jsx
│       └── ThresholdChart.jsx
│
├── api/
│   └── main.py                    # FastAPI — serves run data to dashboard
│
└── .github/workflows/
    └── prompt_safety_gate.yml     # CI/CD pipeline
```

---

## Setup

### Prerequisites

- Python 3.12
- Git Bash (Windows) or any Unix shell
- Anthropic API key

### Installation

```bash
git clone https://github.com/beawesome8/Prompt-Guard.git
cd Prompt-Guard

python -m venv venv
source venv/Scripts/activate  # Windows Git Bash

pip install -r requirements.txt

cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

### Run the eval locally

```bash
python storage/init_db.py

python runner/eval_runner.py \
  --baseline prompts/crm_summary_v1.yaml \
  --candidate prompts/crm_summary_v2.yaml \
  --test-set evals/golden_set.jsonl
```

### Generate the report

```bash
python runner/report_generator.py --run-id <run_id_from_output>
```

Open the HTML report in your browser:

```bash
start storage/artifacts/report_<run_id>.html   # Windows
open storage/artifacts/report_<run_id>.html    # Mac/Linux
```

---

## Golden Test Set

The evaluation suite contains 30 hand-labelled customer support cases covering:

| Category | Count | Purpose |
|---|---|---|
| Delivery complaints | 5 | Urgency extraction under informal language |
| Refund and exchange requests | 4 | Sentiment and urgency mix |
| Positive feedback | 4 | Model must not manufacture urgency |
| Escalation threats | 3 | Critical urgency from repeated contact patterns |
| Billing and security issues | 3 | Financial and account risk detection |
| Mixed sentiment | 3 | Positive product, negative experience |
| Edge cases | 4 | Single character input, non-English (German), all-caps |
| Health and welfare | 2 | Context-based critical urgency without emotional language |
| Time-sensitive requests | 2 | Neutral tone but high urgency |

Notable edge cases for interview discussion:

- **case_007** (wheelchair ramp): Critical urgency must be inferred from context, not tone
- **case_023** (`?`): Single character input — model must not hallucinate detail
- **case_025** (latex allergy): Polite language masking a health-safety critical request
- **case_029** (German text): Non-English input — urgency and sentiment must still be extracted

---

## How to Add Test Cases

1. Open `evals/golden_set.jsonl`
2. Append a new JSON line:

```json
{
  "id": "case_031",
  "input": "your customer note here",
  "expected": {"sentiment": "negative", "urgency": "high"},
  "difficulty": "medium",
  "risk_area": "category_name",
  "why": "what this case tests"
}
```

3. Update `evals/golden_set_changelog.md` with the reason for the addition
4. Run the eval locally to confirm the baseline still passes before committing

---

## Threshold Configuration

Edit `config.yaml` to adjust warning and blocking thresholds:

```yaml
thresholds:
  schema_validity:
    warn: -1.0      # % drop from baseline
    block: -2.0

  sentiment_accuracy:
    warn: -2.0
    block: -5.0

  urgency_accuracy:
    warn: -2.0
    block: -5.0

  cost_per_call:
    warn: +20.0     # % increase
    block: +40.0
```

Schema validity and safety are hard gates — any drop triggers a block immediately. All other metrics have separate warning and blocking levels to avoid noisy false positives.

---

## CI/CD Behaviour

The workflow triggers only when files under `/prompts/**` or `/evals/**` change — prompt-unrelated commits do not run the eval pipeline.

| Gate Result | Exit Code | Merge Allowed | Action |
|---|---|---|---|
| PASSED | 0 | Yes | Green tick on PR |
| WARNING | 0 | Yes | PR comment with caution flag |
| BLOCKED | 1 | No | Red X, merge button disabled |

---

## Engineering Decisions and Debugging Log

This section documents the real engineering problems encountered during development and how they were resolved. These represent genuine decisions made during the build, not a sanitised happy path.

### 1. Python version incompatibility with grpcio and pydantic-core

**Problem:** Initial `pip install` failed with C compilation errors. The venv was created with Python 3.14 (system default), and `grpcio` and `pydantic-core` did not yet have pre-built wheels for 3.14.

**Root cause:** Cutting-edge Python versions lag behind package support by weeks to months. pip falls back to compiling from C source when no wheel exists, and the C compiler (MSVC) failed on a path length issue.

**Fix:** Recreated the venv explicitly with `py -3.12 -m venv venv`. Python 3.12 is the current industry standard for ML and AI work and has full wheel coverage for all dependencies.

**Impact:** Eliminated the compilation failure entirely. No code changes required.

**Lesson:** Always pin the Python version at venv creation with `py -3.X -m venv venv`. Never rely on the system default.

---

### 2. Anthropic model string format error (404 Not Found)

**Problem:** First API call returned `404 — model: claude-haiku-3-5-20241022 not found`.

**Root cause:** Anthropic's model naming convention is `claude-{major}-{minor}-{name}-{date}`, not `claude-{name}-{major}-{minor}-{date}`. The model string was assembled in the wrong order.

**Fix:** Corrected the model ID in `crm_summary_v1.yaml` from `claude-haiku-3-5-20241022` to `claude-haiku-4-5-20251001` (also updating to the current available model).

**Impact:** API calls succeeded on the next run.

**Lesson:** Always verify model IDs against the Anthropic documentation. The string format is easy to misremember.

---

### 3. Output format drift — model ignoring JSON-only instruction

**Problem:** Schema validation failed on the first successful API call. The model returned valid JSON content but wrapped in markdown fences (` ```json ``` `), causing `json.loads()` to throw a parse error.

**Root cause:** Even with an explicit "Return ONLY valid JSON" instruction, Claude sometimes adds markdown formatting — particularly when the model interprets "helpfulness" as adding structure. This is a known LLMOps problem called output format drift.

**Fix:** Added a `clean_output()` function in `runner/eval_runner.py` that strips markdown fences before passing the response to the JSON parser:

```python
def clean_output(raw_text: str) -> str:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()
```

**Impact:** Schema validation went from FAILED to PASSED. All 30 baseline cases now pass schema validation at 100%.

**Lesson:** Never trust raw model output — always sanitise before parsing. The cleaner long-term fix is to reinforce the JSON-only instruction in the few-shot examples so the model sees the exact format it should copy.

---

### 4. GitHub Personal Access Token missing workflow scope

**Problem:** Push to GitHub rejected with: `refusing to allow a Personal Access Token to create or update workflow without workflow scope`.

**Root cause:** The GitHub Actions workflow file lives under `.github/workflows/`. GitHub requires the `workflow` scope on the token specifically to push files to that path — the standard `repo` scope alone is not sufficient.

**Fix:** Updated the Personal Access Token in GitHub Settings → Developer settings → Personal access tokens to include the `workflow` scope. Re-authenticated Git using `git credential reject`.

**Impact:** Workflow file pushed successfully on the next attempt.

**Lesson:** When creating tokens for repos that use GitHub Actions, always tick both `repo` and `workflow` scopes upfront.

---

### 5. Demo PR showing "nothing to compare" (branch history collision)

**Problem:** After creating the demo branch and opening a PR, GitHub showed "There isn't anything to compare — main and demo/bad-prompt-rewrite are identical."

**Root cause:** The candidate prompt (`crm_summary_v2.yaml`) was committed directly to `main` during development, then the demo branch was created from that state. Both branches shared the same commit history, so the diff was empty.

**Fix:** Removed `crm_summary_v2.yaml` from `main` with `git rm`, deleted and recreated the demo branch from the clean `main`, then committed `v2` only on the demo branch.

**Impact:** PR correctly showed 1 changed file and the GitHub Actions pipeline triggered as expected.

**Lesson:** Demo branches must be created from the clean baseline, not from a state that already includes the change being demonstrated.

---

### 6. datetime.utcnow() deprecation breaking CI

**Problem:** Report generator raised `AttributeError: type object 'datetime.datetime' has no attribute 'UTC'` in the CI environment.

**Root cause:** Two-part issue. First, `datetime.utcnow()` is deprecated in Python 3.12 and was replaced with `datetime.now(datetime.UTC)`. Second, the `datetime.UTC` constant requires importing `datetime` as a module, not just the `datetime` class. The CI environment enforced stricter deprecation handling than the local Windows environment.

**Fix:** Updated the import from `from datetime import datetime` to `from datetime import datetime, timezone` and replaced all `datetime.now(datetime.UTC)` calls with `datetime.now(timezone.utc)`.

**Impact:** Report generator ran cleanly in CI with no deprecation warnings or attribute errors.

**Lesson:** CI environments often run stricter Python configurations than local development. Always test with `python -W error` locally to catch deprecation warnings before they become CI failures.

---

### 7. GitHub Actions workflow permission denied posting PR comments (403)

**Problem:** The "Post PR comment" step failed with `HttpError: Resource not accessible by integration` when trying to post a comment via the GitHub API.

**Root cause:** GitHub Actions workflows run with a default `GITHUB_TOKEN` that has read-only permissions unless explicitly granted write access. Posting PR comments requires `pull-requests: write` permission.

**Fix:** Added a `permissions` block to the workflow file:

```yaml
permissions:
  pull-requests: write
  contents: read
```

**Impact:** PR comment posted successfully with the full regression scorecard on the next run.

**Lesson:** GitHub Actions permissions follow the principle of least privilege by default. Any step that writes to the repo, posts comments, or creates issues requires explicit permission grants in the workflow file.

---

### 8. RUN_ID not captured correctly in CI (report showing all zeros)

**Problem:** The report generator ran but produced all-zero metrics. The RUN_ID environment variable was empty in CI because the grep-based extraction from stdout was unreliable when output was piped through `tee`.

**Root cause:** The original approach parsed the run ID from stdout using `grep 'PromptGuard run ID' eval_output.txt | awk '{print $NF}'`. When `--ci-mode` suppressed output, the grep found nothing and the variable was empty.

**Fix:** Modified `eval_runner.py` to write the run ID to a dedicated file (`run_id.txt`) immediately after generating it. The workflow then reads from the file instead of parsing stdout:

```python
with open("run_id.txt", "w") as f:
    f.write(run_id)
```

**Impact:** Run ID captured correctly, report generated with full metrics, PR comment posted with accurate scorecard.

**Lesson:** Never rely on parsing stdout for structured data in CI pipelines. Write structured outputs to files. Stdout is for human-readable logs; files are for machine-readable data.

---

## Scoring Philosophy

**Why not collapse everything into one score?**
A single composite score hides where regressions come from. A prompt that improves summary quality but breaks schema validity should be blocked, not averaged into a pass. PromptGuard keeps all dimensions separate and surfaces them individually.

**Why LLM-as-judge for summary relevance?**
Summary relevance cannot be measured with exact match. The roadmap includes DeepEval G-Eval scoring for open-ended fields — a second model call that scores how well the generated summary captures the customer's intent.

**Cost of a full eval run:**
With `claude-haiku-4-5` as the eval model, 30 test cases x 2 prompts = 60 API calls. Actual measured cost per full run: approximately $0.015-$0.033 depending on prompt verbosity.

---

## Roadmap

- [ ] React dashboard with run history and score trend charts
- [ ] DeepEval G-Eval integration for summary relevance scoring
- [ ] Multi-provider comparison (Anthropic vs OpenAI on the same test set)
- [ ] Slack notification on BLOCK events
- [ ] Automatic threshold calibration from historical run variance
- [ ] Docker containerisation for identical local and CI behaviour
- [ ] Dataset drift detection

---

## Author

**Aman Benjamin Emmanuel**
AI Engineer | Munich, Germany
[LinkedIn](https://www.linkedin.com/in/beawesome8) | [GitHub](https://github.com/beawesome8) | [Portfolio](https://beawesome8.github.io)

