import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st

try:
    from streamlit_keyup import st_keyup
except Exception:
    st_keyup = None

from ethics_analyzer import EthicsAnalyzer
from github_connector import GitHubConnector, create_ethics_issue


PILLAR_ID_TO_NAME = EthicsAnalyzer.PILLARS
PILLAR_NAME_TO_ID = {name: pillar_id for pillar_id, name in PILLAR_ID_TO_NAME.items()}
PILLAR_DESCRIPTIONS = {
    "governance": "Ownership, accountability, and change tracking for the system.",
    "risk": "How clearly project risks are identified, ranked, and reviewed over time.",
    "human_oversight": "Human control paths such as review, override, rollback, and escalation.",
    "privacy": "Data minimization, consent/notice, and retention/deletion policy clarity.",
    "fairness": "Bias awareness, fairness checks, and mitigation actions.",
    "transparency": "User clarity about AI usage, limits, and model/data context.",
    "safety": "Guardrails, stress testing, and safe fallbacks for risky situations.",
    "security": "Secret handling, validation, access control, and abuse prevention.",
    "documentation": "Quality of README, model/data documentation, and decision traceability.",
    "accessibility": "Inclusion, understandable messaging, and non-deceptive UX behavior.",
    "societal": "Social benefit intent, misuse awareness, and harm reduction planning.",
}


def _safe_rule_sort_key(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def _repo_matches_query(repo_name: str, query: str) -> bool:
    if not query:
        return True

    normalized_query = " ".join(query.replace("\t", " ").lower().split())
    if not normalized_query:
        return True

    repo_lower = repo_name.lower()
    repo_words = re.sub(r"[\/_\-.]+", " ", repo_lower)
    tokens = normalized_query.split(" ")

    return all((token in repo_lower) or (token in repo_words) for token in tokens)


def _default_fail_suggestion(question_text: str) -> str:
    text = (question_text or "").lower()
    if "owner" in text or "team" in text or "responsible" in text:
        return "Add an OWNER section in README.md with a primary owner, backup owner, and team contact channel."
    if "explained" in text or "meant to do" in text or "purpose" in text:
        return "Add a clear project overview in README.md covering purpose, inputs, outputs, and a short usage flow."
    if "version history" in text or "changelog" in text or "changed over time" in text:
        return "Create a CHANGELOG.md file and record each release date with Added/Changed/Fixed items; link it in README.md."
    if "privacy" in text or "personal" in text:
        return "Document data handling in README.md: what personal data is collected, why, where stored, and retention/deletion timelines."
    if "security" in text or "secret" in text or "token" in text:
        return "Move secrets to environment variables or a secret manager, rotate exposed keys, and enforce secret scanning in CI."
    if "accessibility" in text:
        return "Add accessibility checks for keyboard navigation, labels, and contrast; include pass/fail criteria in release checks."
    return "Add a concrete policy section in README.md with clear rules, owner, and review cadence."


def _render_llm_results(report: Dict):
    llm_result = report.get("llm_result") or {}
    if not llm_result:
        st.info("LLM result is not available.")
        return

    overall_comment = llm_result.get("overall_comment") or ""
    if (
        "api key is invalid" in overall_comment.lower()
        or "anthropic_api_key" in overall_comment.lower()
    ):
        st.error(overall_comment)
        return

    if llm_result.get("evaluation_status") == "insufficient_code":
        st.warning("Not evaluated: insufficient meaningful code.")

    pillars = llm_result.get("pillars", {})
    focus_pillars = report.get("focus_pillars", list(pillars.keys()))

    st.subheader("Pillar Assessment")
    for pillar_id in focus_pillars:
        pillar_data = pillars.get(pillar_id, {})
        score = pillar_data.get("score")
        pillar_name = EthicsAnalyzer.PILLARS.get(pillar_id, "unknown")
        status_label = EthicsAnalyzer.get_pillar_status_label(pillar_data)
        passed_count = EthicsAnalyzer.count_passed_questions(pillar_data)

        header_text = f"{pillar_name} — {status_label}"
        if passed_count is not None:
            header_text += f" ({passed_count}/3 questions passed)"

        with st.expander(header_text, expanded=False):
            pillar_description = PILLAR_DESCRIPTIONS.get(pillar_name)
            if pillar_description:
                st.caption(f"Meaning: {pillar_description}")

            if passed_count is not None:
                pillar_score = EthicsAnalyzer.QUESTION_PASS_SCORE_MAP.get(
                    passed_count, 0
                )
                st.write(
                    f"Pillar score: {pillar_score}/100 (from {passed_count}/3 questions passed)"
                )
            elif isinstance(score, (int, float)):
                normalized_from_raw = int(max(0, min(2, score)) * 50)
                st.write(f"Pillar score: {normalized_from_raw}/100")
            if passed_count is not None:
                st.write(f"Overall result: {status_label}")

            rules_data = pillar_data.get("rules", {})
            question_texts = EthicsAnalyzer.PILLAR_RULES.get(pillar_id, [])
            if isinstance(rules_data, dict) and rules_data:
                for rule_num in sorted(rules_data.keys(), key=_safe_rule_sort_key):
                    rule_result = rules_data.get(rule_num, {}) or {}
                    passed = rule_result.get("passed")
                    status = "PASS" if passed else "FAIL"
                    reason = rule_result.get("reason", "No reason provided.")
                    evidence = (rule_result.get("evidence") or "").strip()
                    suggestion = (rule_result.get("suggestion") or "").strip()
                    question_index = _safe_rule_sort_key(rule_num) - 1
                    if 0 <= question_index < len(question_texts):
                        question_text = question_texts[question_index]
                    else:
                        question_text = f"Question {rule_num}"

                    st.markdown(f"**{question_text}**")
                    st.write(f"Status: {status}")
                    st.write(f"Reason: {reason}")
                    if passed:
                        if evidence:
                            st.write(f"Evidence snippet: {evidence}")
                    else:
                        if not suggestion:
                            suggestion = _default_fail_suggestion(question_text)
                        st.write(f"Suggested fix: {suggestion}")
            elif pillar_data.get("reason"):
                st.write(pillar_data.get("reason"))
            else:
                st.write("No details returned for this pillar.")

    gen_data = llm_result.get("gen")
    if gen_data:
        st.subheader("GEN Overlay")
        st.write(f"Uses generative AI: {gen_data.get('uses_generative_ai')}")
        gen_score = gen_data.get("score")
        if isinstance(gen_score, (int, float)):
            gen_normalized = int(max(0, min(2, gen_score)) * 50)
            st.write(f"Score: {gen_score} (Normalized from raw: {gen_normalized}/100)")
        else:
            st.write(f"Score: {gen_score}")
        st.write(f"Reason: {gen_data.get('reason')}")

    overall_comment = llm_result.get("overall_comment")
    if overall_comment:
        st.subheader("Overall Comment")
        st.write(overall_comment)


def _render_summary_metrics(report: Dict, files_scanned: int, repo_name: Optional[str]):
    score = report.get("ethical_score", 0)
    issues = report.get("total_issues", 0)
    pillars = len(report.get("focus_pillars", []))

    metric_cols = st.columns(4)
    metric_cols[0].metric("Repository", repo_name or "Local")
    metric_cols[1].metric("Ethical score", f"{score}/100")
    metric_cols[2].metric("Files scanned", files_scanned)
    metric_cols[3].metric("Issues found", issues)


def _render_report_tabs(
    report: Dict,
    files_scanned: int,
    mode: str,
    repo_name: Optional[str],
    analyzed_files: Optional[List[str]] = None,
):
    results_tab, raw_json_tab = st.tabs(["Results", "Raw JSON"])

    with results_tab:
        _render_summary_metrics(report, files_scanned, repo_name)
        st.markdown(_build_summary_response(report, files_scanned, mode))

        if analyzed_files:
            with st.expander(f"Files analyzed ({len(analyzed_files)})", expanded=False):
                for file_path in analyzed_files:
                    st.write(f"- {file_path}")

        st.divider()
        _render_llm_results(report)

    with raw_json_tab:
        st.json(report)


def _build_summary_response(report: Dict, files_scanned: int, mode: str) -> str:
    ethical_score = report.get("ethical_score", 0)
    total_issues = report.get("total_issues", 0)
    focus_pillars = report.get("focus_pillars", [])
    focus_pillar_names = [
        EthicsAnalyzer.PILLARS.get(pillar_id, pillar_id) for pillar_id in focus_pillars
    ]
    return (
        f"Analysis completed in {mode} mode.\n"
        f"Files scanned: {files_scanned}\n"
        f"Focus pillars: {', '.join(focus_pillar_names) if focus_pillar_names else 'N/A'}\n"
        f"Ethical score: {ethical_score}/100\n"
        f"Total issues: {total_issues}"
    )


def _save_report(report: Dict, mode: str, repo_full_name: Optional[str]) -> str:
    os.makedirs("./reports", exist_ok=True)
    repo_name_safe = (
        repo_full_name.replace("/", "_") if repo_full_name else "local_snippet_analysis"
    )
    filename = f"ethics_report_{repo_name_safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_path = os.path.join("./reports", filename)
    with open(save_path, "w", encoding="utf-8") as file_handle:
        json.dump(report, file_handle, indent=2, default=str)
    return save_path


def _analyze_github(
    github_token: str,
    repo_full_name: str,
    selected_pillar_ids: List[str],
    languages: List[str],
) -> Dict:
    connector = None
    try:
        connector = GitHubConnector(access_token=github_token)
        repo = connector.get_repository(repo_full_name)
        if not repo:
            raise ValueError("Repository not found or token lacks permission.")

        code_files = connector.list_code_files(repo, languages=languages or None)
        all_files = [file_path for files in code_files.values() for file_path in files]

        # Fetch ethics-relevant docs (README, CHANGELOG, SECURITY, docs/, .github/, etc.)
        ethics_doc_files = connector.list_ethics_doc_files(repo)

        # Deduplicate: ethics docs first so they appear at the top of the file list
        all_files_set = set(all_files)
        extra_doc_files = [f for f in ethics_doc_files if f not in all_files_set]
        combined_files = extra_doc_files + all_files

        analyzer = EthicsAnalyzer(
            use_llm=True,
            focus_pillars=selected_pillar_ids,
        )

        for file_path in combined_files:
            content = connector.get_file_content(repo, file_path)
            if content:
                analyzer.analyze_file(file_path, content)

        report = analyzer.generate_report(repo_full_name)
        return {
            "report": report,
            "files_scanned": len(combined_files),
            "analyzed_files": combined_files,
            "repo": repo,
            "connector": connector,
        }
    except Exception:
        if connector:
            connector.close()
        raise


def _analyze_local(snippets: Dict[str, str], selected_pillar_ids: List[str]) -> Dict:
    analyzer = EthicsAnalyzer(
        use_llm=True,
        focus_pillars=selected_pillar_ids,
    )

    for file_path, content in snippets.items():
        if content:
            analyzer.analyze_file(file_path, content)

    report = analyzer.generate_report("local/snippet-analysis")
    return {
        "report": report,
        "files_scanned": len(snippets),
        "analyzed_files": sorted(snippets.keys()),
    }


@st.cache_data(ttl=600)
def _load_user_repository_names(github_token: str) -> List[str]:
    connector = None
    try:
        connector = GitHubConnector(access_token=github_token)
        repo_names = [repo.full_name for repo in connector.user.get_repos()]
        repo_names.sort(key=str.lower)
        return repo_names
    finally:
        if connector:
            connector.close()


def main():
    st.set_page_config(page_title="Ethics Analyzer", page_icon="🛡️", layout="wide")
    st.title("🛡️ Ethics Analyzer")
    st.caption("Simple ethics analysis for GitHub repositories or local snippets.")

    with st.sidebar:
        st.header("Settings")
        mode = st.selectbox("Mode", ["github", "local"], index=0)
        default_pillar_names = (
            ["governance"] if "governance" in PILLAR_NAME_TO_ID else []
        )
        selected_pillar_names = st.multiselect(
            "Ethics areas",
            options=list(PILLAR_NAME_TO_ID.keys()),
            default=default_pillar_names,
            help="Select one or more ethics areas to evaluate.",
        )
        if selected_pillar_names:
            with st.expander("What each selected area means", expanded=False):
                for area_name in selected_pillar_names:
                    description = PILLAR_DESCRIPTIONS.get(area_name)
                    if description:
                        st.write(f"- {area_name}: {description}")
        selected_pillar_ids = [
            PILLAR_NAME_TO_ID[name]
            for name in selected_pillar_names
            if name in PILLAR_NAME_TO_ID
        ]
        save_json = st.checkbox("Save JSON report", value=True)

        create_issue = False
        selected_languages: List[str] = []
        github_token = ""
        if mode == "github":
            github_token = st.text_input(
                "GitHub Token",
                value=os.getenv("GITHUB_TOKEN", ""),
                type="password",
            )
            create_issue = st.checkbox("Create GitHub issue if score < 50", value=False)
            selected_languages = st.multiselect(
                "Languages (optional)",
                options=list(GitHubConnector.SUPPORTED_LANGUAGES.keys()),
                default=[],
            )

    repo_full_name = ""
    local_file_name = "app.py"
    local_file_code = 'API_KEY = "abc123xyz456"\nprint("hello")'

    if mode == "github":
        st.subheader("Repository")
        repo_options: List[str] = []
        if github_token:
            with st.spinner("Loading repositories..."):
                repo_options = _load_user_repository_names(github_token)

        if repo_options:
            repo_filter_query = (
                st.text_input(
                    "Filter repositories",
                    placeholder="Type part of owner/repo",
                )
                .strip()
                .lower()
            )

            filtered_repos = [
                name
                for name in repo_options
                if _repo_matches_query(name, repo_filter_query)
            ]

            if filtered_repos:
                repo_full_name = st.selectbox("Select repository", filtered_repos)
            else:
                st.warning("No repositories match the filter.")
        else:
            repo_full_name = st.text_input("Repository (owner/repo)")
    else:
        st.subheader("Local File")
        local_file_name = st.text_input(
            "File name",
            value="app.py",
            help="Paste one file at a time.",
        ).strip()
        local_file_code = st.text_area(
            "Code",
            value='API_KEY = "abc123xyz456"\nprint("hello")',
            height=240,
        )

    run_button = st.button("Analyze", type="primary")
    if not run_button:
        return

    try:
        if not selected_pillar_ids:
            raise ValueError("Select at least one pillar.")

        if mode == "github":
            if not github_token:
                raise ValueError("GitHub token is required in github mode.")
            if not repo_full_name:
                raise ValueError("Repository name is required in github mode.")

            with st.spinner("Analyzing GitHub repository..."):
                result = _analyze_github(
                    github_token=github_token,
                    repo_full_name=repo_full_name,
                    selected_pillar_ids=selected_pillar_ids,
                    languages=selected_languages,
                )

            report = result["report"]
            files_scanned = result["files_scanned"]
            repo = result["repo"]
            connector = result["connector"]

            if create_issue and report.get("ethical_score", 100) < 50:
                create_ethics_issue(repo, report)
                st.success("GitHub issue created successfully.")

            if save_json:
                saved_file = _save_report(
                    report, mode="github", repo_full_name=repo_full_name
                )
                st.success(f"Report saved to: {saved_file}")

            connector.close()
            _render_report_tabs(
                report,
                files_scanned,
                "github",
                repo_full_name,
                analyzed_files=result.get("analyzed_files"),
            )

        else:
            if not local_file_name:
                raise ValueError("File name is required in local mode.")
            if not local_file_code.strip():
                raise ValueError("Code is required in local mode.")

            snippets = {local_file_name: local_file_code}

            with st.spinner("Analyzing local file..."):
                result = _analyze_local(
                    snippets=snippets,
                    selected_pillar_ids=selected_pillar_ids,
                )

            report = result["report"]
            files_scanned = result["files_scanned"]

            if save_json:
                saved_file = _save_report(report, mode="local", repo_full_name=None)
                st.success(f"Report saved to: {saved_file}")

            _render_report_tabs(
                report,
                files_scanned,
                "local",
                None,
                analyzed_files=result.get("analyzed_files"),
            )

    except Exception as error:
        st.error(f"Analysis failed: {error}")


if __name__ == "__main__":
    main()
