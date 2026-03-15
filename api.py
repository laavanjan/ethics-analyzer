# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime
import os
import json

from dotenv import load_dotenv

load_dotenv()

from github_connector import GitHubConnector, create_ethics_issue
from ethics_analyzer import (
    EthicsAnalyzer,
    normalize_focus_profile_name,
    resolve_focus_profile,
)
from llm_client import EthicsLLMClient

app = FastAPI(
    title="Ethics Code Analyzer API",
    description="API for analyzing code repositories or snippets for ethical compliance",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    mode: str = "github"  # "github" or "local"
    github_token: Optional[str] = None  # required only for github mode
    repo_full_name: Optional[str] = None  # required for github
    snippets: Optional[Dict[str, str]] = None  # required for local
    focus_profile: str = "2"
    languages: Optional[List[str]] = None
    create_github_issue: bool = False
    save_json_report: bool = False


@app.post("/api/ethics/analyze")
async def analyze(body: AnalyzeRequest):
    """
    Analyze GitHub repo or local code snippets.

    - github mode: requires github_token and repo_full_name
    - local mode: requires snippets
    - Optional: create_github_issue, save_json_report
    """
    mode = body.mode
    focus_profile = normalize_focus_profile_name(body.focus_profile)
    focus_pillars = resolve_focus_profile(body.focus_profile)

    # Prepare base response early
    response = {
        "success": True,
        "status": "completed",
        "mode": mode,
        "repo_full_name": None,
        "focus_profile": focus_profile,
        "focus_pillars": focus_pillars,
        "files_scanned": 0,
        "scan_timestamp": datetime.utcnow().isoformat() + "Z",
        "issue_created": False,
        "json_saved": False,
        "saved_file": None,
        "issue_error": None,
        "issue_skipped_reason": None,
    }

    connector = None
    repo = None
    report = None

    if mode == "github":
        if not body.github_token:
            raise HTTPException(400, "github_token is required for github mode")
        if not body.repo_full_name:
            raise HTTPException(400, "repo_full_name is required for github mode")

        connector = GitHubConnector(access_token=body.github_token)

        repo = connector.get_repository(body.repo_full_name)
        if not repo:
            raise HTTPException(
                404, "Repository not found or token has insufficient permissions"
            )

        code_files = connector.list_code_files(repo, languages=body.languages)
        code_file_paths = [fp for files in code_files.values() for fp in files]
        ethics_doc_files = connector.list_ethics_doc_files(repo)
        code_set = set(code_file_paths)
        extra_doc_files = [fp for fp in ethics_doc_files if fp not in code_set]
        all_files = extra_doc_files + code_file_paths

        analyzer = EthicsAnalyzer(
            use_llm=True,
            focus_pillars=focus_pillars,
        )

        for file_path in all_files:
            content = connector.get_file_content(repo, file_path)
            if content:
                analyzer.analyze_file(file_path, content)

        report = analyzer.generate_report(body.repo_full_name)

        response["repo_full_name"] = body.repo_full_name
        response["files_scanned"] = len(all_files)
        response["analyzed_files"] = all_files

    elif mode == "local":
        if not body.snippets or not isinstance(body.snippets, dict):
            raise HTTPException(400, "snippets must be a non-empty dict for local mode")

        analyzer = EthicsAnalyzer(
            use_llm=True,
            focus_pillars=focus_pillars,
        )

        for file_path, content in body.snippets.items():
            if content:
                analyzer.analyze_file(file_path, content)

        report = analyzer.generate_report("local/snippet-analysis")

        response["files_scanned"] = len(body.snippets)

    else:
        raise HTTPException(status_code=400, detail="mode must be 'github' or 'local'")

    # Update response with analysis results
    response.update(report)

    # GitHub issue creation (only github mode)
    if mode == "github" and body.create_github_issue:
        if report["ethical_score"] < 50:
            try:
                create_ethics_issue(repo, report)
                response["issue_created"] = True
            except Exception as e:
                response["issue_created"] = False
                response["issue_error"] = str(e)
        else:
            response["issue_created"] = False
            response["issue_skipped_reason"] = "Score >= 50 – no critical issues"

    # JSON saving (both modes)
    if body.save_json_report:
        repo_name_safe = (
            body.repo_full_name.replace("/", "_") if mode == "github" else "local"
        )
        filename = f"ethics_report_{repo_name_safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_path = f"./reports/{filename}"
        os.makedirs("./reports", exist_ok=True)

        # Save the full report
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)  # default=str for dataclasses

        response["json_saved"] = True
        response["saved_file"] = save_path

    # Cleanup
    if connector:
        connector.close()

    return response
