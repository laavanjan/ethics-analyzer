from github import Github
from datetime import datetime
import json
import os
from typing import Optional, List, Dict
from github import Auth, Github
from dotenv import load_dotenv
from ethics_analyzer import EthicsAnalyzer, FOCUS_PROFILES

load_dotenv()


class GitHubConnector:
    """Connect to GitHub and fetch repository data for ethics analysis."""

    SUPPORTED_LANGUAGES = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".ts", ".tsx"],
        "java": [".java"],
        "cpp": [".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"],
        "csharp": [".cs"],
        "go": [".go"],
        "rust": [".rs"],
        "php": [".php"],
        "ruby": [".rb"],
        "swift": [".swift"],
        "kotlin": [".kt"],
        "scala": [".scala"],
    }

    def __init__(self, access_token: Optional[str] = None):
        token = access_token or os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError(
                "GitHub token required. Set GITHUB_TOKEN env variable or pass token."
            )

        auth = Auth.Token(token)
        self.github = Github(auth=auth)
        self.user = self.github.get_user()
        print(f"✓ Connected as: {self.user.login}")

    def get_repository(self, repo_full_name: str):
        try:
            repo = self.github.get_repo(repo_full_name)
            print(f"✓ Found repository: {repo.full_name}")
            print(f"  Description: {repo.description}")
            print(f"  Language: {repo.language}")
            print(f"  Stars: {repo.stargazers_count}")
            return repo
        except Exception as e:
            print(f"✗ Error accessing repository: {e}")
            return None

    def get_all_extensions(self) -> List[str]:
        extensions = []
        for lang_extensions in self.SUPPORTED_LANGUAGES.values():
            extensions.extend(lang_extensions)
        return extensions

    def list_code_files(self, repo, languages: Optional[List[str]] = None):
        if languages:
            target_extensions = []
            target_langs = []
            for lang in languages:
                lang_lower = lang.lower()
                if lang_lower in self.SUPPORTED_LANGUAGES:
                    target_extensions.extend(self.SUPPORTED_LANGUAGES[lang_lower])
                    target_langs.append(lang_lower)
            print(
                f"\n🔍 Scanning for {', '.join(target_langs)} files with extensions: {', '.join(target_extensions)}"
            )
        else:
            target_extensions = self.get_all_extensions()
            target_langs = list(self.SUPPORTED_LANGUAGES.keys())
            print(f"\n🔍 Scanning for all supported languages")

        code_files = {lang: [] for lang in target_langs}
        total_files = 0

        try:
            contents = repo.get_contents("")
            while contents:
                file_content = contents.pop(0)
                if file_content.type == "dir":
                    try:
                        contents.extend(repo.get_contents(file_content.path))
                    except Exception:
                        pass
                else:
                    for ext in target_extensions:
                        if file_content.name.endswith(ext):
                            for lang in target_langs:
                                if ext in self.SUPPORTED_LANGUAGES[lang]:
                                    code_files[lang].append(file_content.path)
                                    total_files += 1
                                    print(f"  Found: {file_content.path} ({lang})")
                                    break
                            break
        except Exception as e:
            print(f"✗ Error scanning repository: {e}")

        code_files = {lang: files for lang, files in code_files.items() if files}

        if total_files == 0:
            print(f"\n⚠️  No files found matching the selected criteria")
        else:
            print(f"\n📊 Found {total_files} files across {len(code_files)} languages")
            for lang, files in code_files.items():
                print(f"  {lang}: {len(files)} files")

        return code_files

    def list_python_files(self, repo):
        code_files = self.list_code_files(repo, languages=["python"])
        return code_files.get("python", [])

    def get_file_content(self, repo, file_path: str) -> str:
        try:
            file_content = repo.get_contents(file_path)
            content = file_content.decoded_content.decode("utf-8")
            return content
        except Exception as e:
            print(f"✗ Error reading file {file_path}: {e}")
            return ""

    def close(self):
        self.github.close()
        print("✓ Connection closed")

    def list_my_repositories(self, limit: int = 10, interactive: bool = True):
        repos = list(self.user.get_repos())
        total_repos = len(repos)

        print(
            f"\n📂 Your repositories ({self.user.public_repos} public, {self.user.total_private_repos} private):"
        )
        print(f"   Total: {total_repos} repositories\n")

        offset = 0

        while offset < total_repos:
            end = min(offset + limit, total_repos)
            print(f"Showing {offset + 1}-{end} of {total_repos}:\n")

            for i, repo in enumerate(repos[offset:end], start=offset + 1):
                print(
                    f"  {i}. {repo.full_name} ({repo.language or 'Unknown'}) - {repo.stargazers_count} ⭐"
                )
                print(f"     {repo.description or 'No description'}")

            offset = end

            if interactive and offset < total_repos:
                print(f"\n📄 Showing {end}/{total_repos} repositories")
                response = input("Show more? (yes/no/number): ").strip().lower()

                if response in ["no", "n", "exit", "quit"]:
                    break
                elif response.isdigit():
                    limit = int(response)
                elif response not in ["yes", "y", ""]:
                    break
                print()
            else:
                break

        return repos

    def select_repository_interactive(self):
        repos = self.list_my_repositories(limit=10, interactive=True)

        if not repos:
            print("❌ No repositories found")
            return None

        print("\n" + "=" * 60)
        print("SELECT REPOSITORY TO ANALYZE")
        print("=" * 60)

        while True:
            selection = input(
                "\nEnter repository number (or 'manual' to enter owner/repo): "
            ).strip()

            if selection.lower() == "manual":
                manual_repo = input("Enter repository (format: owner/repo): ").strip()
                return self.get_repository(manual_repo)
            elif selection.isdigit():
                idx = int(selection) - 1
                if 0 <= idx < len(repos):
                    selected_repo = repos[idx]
                    print(f"\n✅ Selected: {selected_repo.full_name}")
                    return selected_repo
                else:
                    print(f"❌ Invalid number. Please enter 1-{len(repos)}")
            elif selection.lower() in ["exit", "quit", "cancel"]:
                print("❌ Cancelled")
                return None
            else:
                print("❌ Invalid input. Enter a number, 'manual', or 'exit'")


def can_create_issue(repo, connector) -> bool:
    if repo.owner.login == connector.user.login:
        return True
    try:
        perms = getattr(repo, "permissions", None)
        if perms:
            if getattr(perms, "admin", False) or getattr(perms, "push", False):
                return True
    except Exception:
        pass
    return False


def create_ethics_issue(repo, report):
    critical_issues = [i for i in report["issues"] if i.severity == "critical"]

    if report["ethical_score"] >= 50:
        print("✅ Ethical score is >= 50 - skipping issue creation")
        return

    issue_title = f"🚨 Ethics Scan: {report['total_issues']} Issues Found (Score: {report['ethical_score']}/100)"
    critical_summary = "\n".join(
        [f"• {i.file_path}:{i.line_number} - {i.message}" for i in critical_issues[:10]]
    )

    issue_body = f"""
## 🤖 Automated Ethics Analysis Report

**Scan Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Repository**: {repo.full_name}
**Ethical Score**: {report['ethical_score']}/100 ⭐
**Total Issues**: {report['total_issues']}
**Critical Issues**: {len(critical_issues)}

### 🚨 CRITICAL ISSUES (Must Fix Immediately)
{critical_summary}

### 📊 SUMMARY
Severity: {report['issues_by_severity']}
By Type: {report['issues_by_type']}

### 📁 Full Report
[Download JSON report](https://github.com/{repo.full_name}/actions) (check artifacts)

### ✅ Next Steps
1. Fix CRITICAL privacy/security issues.
2. Address fairness, transparency, and other gaps noted in the report.
3. Rerun analyzer after fixes.
4. Close this issue when score > 80/100.

**Local testing**: `python github_connector.py`
    """
    try:
        new_issue = repo.create_issue(title=issue_title, body=issue_body.strip())
        print(f"✅ SUCCESS! Created GitHub issue:")
        print(f"   📋 {new_issue.title}")
        print(f"   🔗 {new_issue.html_url}")
        return new_issue
    except Exception as e:
        print(f"❌ Failed to create issue: {e}")
        print("   Check repo permissions or create manually")


def display_issues_paginated(issues: List, page_size: int = 10):
    total = len(issues)
    offset = 0

    while offset < total:
        end = min(offset + page_size, total)
        print(f"\n🔍 ISSUES {offset + 1}-{end} of {total}:")

        for i, issue in enumerate(issues[offset:end], start=offset + 1):
            emoji = {"critical": "🚨", "medium": "⚠️", "low": "📝"}.get(
                issue.severity, "📌"
            )
            print(
                f"\n{i}. {emoji} [{issue.issue_type.upper()}] {issue.file_path}:{issue.line_number}"
            )
            print(f"   {issue.message}")
            print(f"   💡 {issue.suggestion}")

        offset = end

        if offset < total:
            response = input(f"\nShow more issues? (yes/no/number): ").strip().lower()
            if response in ["no", "n", "exit", "quit"]:
                break
            elif response.isdigit():
                page_size = int(response)
            elif response not in ["yes", "y", ""]:
                break
        else:
            print(f"\n✅ Displayed all {total} issues")
            break


def run_ethics_analysis(connector, repo):
    if not repo:
        print("❌ No repository selected")
        return

    # Select ethics focus profile
    print("\nSelect ethics focus:")
    print("1. Responsibility & management (P1–P3)")
    print("2. Data safety and security (P4–P8)")
    print("3. Understanding, accessibility, and societal impact (P9–P11)")
    focus_choice = input("Choice (1-3, default=2): ").strip() or "2"
    focus_pillars = FOCUS_PROFILES.get(focus_choice, FOCUS_PROFILES["2"])

    print("\n" + "=" * 60)
    print("LANGUAGE SELECTION")
    print("=" * 60)
    print("\n🎯 Select languages to scan:")
    print("1. Python only")
    print("2. JavaScript/TypeScript only")
    print("3. All supported languages")
    print("4. Custom selection")

    choice = input("\nYour choice (1-4, default=1): ").strip() or "1"

    if choice == "1":
        languages = ["python"]
    elif choice == "2":
        languages = ["javascript"]
    elif choice == "3":
        languages = None
    elif choice == "4":
        print(
            "\nAvailable: python, javascript, java, cpp, csharp, go, rust, php, ruby, swift, kotlin, scala"
        )
        custom = input("Enter languages (comma-separated): ").strip()
        languages = [lang.strip() for lang in custom.split(",")]
    else:
        languages = ["python"]

    print(f"\n🔍 Running ethics analysis on {repo.full_name}...")

    code_files = connector.list_code_files(repo, languages=languages)
    if not code_files:
        print("❌ No code files found for selected languages")
        return

    all_files = []
    for lang, files in code_files.items():
        all_files.extend(files)

    print(f"\n📊 Analyzing {len(all_files)} files...")

    analyzer = EthicsAnalyzer(
        use_llm=True,
        groq_api_key=os.getenv("GROQ_API_KEY"),
        focus_pillars=focus_pillars,
    )

    for i, file_path in enumerate(all_files, 1):
        print(f"  [{i}/{len(all_files)}] Analyzing {file_path}...")
        content = connector.get_file_content(repo, file_path)
        if content:
            analyzer.analyze_file(file_path, content)

    report = analyzer.generate_report(repo.full_name)

    print(f"\n{'='*60}")
    print(f"📈 ETHICS ANALYSIS REPORT")
    print(f"{'='*60}")
    print(f"Repository: {repo.full_name}")
    print(f"Files scanned: {len(all_files)}")
    print(f"Total issues: {report['total_issues']}")
    print(f"Ethical score: {report['ethical_score']}/100")

    severity_counts = report["issues_by_severity"]
    critical = severity_counts.get("critical", 0)
    if critical > 0:
        print("🚨 CRITICAL: Security/privacy issues detected!")
    elif report["total_issues"] > 20:
        print("⚠️  HIGH: Multiple bias/privacy concerns")
    elif report["total_issues"] > 5:
        print("📊 MEDIUM: Potential improvements needed")
    else:
        print("✅ Good ethical practices detected")

    print(f"\nIssues by severity: {report['issues_by_severity']}")
    print(f"Issues by type: {report['issues_by_type']}")

    # LLM pillar view with reasons and code excerpts
    if report.get("llm_result"):
        print("\n🤖 LLM‑based pillar assessment:")
        pillars_raw = report["llm_result"].get("pillars", {})
        focus_pillars = report.get("focus_pillars", list(pillars_raw.keys()))
        if report["llm_result"].get("evaluation_status") == "insufficient_code":
            print("  status: NOT EVALUATED (insufficient meaningful code)")

        for pid in focus_pillars:
            p = pillars_raw.get(pid, {})
            score = p.get("score")
            verdict = (p.get("verdict") or ("pass" if isinstance(score, (int, float)) and score >= 1 else "fail")).upper()
            print(f"\n  {pid} ({EthicsAnalyzer.PILLARS[pid]}): {verdict}")
            rules_data = p.get("rules", {})
            if rules_data:
                for rule_num in sorted(rules_data.keys(), key=lambda x: int(x)):
                    rule_result = rules_data[rule_num]
                    passed_str = "PASS" if rule_result.get("passed") else "FAIL"
                    print(f"     Rule {rule_num} [{passed_str}]: {rule_result.get('reason', '')}")
            elif p.get("reason"):
                print(f"     reason: {p.get('reason')}")

        gen = report["llm_result"].get("gen")
        if gen:
            print("\n🎨 GEN overlay assessment:")
            print(f"  uses_generative_ai: {gen.get('uses_generative_ai')}")
            print(f"  score: {gen.get('score')}")
            print(f"  reason: {gen.get('reason')}")
        overall_comment = report["llm_result"].get("overall_comment")
        if overall_comment:
            print(f"\nLLM overall comment: {overall_comment}")
    else:
        print("\nℹ️ LLM result not available (check GROQ_API_KEY or llm_client).")

    if report["issues"]:
        display_issues_paginated(report["issues"], page_size=10)

    if report["ethical_score"] < 50:
        if not can_create_issue(repo, connector):
            print(
                "\nℹ️ Ethical score is below 50, "
                "but you are not the owner/collaborator of this repository."
            )
            print("   Skipping automatic issue creation.")
            print("   Share the JSON report with the repo owner if needed.")
        else:
            print("\n🚨 Ethical score is below 50/100 – repository needs attention.")
            create_issue = (
                input("Create GitHub issue with full report? (yes/no): ")
                .strip()
                .lower()
            )
            if create_issue in ["yes", "y"]:
                create_ethics_issue(repo, report)
    else:
        print("\n📝 Ethical score is 50 or above – skipping automatic issue creation.")

    save_report = input("\n💾 Save report to JSON file? (yes/no): ").strip().lower()
    if save_report in ["yes", "y"]:
        filename = (
            f"ethics_report_{repo.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_json = {
            "repository": repo.full_name,
            "scan_date": datetime.now().isoformat(),
            "total_issues": report["total_issues"],
            "ethical_score": report["ethical_score"],
            "issues_by_severity": report["issues_by_severity"],
            "issues_by_type": report["issues_by_type"],
            "issues": [
                {
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "code_snippet": i.code_snippet,
                }
                for i in report["issues"]
            ],
            "llm_result": report.get("llm_result"),
            "focus_pillars": report.get("focus_pillars"),
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report_json, f, indent=2)
        print(f"✅ Report saved to: {filename}")


def analyze_local_code(snippets: Dict[str, str]):
    """
    Run ethics analysis on ad‑hoc code snippets instead of a GitHub repo.
    """
    print("\n" + "=" * 60)
    print("LOCAL CODE ETHICS ANALYSIS")
    print("=" * 60)

    print("\nSelect ethics focus:")
    print("1. Responsibility & management (P1–P3)")
    print("2. Data safety and security (P4–P8)")
    print("3. Understanding, accessibility, and societal impact (P9–P11)")
    focus_choice = input("Choice (1-3, default=2): ").strip() or "2"
    focus_pillars = FOCUS_PROFILES.get(focus_choice, FOCUS_PROFILES["2"])

    analyzer = EthicsAnalyzer(
        use_llm=True,
        groq_api_key=os.getenv("GROQ_API_KEY"),
        focus_pillars=focus_pillars,
    )

    all_files = list(snippets.items())
    print(f"\n📊 Analyzing {len(all_files)} local files...")

    for i, (file_path, content) in enumerate(all_files, 1):
        print(f"  [{i}/{len(all_files)}] Analyzing {file_path}...")
        analyzer.analyze_file(file_path, content)

    report = analyzer.generate_report("local/snippet-analysis")

    print(f"\n{'='*60}")
    print("📈 ETHICS ANALYSIS REPORT (LOCAL)")
    print(f"{'='*60}")
    print(f"Files scanned: {len(all_files)}")
    print(f"Total issues: {report['total_issues']}")
    print(f"Ethical score: {report['ethical_score']}/100")
    print(f"Issues by severity: {report['issues_by_severity']}")
    print(f"Issues by type: {report['issues_by_type']}")

    if report.get("llm_result"):
        print("\n🤖 LLM‑based pillar assessment:")
        pillars_raw = report["llm_result"].get("pillars", {})
        focus_pillars = report.get("focus_pillars", list(pillars_raw.keys()))

        if report["llm_result"].get("evaluation_status") == "insufficient_code":
            print("  status: NOT EVALUATED (insufficient meaningful code)")

        for pid in focus_pillars:
            p = pillars_raw.get(pid, {})
            score = p.get("score")
            verdict = (p.get("verdict") or ("pass" if isinstance(score, (int, float)) and score >= 1 else "fail")).upper()
            print(f"\n  {pid} ({EthicsAnalyzer.PILLARS[pid]}): {verdict}")
            rules_data = p.get("rules", {})
            if rules_data:
                for rule_num in sorted(rules_data.keys(), key=lambda x: int(x)):
                    rule_result = rules_data[rule_num]
                    passed_str = "PASS" if rule_result.get("passed") else "FAIL"
                    print(f"     Rule {rule_num} [{passed_str}]: {rule_result.get('reason', '')}")
            elif p.get("reason"):
                print(f"     reason: {p.get('reason')}")

        gen = report["llm_result"].get("gen")
        if gen:
            print("\n🎨 GEN overlay assessment:")
            print(f"  uses_generative_ai: {gen.get('uses_generative_ai')}")
            print(f"  score: {gen.get('score')}")
            print(f"  reason: {gen.get('reason')}")
        overall_comment = report["llm_result"].get("overall_comment")
        if overall_comment:
            print(f"\nLLM overall comment: {overall_comment}")

    if report["issues"]:
        display_issues_paginated(report["issues"], page_size=10)

    return report


if __name__ == "__main__":
    mode = (
        input(
            "\nSelect mode:\n"
            "1. Analyze GitHub repository\n"
            "2. Analyze pasted/local code\n"
            "Choice (1-2, default=1): "
        ).strip()
        or "1"
    )

    if mode == "2":
        print(
            "\nEnter code snippets to analyze. Type a single line with 'EOF' to finish each file."
        )
        snippets: Dict[str, str] = {}
        while True:
            file_name = input("\nPseudo file name (or just Enter to stop): ").strip()
            if not file_name:
                break
            print(f"Paste code for {file_name}, then type 'EOF' on a new line:")
            lines = []
            while True:
                line = input()
                if line.strip() == "EOF":
                    break
                lines.append(line)
            snippets[file_name] = "\n".join(lines)

        if snippets:
            analyze_local_code(snippets)
        else:
            print("❌ No code provided; exiting.")
    else:
        connector = GitHubConnector()
        print("\n" + "=" * 60)
        print("🛡️ ETHICS CODE ANALYZER")
        print("=" * 60)
        repo = connector.select_repository_interactive()
        if repo:
            run_ethics_analysis(connector, repo)
        connector.close()
        print("\n" + "=" * 60)
        print("✅ Analysis complete! Thank you for using Ethics Code Analyzer.")
        print("=" * 60)
