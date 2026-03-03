
# Ethics Code Analyzer API

A FastAPI-powered API that scans GitHub repositories or local code snippets for ethical compliance (privacy, fairness, transparency, safety, security, etc.) using rule-based checks + Claude (Anthropic LLM).

Focus profiles:
- **1** — Responsibility & management (P1–P3)
- **2** — Data safety & security (P4–P8) ← **default**
- **3** — Understanding, accessibility, societal impact (P9–P11)

## Features

- Analyze GitHub repos or pasted code
- Optional: auto-create GitHub issue if score < 50
- Optional: save full report as JSON file on server
- Powered by Claude for deep qualitative reasoning

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
# or
uv pip install fastapi uvicorn python-dotenv anthropic PyGithub
```

### 2. Create `.env` file (in project root)

```env
# Required — your Claude API key
ANTHROPIC_API_KEY=sk-ant-api03-................................

# Optional — only needed if scanning private repos or creating issues
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Start the server

```bash
uvicorn api:app --reload --port 8000
```

Open interactive docs:  
→ http://127.0.0.1:8000/docs

## How to Get a GitHub Personal Access Token (Classic)

You need this token to scan repositories (especially private ones) or create issues.

1. Go to: https://github.com/settings/tokens
2. Click **Generate new token** → **Generate new token (classic)**
3. Give it a name (e.g. "Ethics Analyzer 2026")
4. Set expiration (e.g. 30 days or No expiration — your choice)
5. Select scopes:
   - `repo` (full control of private repositories — includes read code + create issues)
   - Optional: `read:org` if scanning org repos
6. Click **Generate token**
7. **Copy the token** (starts with `ghp_`) — you won't see it again!
8. Paste it into your `.env` file (or send it in API requests)

**Security warning**: Never commit the token to Git or share it publicly.

## API Endpoint

**POST** `/api/ethics/analyze`

**Base URL**: `http://127.0.0.1:8000` (local)

### Request Body Schema

```json
{
  "mode":              "github" | "local" (required)
  "github_token":      string (required for github mode)
  "repo_full_name":    string (required for github mode, e.g. "owner/repo")
  "snippets":          object (required for local mode, { "file.py": "code..." })
  "focus_profile":     "1" | "2" | "3" (default: "2")
  "languages":         ["python", "javascript", ...] (optional, github mode only)
  "create_github_issue": boolean (optional, default: false)
  "save_json_report":    boolean (optional, default: false)
}
```

### Examples

#### Scan GitHub repo + create issue + save JSON

```json
{
  "mode": "github",
  "github_token": "ghp_your_token_here",
  "repo_full_name": "laavanjan/ethics-analyzer",
  "focus_profile": "2",
  "create_github_issue": true,
  "save_json_report": true
}
```

#### Local snippets (no token needed)

```json
{
  "mode": "local",
  "snippets": {
    "test.py": "API_KEY = \"gsk_123456789secret\"",
    "app.py": "def process(text): return text.upper()"
  },
  "focus_profile": "2",
  "save_json_report": true
}
```

### Where Saved Files Go

- JSON reports are saved in the `./reports/` folder (relative to where you run `uvicorn`)
- Example: `./reports/ethics_report_laavanjan_ethics-analyzer_20260303_071317.json`
- Folder is auto-created if missing

### Response Body Example

```json
{
  "success": true,
  "status": "completed",
  "mode": "github",
  "repo_full_name": "laavanjan/ethics-analyzer",
  "focus_profile": "2",
  "focus_pillars": ["P4", "P5", "P6", "P7", "P8"],
  "files_scanned": 3,
  "scan_timestamp": "2026-03-03T07:13:17.337754Z",
  "ethical_score": 25,
  "total_issues": 0,
  "issue_created": true,
  "json_saved": true,
  "saved_file": "./reports/ethics_report_laavanjan_ethics-analyzer_20260303_XXXXXX.json",
  "llm_result": {
    "pillars": { ... },
    "gen": { ... },
    "overall_comment": "..."
  }
}
```

## Security & Best Practices

- **Never commit tokens** to git — use `.env` or environment variables
- Use minimal scopes on GitHub tokens
- For production: switch to GitHub OAuth (no raw token sharing)
- Rate limits: GitHub API ~5000 requests/hour with token
- Private repos: token needs `repo` scope

## Troubleshooting

- No file saved? → Make sure `"save_json_report": true` is in the body
- Issue not created? → Check token has `repo` scope, score < 50, and you have write access
- 404 repo not found? → Wrong repo name or insufficient token permissions

For bugs or suggestions — open an issue!

Happy ethical coding! 🛡️
