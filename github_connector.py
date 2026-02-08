from github import Github
from datetime import datetime
import json
import os
from typing import Optional
from github import Auth, Github
from dotenv import load_dotenv
from ethics_analyzer import EthicsAnalyzer
load_dotenv()

class GitHubConnector:
    """Connect to GitHub and fetch repository data for ethics analysis."""
    
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
    
    def list_python_files(self, repo):
        """
        List all Python files in a repository.
        
        Args:
            repo: Repository object
            
        Returns:
            List of file paths
        """
        python_files = []
        contents = repo.get_contents("")
        
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo.get_contents(file_content.path))
            elif file_content.name.endswith('.py'):
                python_files.append(file_content.path)
                print(f"  Found: {file_content.path}")
        
        return python_files
    
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

    def list_my_repositories(self, limit: int = 10):
        """
        List your repositories.
        
        Args:
            limit: Number of repositories to show
        """
        repos = self.user.get_repos()
        print(f"\n📂 Your repositories ({self.user.public_repos} public, {self.user.total_private_repos} private):")
        
        for i, repo in enumerate(repos, 1):
            if i > limit:
                break
            print(f"  {i}. {repo.full_name} ({repo.language}) - {repo.stargazers_count} ⭐")
            print(f"     {repo.description or 'No description'}")
        
        return list(repos)[:limit]

def create_ethics_issue(repo, report):
    """
    Automatically create GitHub issue for critical ethics findings.
    """
    critical_issues = [i for i in report['issues'] if i.severity == 'critical']
    
    if not critical_issues:
        print("✅ No critical issues - skipping issue creation")
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
        # Create the issue
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


if __name__ == "__main__":
    connector = GitHubConnector()
    
    # Analyze Deepminders/DoconAI (your successful repo)
    repo_name = "laavanjan/Youtube_comment_analysis_end_to_end"
    repo = connector.get_repository(repo_name)
    
    if repo:
        print(f"\n🔍 Running ethics analysis on {repo.full_name}...")
        
        analyzer = EthicsAnalyzer()
        python_files = connector.list_python_files(repo)
        
        print(f"\n📊 Analyzing {len(python_files)} Python files...")
        
        # Analyze first 5 files for quick test (remove limit for full scan)
        for i, file_path in enumerate(python_files):
            print(f"  Analyzing {file_path}...")
            content = connector.get_file_content(repo, file_path)
            analyzer.analyze_file(file_path, content)
        
        # Generate report
        report = analyzer.generate_report()
        print(f"\n{'='*60}")
        print(f"📈 ETHICS ANALYSIS REPORT")
        print(f"{'='*60}")
        print(f"Repository: {repo.full_name}")
        print(f"Files scanned: {len(python_files[:5])}")
        print(f"Total issues: {report['total_issues']}")
        print(f"Ethical score: {report['ethical_score']}/100")
        # AUTO-CREATE GITHUB ISSUE (uncomment the line below to enable)
        create_ethics_issue(repo, report)


        # Fixed summary
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

        # Show TOP 10 issues
        print(f"\n🔍 TOP ISSUES (showing first 10):")
        for i, issue in enumerate(report['issues'][:10], 1):
            emoji = {'critical': '🚨', 'medium': '⚠️', 'low': '📝'}.get(issue.severity, '📌')
            print(f"{i}. {emoji} [{issue.issue_type.upper()}] {issue.file_path}:{issue.line_number}")
            print(f"   {issue.message}")
            print(f"   💡 {issue.suggestion}")
            print()

    
    connector.close()


