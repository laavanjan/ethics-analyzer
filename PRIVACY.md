# Privacy & Data Handling

This document explains what data the Ethics Code Analyzer touches, what (if
anything) is retained, and how to clear it.

It addresses CER controls **PRIV-01** (PII in logs), **PRIV-03** (user-facing
data-use notice), and **PRIV-04** (retention / deletion).

---

## What data the tool receives

| Mode | Input | Sent to Anthropic Claude? | Stored locally? |
|---|---|---|---|
| `github` | A GitHub access token + a `owner/repo` name. The tool downloads file contents via the GitHub API. | Yes — summarised file snippets (≤ ~5 KB per file) are sent to Claude Haiku. The token itself is NEVER sent. | Only if `save_json_report=true`, then a JSON report is written to `./reports/`. |
| `git`  | A `.git` URL + a branch name. The repo is cloned to a temporary directory, scanned, then the clone is deleted. | Same as above — only summarised file snippets, not the token. | Same. |
| `local` | Pasted code snippets. | Same as above. | Same. |

No analytics, no telemetry, no third-party logging service.

---

## What is retained

**Only `./reports/*.json` files**, and only if you explicitly pass
`save_json_report=true` in the API body or enable the toggle in the UI.

Each file contains:

- The repo name (or `local/snippet-analysis`)
- The scan timestamp
- The per-pillar findings, evidence excerpts, and remediation suggestions

It does **not** contain:

- GitHub or Anthropic API tokens
- Full file contents — only the snippets the LLM was shown
- User identity beyond the repo owner already encoded in the repo name

---

## Retention policy (TTL — 30 days)

Saved reports under `./reports/` are considered ephemeral and **expire after
30 days** by default. To enforce this, run the bundled cleanup script:

```bash
python cleanup_reports.py            # delete reports older than 30 days
python cleanup_reports.py --days 7   # custom TTL
python cleanup_reports.py --dry-run  # show what would be deleted
```

Schedule it via cron / Windows Task Scheduler if you want it automated:

```
# Daily 03:00 cleanup
0 3 * * *  cd /path/to/ethics-analyzer && python cleanup_reports.py
```

---

## How to delete your data

| Want to delete… | Run |
|---|---|
| One specific report | `rm reports/<filename>.json` |
| Everything older than N days | `python cleanup_reports.py --days N` |
| All reports | `rm -rf reports/` (the next scan will recreate the directory) |
| The cloned-repo cache | Nothing to do — temp clones are deleted automatically after each scan. |

---

## Log redaction (PRIV-01)

Error messages returned by the FastAPI backend and written to stdout pass
through [`logging_utils.redact_sensitive`](logging_utils.py), which masks:

- GitHub tokens (`ghp_…`, `github_pat_…`)
- Anthropic API keys (`sk-ant-…`)
- `Authorization: Bearer …` headers
- Email addresses (local-part is masked, domain kept for debugging)
- Generic `secret=…` / `password=…` / `token=…` / `api_key=…` assignments

If you spot a log line that leaks something, please open an issue with the
exact pattern so we can extend the redactor.

---

## Optional access control (PRIV-05)

If you deploy this beyond localhost, set the `ETHICS_API_KEY` environment
variable. When set, both `/api/ethics/analyze` and `/api/ethics/git-list-files`
require a matching `X-API-Key` header. When unset (default), the routes are
open to make local development frictionless.

```bash
# Server
export ETHICS_API_KEY="$(openssl rand -hex 32)"
uvicorn api:app --port 8000

# Client
curl -H "X-API-Key: $ETHICS_API_KEY" \
     -X POST http://127.0.0.1:8000/api/ethics/analyze \
     -d '{"mode":"local","snippets":{"a.py":"print(1)"}}'
```

---

Last updated: 2026-06-13.
