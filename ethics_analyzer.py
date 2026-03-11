from dataclasses import dataclass
from typing import List, Dict, Optional, Any
import re

from llm_client import EthicsLLMClient


# Focus profiles for user selection (moved here from github_connector.py)
FOCUS_PROFILES = {
    "1": ["P1", "P2", "P3"],  # Responsibility & management
    "2": ["P4", "P5", "P6", "P7", "P8"],  # Data safety & security
    "3": ["P9", "P10", "P11"],  # Understanding, accessibility, impact
}


# ---------- Data structures ----------


@dataclass
class EthicsIssue:
    file_path: str
    line_number: int
    issue_type: str  # e.g. "governance", "privacy", "fairness"
    severity: str  # "critical" | "high" | "medium" | "low"
    message: str
    suggestion: str
    code_snippet: str = ""


class EthicsAnalyzer:
    """
    Ethics analyzer aligned with P1–P11 primary controls and GEN/REL overlays.
    - Heuristic rules mark controls satisfied/unsatisfied from code patterns.
    - Groq LLM evaluates repo against selected pillars (P1–P11) and GEN overlay
      using code snippets.
    """

    # ---------- PRIMARY PILLARS (P1–P11) ----------

    PILLARS = {
        "P1": "governance",
        "P2": "risk",
        "P3": "human_oversight",
        "P4": "privacy",
        "P5": "fairness",
        "P6": "transparency",
        "P7": "safety",
        "P8": "security",
        "P9": "documentation",
        "P10": "accessibility",
        "P11": "societal",
    }

    # ---------- 3 RULES PER PILLAR (passed to LLM for evaluation) ----------

    PILLAR_RULES: Dict[str, List[str]] = {
        "P1": [
            "Code or docs identify an owner, responsible team, or contact person.",
            "There is a stated purpose, scope, or description of what the system does.",
            "Version history, changelog, or change notes are present.",
        ],
        "P2": [
            "Risk, harm, impact, or threat terms appear in code or documentation.",
            "A risk level or classification (e.g. low/medium/high) is mentioned.",
            "There is a trigger or mention of re-assessment after model or data changes.",
        ],
        "P3": [
            "A human review, approval, or sign-off step is present.",
            "A manual override, rollback, or fallback mechanism exists.",
            "A user escalation, support, or recourse path is available.",
        ],
        "P4": [
            "No unnecessary personal data is collected (minimal data fields).",
            "Consent, legal basis, or privacy notice language is present.",
            "Data retention, deletion, or expiry handling is implemented.",
        ],
        "P5": [
            "Protected groups, bias, or fairness terms are acknowledged.",
            "A bias testing plan, test dataset, or fairness metric is referenced.",
            "Mitigation actions or fairness improvements are documented.",
        ],
        "P6": [
            "Users are informed that they are interacting with AI.",
            "Limitations, failure modes, or disclaimers are documented.",
            "Model or data source information is available.",
        ],
        "P7": [
            "Safety constraints, harmful output filters, or safety requirements are defined.",
            "Edge-case, adversarial, or stress testing is present.",
            "A safe fallback or deny response for risky or out-of-scope inputs exists.",
        ],
        "P8": [
            "No hard-coded secrets, tokens, or passwords appear in code.",
            "Authentication, authorization, or input validation is implemented.",
            "Rate limiting, abuse detection, or anomaly controls are present.",
        ],
        "P9": [
            "A README, system description, or overview document exists.",
            "Data or model documentation is available.",
            "Logging or decision traceability is implemented.",
        ],
        "P10": [
            "Accessibility requirements or standards (e.g. WCAG) are referenced.",
            "Error messages and UI feedback are clear and informative.",
            "No deceptive UX patterns (dark patterns) are present.",
        ],
        "P11": [
            "An intended social benefit or positive societal purpose is stated.",
            "Potential societal harms or misuse risks are identified.",
            "Dual-use risk or misuse assessment is documented.",
        ],
    }

    MIN_EFFECTIVE_LINES_PER_FILE = 3
    MIN_EFFECTIVE_LINES_FOR_REPO_EVAL = 8

    def __init__(
        self,
        use_llm: bool = False,
        groq_api_key: Optional[str] = None,
        focus_pillars: Optional[List[str]] = None,
    ):
        # which pillars the user wants (P1–P11)
        self.focus_pillars = focus_pillars or list(self.PILLARS.keys())

        # issues
        self.issues: List[EthicsIssue] = []

        # LLM integration
        self.use_llm = use_llm
        self.llm_client = EthicsLLMClient(groq_api_key) if use_llm else None
        self._repo_snippets: List[str] = []  # accumulated code snippets for LLM
        self._effective_lines_total = 0
        self._files_with_enough_code = 0

    # ---------- Public API called from github_connector ----------

    def analyze_file(self, file_path: str, content: str):
        """
        1) Run lightweight heuristic checks.
        2) Accumulate truncated snippet for LLM P1–P11/GEN analysis.
        """
        lowered = content.lower()
        effective_lines = self._count_effective_lines(content)
        self._effective_lines_total += effective_lines

        if effective_lines < self.MIN_EFFECTIVE_LINES_PER_FILE:
            # Too little signal to evaluate ethics reliably for this file.
            return

        self._files_with_enough_code += 1

        # Relaxed rule: flag only likely real secret assignments (avoid noisy matches)
        if re.search(
            r"(api[_-]?key|secret[_-]?key|access[_-]?token)\s*=\s*['\"][^'\"]{12,}['\"]",
            lowered,
        ):
            self._add_issue(
                file_path=file_path,
                line_number=1,
                issue_type="security",
                severity="high",
                message="Possible hard‑coded secret detected.",
                suggestion="Move secrets to env vars or secret manager; rotate exposed keys.",
                code_snippet="...api_key = '***'...",
            )

        # Accumulate snippet for LLM – short, so LLM can quote it back
        snippet = content[:500]
        self._repo_snippets.append(f"# File: {file_path}\n{snippet}")

    def generate_report(self, repo_full_name: str = "unknown/repo") -> Dict:
        """
        Compute ethics score, derive overlays, and optionally fuse Groq LLM
        P1–P11 + GEN scores, restricted to focus_pillars.
        """
        # Baseline score — replaced by LLM pillar results when available
        ethical_score = 50.0

        issues_by_severity: Dict[str, int] = {}
        issues_by_type: Dict[str, int] = {}
        for issue in self.issues:
            issues_by_severity[issue.severity] = (
                issues_by_severity.get(issue.severity, 0) + 1
            )
            issues_by_type[issue.issue_type] = (
                issues_by_type.get(issue.issue_type, 0) + 1
            )

        # LLM evaluation for selected pillars + GEN overlay
        llm_result = None
        if (
            self._files_with_enough_code == 0
            or self._effective_lines_total < self.MIN_EFFECTIVE_LINES_FOR_REPO_EVAL
        ):
            llm_result = {
                "evaluation_status": "insufficient_code",
                "pillars": {},
                "gen": {
                    "uses_generative_ai": False,
                    "score": 0,
                    "reason": "Not enough meaningful code to evaluate ethics reliably.",
                },
                "overall_comment": (
                    "Skipped detailed ethics evaluation: repository has too little meaningful code "
                    "(e.g., very short snippets/files)."
                ),
            }

        if self.use_llm and self.llm_client:
            if llm_result is None:
                summary_text = "\n\n".join(self._repo_snippets)
                llm_result = self.llm_client.evaluate_repo(
                    repo_name=repo_full_name,
                    files_summary=summary_text,
                    focus_pillars=self.focus_pillars,
                    pillar_rules=self.PILLAR_RULES,
                )

            # Fuse P1–P11 scores: 0/1/2 → 0/50/100 and average with heuristic score
            if llm_result.get("evaluation_status") != "insufficient_code":
                pillar_scores = llm_result.get("pillars", {})
                if pillar_scores:
                    llm_total = 0.0
                    count = 0
                    for p in self.focus_pillars:
                        if p in pillar_scores:
                            s = pillar_scores[p].get("score", 0)
                            llm_total += max(0, min(2, s)) * 50
                            count += 1
                    if count:
                        llm_score = llm_total / count

                        # Optional: blend GEN score if generative AI is used
                        gen_info = llm_result.get("gen")
                        if gen_info and gen_info.get("uses_generative_ai"):
                            gen_raw = max(0, min(2, gen_info.get("score", 0)))
                            gen_score = gen_raw * 50  # 0/1/2 → 0/50/100
                            llm_score = (llm_score + gen_score) / 2.0

                        ethical_score = round(llm_score, 1)

        return {
            "ethical_score": ethical_score,
            "total_issues": len(self.issues),
            "issues_by_severity": issues_by_severity,
            "issues_by_type": issues_by_type,
            "issues": self.issues,
            "llm_result": llm_result,
            "focus_pillars": self.focus_pillars,
        }

    # ---------- Internal helpers ----------

    def _add_issue(
        self,
        file_path: str,
        line_number: int,
        issue_type: str,
        severity: str,
        message: str,
        suggestion: str,
        code_snippet: str = "",
    ):
        self.issues.append(
            EthicsIssue(
                file_path=file_path,
                line_number=line_number,
                issue_type=issue_type,
                severity=severity,
                message=message,
                suggestion=suggestion,
                code_snippet=code_snippet,
            )
        )

    def _count_effective_lines(self, content: str) -> int:
        count = 0
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith("//"):
                continue
            count += 1
        return count
