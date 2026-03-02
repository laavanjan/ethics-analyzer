
# Ethics Code Analyzer API

This API exposes the **Ethics Code Analyzer** so anyone on the team can scan a GitHub repository or local code snippets for ethical risks and governance coverage.

It combines:

- Heuristic checks (e.g., hard‑coded secrets, logging).
- Pillar-based LLM assessment using Groq (`llama-3.3-70b-versatile`).
- Primary pillars **P1–P11** plus **GEN/REL overlays**.

---

## 1. Architecture

Core files:

- `ethics_analyzer.py`  
  Implements `EthicsAnalyzer` (controls, overlays, scoring, report).
- `github_connector.py`  
  GitHub integration; in the API, its logic is reused for repo scanning.
- `llm_client.py`  
  `EthicsLLMClient` wrapper around Groq chat completions (JSON output).

API layer (e.g., `api.py`) wraps these components and exposes an HTTP endpoint.

---

## 2. Authentication

The API requires a simple Bearer token.

### Server configuration

Set a shared token on the server:

```bash
export INTERNAL_API_KEY="some-long-random-token"
```

In your API code, validate:

```python
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

def check_auth(auth_header: str | None):
    if not INTERNAL_API_KEY:
        return  # auth disabled if not set
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1).strip()
    if token != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### Client headers

```http
Authorization: Bearer YOUR_INTERNAL_API_KEY
Content-Type: application/json
```

Note: Groq and GitHub have their own API keys via env:

- `GROQ_API_KEY`
- `GITHUB_TOKEN`

---

## 3. Endpoint

- **Base URL** (example): `https://your-domain.com/api`
- **Path**: `/ethics/analyze`
- **Method**: `POST`
- **Content‑Type**: `application/json`

One endpoint supports two modes:

- `mode = "github"` – scan a GitHub repository.
- `mode = "local"` – scan ad‑hoc code snippets.

---

## 4. Request body

### Common field

- `mode` (string, required): `"github"` or `"local"`.

### 4.1 GitHub repo analysis

```json
{
  "mode": "github",
  "repo_full_name": "owner/repo",
  "focus_profile": "2",
  "languages": ["python", "javascript"]
}
```

#### Fields

- `repo_full_name` (string, required when `mode == "github"`):  
  GitHub repo in `owner/repo` format. Example:

  ```json
  "repo_full_name": "laavanjan/Youtube_comment_analysis_end_to_end"
  ```

- `focus_profile` (string, optional, default `"2"`): selects which pillars to emphasize.

  ```python
  FOCUS_PROFILES = {
    "1": ["P1", "P2", "P3"],          # Responsibility & management
    "2": ["P4", "P5", "P6", "P7", "P8"],  # Data safety & security
    "3": ["P9", "P10", "P11"],        # Understanding, accessibility, impact
  }
  ```

  - `"1"` → P1–P3 (Responsibility & management)  
  - `"2"` → P4–P8 (Data safety & security)  
  - `"3"` → P9–P11 (Understanding, accessibility, impact)

- `languages` (array of strings, optional):

  - If omitted or `null`: scan all supported languages
    (`python`, `javascript`, `java`, `cpp`, `csharp`, `go`, `rust`, `php`, `ruby`, `swift`, `kotlin`, `scala`).
  - If present: restrict to those languages:

    ```json
    "languages": ["python"]
    ```

### 4.2 Local snippets analysis

```json
{
  "mode": "local",
  "snippets": {
    "app.py": "import logging\napi_key = 'secret'\nlogging.info('hello')",
    "utils/security.py": "def sanitize(x):\n    return x.strip()"
  },
  "focus_profile": "1"
}
```

#### Fields

- `snippets` (object, required when `mode == "local"`):  
  Mapping `pseudo_file_path -> code string`.

- `focus_profile` (string, optional, default `"2"`): same mapping as above.

---

## 5. Response schema

On success (`200 OK`) the API returns the same structure as:

```python
EthicsAnalyzer.generate_report(...)
```

plus:

- `"mode"` – `"github"` or `"local"`.
- `"repo_full_name"` – for GitHub mode.

### Example

```json
{
  "mode": "github",
  "repo_full_name": "owner/repo",
  "ethical_score": 72.5,
  "total_issues": 3,
  "issues_by_severity": {
    "critical": 1,
    "medium": 2
  },
  "issues_by_type": {
    "security": 1,
    "privacy": 1,
    "fairness": 1
  },
  "issues": [
    {
      "file_path": "src/app.py",
      "line_number": 1,
      "issue_type": "security",
      "severity": "critical",
      "message": "Possible hard‑coded secret detected.",
      "suggestion": "Move secrets to env vars or secret manager; rotate exposed keys.",
      "code_snippet": "...api_key = '***'..."
    }
  ],
  "controls": {
    "SEC-03": {
      "control_id": "SEC-03",
      "pillar": "P8",
      "name": "Secure SDLC / secrets",
      "satisfied": false,
      "evidence_files": ["src/app.py"],
      "notes": "Hard‑coded secrets found."
    }
  },
  "overlays": {
    "GEN": {
      "GEN-01": "conditional",
      "GEN-02": "not_applicable"
    },
    "REL": {
      "REL-01": "unmet"
    }
  },
  "llm_result": {
    "pillars": {
      "P4": {
        "score": 1,
        "reason": "In src/app.py: `api_key = 'secret'` shows privacy/security risk; limited evidence of proper controls."
      },
      "P5": {
        "score": 0,
        "reason": "No fairness or bias‑related logic visible in the provided snippets."
      }
    },
    "gen": {
      "uses_generative_ai": false,
      "score": 0,
      "reason": "No LLM or image generation calls found."
    },
    "overall_comment": "Good logging, but secrets in code and missing privacy controls."
  },
  "focus_pillars": ["P4", "P5", "P6", "P7", "P8"]
}
```

Notes for readers:

- `ethical_score` is a blended heuristic + LLM score (0–100).
- `issues` are the heuristic issues detected (e.g., secrets in code).
- `controls` reflect which governance controls are satisfied or unmet.
- `overlays.GEN`/`REL` come from anchor controls.
- `llm_result.pillars` only contains pillars in the selected `focus_profile`.
- Each `reason` includes code or file references to explain why the score is 0/1/2.

---

## 6. Error responses

### 400 Bad Request

Missing or invalid fields.

```json
{
  "error": "invalid_request",
  "message": "repo_full_name is required when mode == 'github'"
}
```

Other examples:

- `mode` not in `["github", "local"]`
- missing `snippets` when `mode == "local"`.

### 401 Unauthorized

Missing or invalid `Authorization` header.

```json
{
  "error": "unauthorized",
  "message": "Missing or invalid API token"
}
```

### 500 Internal Server Error

Unexpected internal error (GitHub / Groq / parsing failures).

```json
{
  "error": "server_error",
  "message": "Unexpected error while running ethics analysis"
}
```

---

## 7. Example calls

### 7.1 GitHub repo (cURL)

```bash
curl -X POST https://your-domain.com/api/ethics/analyze \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "github",
    "repo_full_name": "laavanjan/Youtube_comment_analysis_end_to_end",
    "focus_profile": "2",
    "languages": ["python"]
  }'
```

### 7.2 Local snippets (cURL)

```bash
curl -X POST https://your-domain.com/api/ethics/analyze \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "local",
    "focus_profile": "1",
    "snippets": {
      "app.py": "import logging\napi_key = \"secret\"\nlogging.info(\"hello\")",
      "utils/security.py": "def sanitize(x):\n    return x.strip()"
    }
  }'
```

---

## 8. Running locally (dev)

1. Clone the repo and set up a virtual environment.
2. Install dependencies:

   ```bash
   pip install fastapi uvicorn groq PyGithub python-dotenv
   ```

3. Set environment variables:

   ```bash
   export GROQ_API_KEY="your-groq-key"
   export GITHUB_TOKEN="your-github-token"
   export INTERNAL_API_KEY="your-internal-api-token"
   ```

4. Start the API (example with FastAPI):

   ```bash
   uvicorn api:app --reload
   ```

5. Call the endpoint from cURL/Postman as shown above.

---

## 9. Extending the API

Possible extensions:

- Add a `GET /ethics/models` to list available Groq models.
- Add a `GET /health` to check Groq/GitHub/env status.
- Add a query parameter or field to toggle LLM usage (`use_llm: true/false`) for faster, heuristic-only scans.

Contributors should preserve the current JSON contract so existing clients continue to work.
```