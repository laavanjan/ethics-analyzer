from github import Github
from datetime import datetime
import json
import os
from typing import Optional, List, Dict
from github import Auth, Github
from dotenv import load_dotenv
from ethics_analyzer import EthicsAnalyzer
load_dotenv()


class GitHubConnector:
    """Connect to GitHub and fetch repository data for ethics analysis."""
    
    # Supported file extensions for different languages
    SUPPORTED_LANGUAGES = {
        'python': ['.py'],
        'javascript': ['.js', '.jsx', '.ts', '.tsx'],
        'java': ['.java'],
        'cpp': ['.cpp', '.cc', '.cxx', '.c', '.h', '.hpp'],
        'csharp': ['.cs'],
        'go': ['.go'],
        'rust': ['.rs'],
        'php': ['.php'],
        'ruby': ['.rb'],
        'swift': ['.swift'],
        'kotlin': ['.kt'],
        'scala': ['.scala']
    }
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize GitHub connection.
        
        Args:
            access_token: GitHub personal access token. 
                         If None, reads from GITHUB_TOKEN env variable.
        """
        token = access_token or os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN env variable or pass token.")
        
        auth = Auth.Token(token)
        self.github = Github(auth=auth)
        self.user = self.github.get_user()
        print(f"✓ Connected as: {self.user.login}")
    
    def get_repository(self, repo_full_name: str):
        """
        Fetch a repository object.
        
        Args:
            repo_full_name: Repository in format 'owner/repo'
            
        Returns:
            Repository object
        """
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
        """Get all supported file extensions."""
        extensions = []
        for lang_extensions in self.SUPPORTED_LANGUAGES.values():
            extensions.extend(lang_extensions)
        return extensions
    
    def list_code_files(self, repo, languages: Optional[List[str]] = None):
        """
        List all code files in a repository (supports multiple languages).
        
        Args:
            repo: Repository object
            languages: List of languages to scan. If None, scans all supported languages.
                      Options: 'python', 'javascript', 'java', 'cpp', 'csharp', 'go', etc.
        
        Returns:
            Dictionary with file paths grouped by language
        """
        # Determine which extensions to look for
        if languages:
            # Only get extensions for selected languages
            target_extensions = []
            target_langs = []
            for lang in languages:
                lang_lower = lang.lower()
                if lang_lower in self.SUPPORTED_LANGUAGES:
                    target_extensions.extend(self.SUPPORTED_LANGUAGES[lang_lower])
                    target_langs.append(lang_lower)
            
            print(f"\n🔍 Scanning for {', '.join(target_langs)} files with extensions: {', '.join(target_extensions)}")
        else:
            # Scan all languages
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
                    except:
                        pass  # Skip directories we can't access
                else:
                    # Check if file matches any of the TARGET extensions
                    for ext in target_extensions:
                        if file_content.name.endswith(ext):
                            # Find which language this extension belongs to
                            for lang in target_langs:
                                if ext in self.SUPPORTED_LANGUAGES[lang]:
                                    code_files[lang].append(file_content.path)
                                    total_files += 1
                                    print(f"  Found: {file_content.path} ({lang})")
                                    break
                            break  # Stop checking other extensions once we found a match
        
        except Exception as e:
            print(f"✗ Error scanning repository: {e}")
        
        # Remove empty languages
        code_files = {lang: files for lang, files in code_files.items() if files}
        
        if total_files == 0:
            print(f"\n⚠️  No files found matching the selected criteria")
        else:
            print(f"\n📊 Found {total_files} files across {len(code_files)} languages")
            for lang, files in code_files.items():
                print(f"  {lang}: {len(files)} files")
        
        return code_files
    
    def list_python_files(self, repo):
        """
        List all Python files in a repository (legacy method).
        
        Args:
            repo: Repository object
            
        Returns:
            List of file paths
        """
        code_files = self.list_code_files(repo, languages=['python'])
        return code_files.get('python', [])
    
    def get_file_content(self, repo, file_path: str) -> str:
        """
        Fetch the content of a specific file.
        
        Args:
            repo: Repository object
            file_path: Path to file in repository
            
        Returns:
            File content as string
        """
        try:
            file_content = repo.get_contents(file_path)
            content = file_content.decoded_content.decode('utf-8')
            return content
        except Exception as e:
            print(f"✗ Error reading file {file_path}: {e}")
            return ""
    
    def close(self):
        """Close the GitHub connection."""
        self.github.close()
        print("✓ Connection closed")

    def list_my_repositories(self, limit: int = 10, interactive: bool = True):
        """
        List your repositories with pagination.
        
        Args:
            limit: Number of repositories to show per page
            interactive: If True, allows user to request more repos
            
        Returns:
            List of repository objects
        """
        repos = list(self.user.get_repos())
        total_repos = len(repos)
        
        print(f"\n📂 Your repositories ({self.user.public_repos} public, {self.user.total_private_repos} private):")
        print(f"   Total: {total_repos} repositories\n")
        
        offset = 0
        
        while offset < total_repos:
            # Show current batch
            end = min(offset + limit, total_repos)
            print(f"Showing {offset + 1}-{end} of {total_repos}:\n")
            
            for i, repo in enumerate(repos[offset:end], start=offset + 1):
                print(f"  {i}. {repo.full_name} ({repo.language or 'Unknown'}) - {repo.stargazers_count} ⭐")
                print(f"     {repo.description or 'No description'}")
            
            offset = end
            
            # Ask if user wants more
            if interactive and offset < total_repos:
                print(f"\n📄 Showing {end}/{total_repos} repositories")
                response = input("Show more? (yes/no/number): ").strip().lower()
                
                if response in ['no', 'n', 'exit', 'quit']:
                    break
                elif response.isdigit():
                    limit = int(response)
                elif response not in ['yes', 'y', '']:
                    break
                print()  # Blank line for readability
            else:
                break
        
        return repos

    def select_repository_interactive(self):
        """
        Interactively select a repository from your list.
        
        Returns:
            Selected repository object or None
        """
        repos = self.list_my_repositories(limit=10, interactive=True)
        
        if not repos:
            print("❌ No repositories found")
            return None
        
        print("\n" + "="*60)
        print("SELECT REPOSITORY TO ANALYZE")
        print("="*60)
        
        while True:
            selection = input("\nEnter repository number (or 'manual' to enter owner/repo): ").strip()
            
            if selection.lower() == 'manual':
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
            
            elif selection.lower() in ['exit', 'quit', 'cancel']:
                print("❌ Cancelled")
                return None
            
            else:
                print("❌ Invalid input. Enter a number, 'manual', or 'exit'")


def can_create_issue(repo, connector) -> bool:
    """Return True if the current user can reasonably create issues on this repo."""
    # Fast path: you own the repo
    if repo.owner.login == connector.user.login:
        return True

    # If permissions object is available, check write/admin
    try:
        perms = getattr(repo, "permissions", None)
        if perms:
            if getattr(perms, "admin", False) or getattr(perms, "push", False):
                return True
    except Exception:
        pass

    # Otherwise assume no permission
    return False


def create_ethics_issue(repo, report):
    """
    Automatically create GitHub issue for low ethical score.
    """
    critical_issues = [i for i in report['issues'] if i.severity == 'critical']
    
    if report['ethical_score'] >= 50:
        print("✅ Ethical score is >= 50 - skipping issue creation")
        return
    
    # Issue title and body
    issue_title = f"🚨 Ethics Scan: {report['total_issues']} Issues Found (Score: {report['ethical_score']}/100)"
    
    critical_summary = "\n".join([f"• {i.file_path}:{i.line_number} - {i.message}" for i in critical_issues[:10]])
    
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
1. **Fix CRITICAL privacy issues** (hardcoded credentials)
2. Review `{len([i for i in report['issues'] if i.issue_type == 'gender'])}` gender bias instances  
3. Rerun analyzer after fixes
4. Close this issue when score > 80/100

**Local testing**: `python github_connector.py`
    """

    try:
        new_issue = repo.create_issue(
            title=issue_title,
            body=issue_body.strip()
        )
        print(f"✅ SUCCESS! Created GitHub issue:")
        print(f"   📋 {new_issue.title}")
        print(f"   🔗 {new_issue.html_url}")
        return new_issue
    except Exception as e:
        print(f"❌ Failed to create issue: {e}")
        print("   Check repo permissions or create manually")


def display_issues_paginated(issues: List, page_size: int = 10):
    """Display issues with pagination."""
    total = len(issues)
    offset = 0
    
    while offset < total:
        end = min(offset + page_size, total)
        print(f"\n🔍 ISSUES {offset + 1}-{end} of {total}:")
        
        for i, issue in enumerate(issues[offset:end], start=offset + 1):
            emoji = {'critical': '🚨', 'medium': '⚠️', 'low': '📝'}.get(issue.severity, '📌')
            print(f"\n{i}. {emoji} [{issue.issue_type.upper()}] {issue.file_path}:{issue.line_number}")
            print(f"   {issue.message}")
            print(f"   💡 {issue.suggestion}")
        
        offset = end
        
        if offset < total:
            response = input(f"\nShow more issues? (yes/no/number): ").strip().lower()
            if response in ['no', 'n', 'exit', 'quit']:
                break
            elif response.isdigit():
                page_size = int(response)
            elif response not in ['yes', 'y', '']:
                break
        else:
            print(f"\n✅ Displayed all {total} issues")
            break


def run_ethics_analysis(connector, repo):
    """Run complete ethics analysis on a repository."""
    
    if not repo:
        print("❌ No repository selected")
        return
    
    # Choose which languages to scan
    print("\n" + "="*60)
    print("LANGUAGE SELECTION")
    print("="*60)
    print("\n🎯 Select languages to scan:")
    print("1. Python only")
    print("2. JavaScript/TypeScript only")
    print("3. All supported languages")
    print("4. Custom selection")
    
    choice = input("\nYour choice (1-4, default=1): ").strip() or '1'
    
    if choice == '1':
        languages = ['python']
    elif choice == '2':
        languages = ['javascript']
    elif choice == '3':
        languages = None  # Scan all
    elif choice == '4':
        print("\nAvailable: python, javascript, java, cpp, csharp, go, rust, php, ruby, swift, kotlin, scala")
        custom = input("Enter languages (comma-separated): ").strip()
        languages = [lang.strip() for lang in custom.split(',')]
    else:
        languages = ['python']  # Default
    
    print(f"\n🔍 Running ethics analysis on {repo.full_name}...")
    
    # Scan for code files
    code_files = connector.list_code_files(repo, languages=languages)
    
    if not code_files:
        print("❌ No code files found for selected languages")
        return
    
    # Flatten all files into single list
    all_files = []
    for lang, files in code_files.items():
        all_files.extend(files)
    
    print(f"\n📊 Analyzing {len(all_files)} files...")
    
    # Initialize analyzer
    analyzer = EthicsAnalyzer()
    
    # Analyze files with progress
    for i, file_path in enumerate(all_files, 1):
        print(f"  [{i}/{len(all_files)}] Analyzing {file_path}...")
        content = connector.get_file_content(repo, file_path)
        if content:
            analyzer.analyze_file(file_path, content)
    
    # Generate report
    report = analyzer.generate_report()
    
    print(f"\n{'='*60}")
    print(f"📈 ETHICS ANALYSIS REPORT")
    print(f"{'='*60}")
    print(f"Repository: {repo.full_name}")
    print(f"Files scanned: {len(all_files)}")
    print(f"Total issues: {report['total_issues']}")
    print(f"Ethical score: {report['ethical_score']}/100")
    
    # Severity assessment
    severity_counts = report['issues_by_severity']
    critical = severity_counts.get('critical', 0)
    if critical > 0:
        print("🚨 CRITICAL: Security/privacy issues detected!")
    elif report['total_issues'] > 20:
        print("⚠️  HIGH: Multiple bias/privacy concerns")
    elif report['total_issues'] > 5:
        print("📊 MEDIUM: Potential improvements needed")
    else:
        print("✅ Good ethical practices detected")
    
    print(f"\nIssues by severity: {report['issues_by_severity']}")
    print(f"Issues by type: {report['issues_by_type']}")
    
    # Display issues with pagination
    if report['issues']:
        display_issues_paginated(report['issues'], page_size=10)
    
    # Ask about creating GitHub issue when ethical score is low
    if report['ethical_score'] < 50:
        if not can_create_issue(repo, connector):
            print("\nℹ️ Ethical score is below 50, "
                  "but you are not the owner/collaborator of this repository.")
            print("   Skipping automatic issue creation.")
            print("   Share the JSON report with the repo owner if needed.")
        else:
            print("\n🚨 Ethical score is below 50/100 – repository needs attention.")
            create_issue = input("Create GitHub issue with full report? (yes/no): ").strip().lower()
            if create_issue in ['yes', 'y']:
                create_ethics_issue(repo, report)
    else:
        print("\n📝 Ethical score is 50 or above – skipping automatic issue creation.")
    
    # Save report to JSON
    save_report = input("\n💾 Save report to JSON file? (yes/no): ").strip().lower()
    if save_report in ['yes', 'y']:
        filename = f"ethics_report_{repo.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_json = {
            'repository': repo.full_name,
            'scan_date': datetime.now().isoformat(),
            'total_issues': report['total_issues'],
            'ethical_score': report['ethical_score'],
            'issues_by_severity': report['issues_by_severity'],
            'issues_by_type': report['issues_by_type'],
            'issues': [
                {
                    'file_path': i.file_path,
                    'line_number': i.line_number,
                    'issue_type': i.issue_type,
                    'severity': i.severity,
                    'message': i.message,
                    'suggestion': i.suggestion,
                    'code_snippet': i.code_snippet
                } for i in report['issues']
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_json, f, indent=2)
        
        print(f"✅ Report saved to: {filename}")


if __name__ == "__main__":
    connector = GitHubConnector()
    
    print("\n" + "="*60)
    print("🛡️ ETHICS CODE ANALYZER")
    print("="*60)
    
    # Interactive repository selection
    repo = connector.select_repository_interactive()
    
    if repo:
        # Run ethics analysis
        run_ethics_analysis(connector, repo)
    
    connector.close()
    
    print("\n" + "="*60)
    print("✅ Analysis complete! Thank you for using Ethics Code Analyzer.")
    print("="*60)
