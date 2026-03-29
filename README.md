
# Ethics Code Analyzer

A tool that scans any code repository — **GitHub, GitLab, Bitbucket, or pasted code** — for ethical compliance issues such as privacy risks, security secrets, fairness gaps, transparency, and more.

It combines **rule-based pattern scanning** with **Claude AI (Anthropic)** to produce a scored report with concrete, actionable suggestions.

---

## How It Works — Big Picture

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                          YOU  (the user)                            │
  │         paste code snippet   OR   provide a repo URL + files        │
  └─────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │       Streamlit UI           │   streamlit_app.py
              │   (runs on localhost:8501)   │
              └──────────────┬───────────────┘
                             │  HTTP POST /api/ethics/analyze
                             ▼
              ┌──────────────────────────────┐
              │      FastAPI Backend         │   api.py
              │   (runs on localhost:8000)   │
              └──────┬───────────┬───────────┘
                     │           │           │
           ┌─────────┘    ┌──────┘    ┌──────┘
           ▼              ▼           ▼
  ┌──────────────┐ ┌────────────┐ ┌────────────────┐
  │   GitHub     │ │  Git URL   │ │    Local       │
  │  Connector   │ │ Connector  │ │   Snippets     │
  │  PyGitHub    │ │ GitPython  │ │  (no clone)    │
  │  API calls   │ │   clone    │ │                │
  └──────┬───────┘ └─────┬──────┘ └───────┬────────┘
         │               │                │
         └───────────────┼────────────────┘
                         │  (file contents)
                         ▼
         ┌───────────────────────────────────┐
         │         Ethics Analyzer           │   ethics_analyzer.py
         │                                   │
         │  Step 1 — Heuristic rule scan:    │
         │    regex patterns for secrets,    │
         │    privacy, governance keywords   │
         │                                   │
         │  Step 2 — Build code summary      │
         │    (top snippets per file)        │
         └──────────────┬────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────┐
         │          LLM Client               │   llm_client.py
         │   Claude Haiku (Anthropic API)    │
         │                                   │
         │   Evaluates P1–P11 pillars:       │
         │   3 yes/no questions each,        │
         │   scored 0 / 1 / 2               │
         └──────────────┬────────────────────┘
                        │
                        ▼
         ┌───────────────────────────────────┐
         │        Score + Report             │
         │   Overall score  0–100            │
         │   Per-pillar verdict + evidence   │
         │   Concrete fix suggestions        │
         └──────┬──────────────┬─────────────┘
                │              │
                ▼              ▼
  ┌─────────────────┐   ┌──────────────────────┐
  │  Streamlit UI   │   │   Optional outputs   │
  │  Dashboard      │   │                      │
  │  • score gauge  │   │  • Save JSON report  │
  │  • pillar cards │   │    → ./reports/      │
  │  • suggestions  │   │                      │
  └─────────────────┘   │  • Create GitHub     │
                        │    Issue (score < 50)│
                        └──────────────────────┘
```

---

## What Are the Ethics Pillars?

The analyzer checks your code against **11 pillars** grouped into 3 focus profiles.

| # | Pillar | What it looks for |
|---|--------|-------------------|
| P1 | Governance | Ownership, team accountability, responsible party |
| P2 | Risk | Risk assessment, documented edge cases |
| P3 | Human Oversight | Human review steps, override mechanisms |
| P4 | Privacy | PII handling, data collection policies |
| P5 | Fairness | Bias checks, representative test data |
| P6 | Transparency | Explainability, logging, audit trails |
| P7 | Safety | Dangerous operation guards, input validation |
| P8 | Security | Hardcoded secrets, token exposure, encryption |
| P9 | Documentation | README quality, changelog, architecture docs |
| P10 | Accessibility | Keyboard nav, ARIA labels, color contrast |
| P11 | Societal Impact | Misuse risks, harm prevention policies |

**GEN overlay** — additionally checks if the code uses generative AI and whether it handles prompt injection, data leakage, or hallucination risks.

**Focus profiles** let you pick a subset:

| Profile | Pillars | Best for |
|---------|---------|----------|
| `1` — Responsibility & management | P1, P2, P3 | Teams, governance audits |
| `2` — Data safety & security *(default)* | P4, P5, P6, P7, P8 | Security reviews, data products |
| `3` — Understanding, accessibility & impact | P9, P10, P11 | Open-source, public-facing tools |

---

## Project File Structure

```
ethics-analyzer/
│
├── api.py                  # FastAPI backend — 2 endpoints:
│                           #   POST /api/ethics/analyze
│                           #   POST /api/ethics/git-list-files
│
├── streamlit_app.py        # Streamlit web UI — sidebar controls,
│                           # results dashboard, file picker
│
├── ethics_analyzer.py      # Core engine:
│                           #   - Heuristic rule scanner (regex patterns)
│                           #   - Score calculation (per pillar + overall)
│                           #   - Calls LLM for qualitative evaluation
│
├── llm_client.py           # Anthropic Claude API wrapper
│                           #   - Sends code summaries to Claude Haiku
│                           #   - Parses and normalises JSON response
│                           #   - JSON auto-repair on malformed responses
│
├── github_connector.py     # GitHub-specific connector (uses PyGitHub)
│                           #   - Lists code files by language
│                           #   - Reads file content via GitHub API
│                           #   - Creates GitHub issues for low scores
│
├── git_connector.py        # Generic git connector (uses GitPython)
│                           #   - Clones any public repo (GitHub/GitLab/Bitbucket)
│                           #   - Branch fallback (main → master → remote HEAD)
│                           #   - Cleans up temp clone after use
│
├── main.py                 # Uvicorn entry point (python main.py)
├── requirements.txt        # Python dependencies
├── .env                    # Your API keys (never commit this!)
└── reports/                # Auto-created — saved JSON reports go here
```

---

## Quick Start (Step by Step)

### Step 1 — Clone the repo

```bash
git clone https://github.com/laavanjan/ethics-analyzer.git
cd ethics-analyzer
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

Or if you use `uv`:

```bash
uv pip install -r requirements.txt
```

### Step 3 — Create a `.env` file

Create a file called `.env` in the project root:

```env
# Required — your Claude (Anthropic) API key
ANTHROPIC_API_KEY=sk-ant-api03-................................

# Optional — only needed for GitHub mode (scanning GitHub repos or creating issues)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Get your Anthropic API key at: https://console.anthropic.com/

### Step 4 — Start the backend

```bash
uvicorn api:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Interactive API docs are at: http://127.0.0.1:8000/docs

### Step 5 — Start the Streamlit UI

In a **new terminal** (keep the backend running):

```bash
streamlit run streamlit_app.py
```

Open: http://localhost:8501

---

## Three Modes of Analysis

### Mode 1 — GitHub (scan a GitHub repo)

1. Select **GitHub** in the sidebar
2. Enter your GitHub token
3. Enter the repo name as `owner/repo` — e.g. `laavanjan/ethics-analyzer`
4. Choose a focus profile
5. Click **Analyze**

**How to get a GitHub token:**
1. Go to https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Select the `repo` scope
4. Copy the token (starts with `ghp_`)

---

### Mode 2 — Git URL (scan any public Git repo — GitLab, Bitbucket, etc.)

No token needed for public repos. The tool clones the repo to a temporary folder, reads the files you select, then deletes the clone.

1. Select **Git** in the sidebar
2. Paste the `.git` URL of the repo
3. Enter the branch name (e.g. `main` or `master`) — leave blank to auto-detect
4. Click **Load Files** to see all files in the repo
5. Check the files you want to scan
6. Click **Analyze**

**Test repos you can try right now:**

| Platform | URL | Branch |
|----------|-----|--------|
| GitLab | `https://gitlab.com/j3j5/website-blog.git` | `master` |
| Bitbucket | `https://bitbucket.org/atlassian/bitbucket-forge-hello-world.git` | `master` |
| GitHub | `https://github.com/laavanjan/ethics-analyzer.git` | `main` |

---

### Mode 3 — Local (paste code directly)

No repo needed. Paste code snippets directly into the UI.

1. Select **Local** in the sidebar
2. Enter a filename (e.g. `app.py`)
3. Paste your code
4. Click **Analyze**

---

## Understanding the Score

After analysis, you get a score from **0 to 100**.

| Score | Meaning |
|-------|---------|
| 80–100 | Strong — good ethical practices in place |
| 50–79 | Moderate — some issues, improvements recommended |
| 0–49 | Weak — significant ethical gaps found |

The score is calculated per pillar (3 yes/no questions each) and blended with the Claude AI qualitative evaluation.

Each failed question shows:
- **Why it failed** — a clear explanation with code evidence
- **What to do** — a concrete, actionable suggestion

---

## Optional Features

### Auto-create a GitHub Issue (GitHub mode only)

If the score is below 50, the tool can automatically open a GitHub issue in the scanned repo listing all findings.

Set `"create_github_issue": true` in the API body, or toggle it in the UI.

Your token needs `repo` (write) scope for this.

### Save a JSON report

The full structured report can be saved as a `.json` file in the `./reports/` folder on the server.

Set `"save_json_report": true` in the API body, or toggle it in the UI.

Example saved file:
```
./reports/ethics_report_laavanjan_ethics-analyzer_20260329_143022.json
```

---

## API Reference (for developers)

Base URL: `http://127.0.0.1:8000`

### POST `/api/ethics/analyze`

```json
{
  "mode": "github" | "local" | "git",

  // GitHub mode only:
  "github_token": "ghp_...",
  "repo_full_name": "owner/repo",

  // Local mode only:
  "snippets": { "file.py": "your code here" },

  // Git mode only:
  "repo_url": "https://gitlab.com/user/repo.git",
  "branch": "main",
  "file_paths": ["README.md", "src/app.py"],

  // All modes:
  "focus_profile": "1" | "2" | "3",
  "languages": ["python", "javascript"],
  "create_github_issue": false,
  "save_json_report": false
}
```

### POST `/api/ethics/git-list-files`

Lists all files in a public git repo (used by the UI's "Load Files" button).

```
?repo_url=https://github.com/user/repo.git&branch=main&languages=python
```

Returns: `{ "files": ["src/app.py", "README.md", ...] }`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY` error | Check your `.env` file has the correct key |
| GitHub 404 repo not found | Wrong repo name, or token doesn't have `repo` scope |
| Bitbucket/GitLab clone fails | Use the `.git` URL, not the browser URL. Public repos only. |
| Wrong branch error | Try `master` instead of `main` (or leave branch blank) |
| Issue not created | Score must be < 50, token needs write access |
| No JSON file saved | Check `save_json_report` is enabled |
| Backend not running | Start `uvicorn api:app --reload --port 8000` first |

---

## Security Notes

- Never commit your `.env` file — it's in `.gitignore`
- Use minimal scopes on GitHub tokens
- All git clones go into OS temp folders and are deleted after analysis

---

Happy ethical coding! 🛡️
