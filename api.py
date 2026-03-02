# api.py
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import os

from github_connector import GitHubConnector, run_ethics_analysis, analyze_local_code
from ethics_analyzer import EthicsAnalyzer, FOCUS_PROFILES  # export FOCUS_PROFILES from that file
from llm_client import EthicsLLMClient

app = FastAPI()
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


class GitHubRequest(BaseModel):
    mode: str = "github"
    repo_full_name: str
    focus_profile: str = "2"
    languages: Optional[List[str]] = None


class LocalRequest(BaseModel):
    mode: str = "local"
    snippets: Dict[str, str]
    focus_profile: str = "2"


def check_auth(auth_header: Optional[str]):
    if not INTERNAL_API_KEY:
        return
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if token != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/ethics/analyze")
async def analyze(
    body: Dict,
    authorization: Optional[str] = Header(None),
):
    check_auth(authorization)

    mode = body.get("mode", "github")

    focus_profile = body.get("focus_profile", "2")
    focus_pillars = FOCUS_PROFILES.get(focus_profile, FOCUS_PROFILES["2"])

    if mode == "github":
        repo_full_name = body.get("repo_full_name")
        if not repo_full_name:
            raise HTTPException(status_code=400, detail="repo_full_name is required for github mode")

        languages = body.get("languages")
        connector = GitHubConnector()
        repo = connector.get_repository(repo_full_name)
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        code_files = connector.list_code_files(repo, languages=languages)
        all_files = [fp for files in code_files.values() for fp in files]

        analyzer = EthicsAnalyzer(
            use_llm=True,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            focus_pillars=focus_pillars,
        )
        for file_path in all_files:
            content = connector.get_file_content(repo, file_path)
            if content:
                analyzer.analyze_file(file_path, content)

        report = analyzer.generate_report(repo_full_name)
        connector.close()
        report["mode"] = "github"
        report["repo_full_name"] = repo_full_name
        return report

    elif mode == "local":
        snippets = body.get("snippets")
        if not snippets:
            raise HTTPException(status_code=400, detail="snippets is required for local mode")

        analyzer = EthicsAnalyzer(
            use_llm=True,
            groq_api_key=os.getenv("GROQ_API_KEY"),
            focus_pillars=focus_pillars,
        )
        for file_path, content in snippets.items():
            analyzer.analyze_file(file_path, content)

        report = analyzer.generate_report("local/snippet-analysis")
        report["mode"] = "local"
        return report

    else:
        raise HTTPException(status_code=400, detail="mode must be 'github' or 'local'")
