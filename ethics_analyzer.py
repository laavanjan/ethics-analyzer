from dataclasses import dataclass
from typing import List, Dict, Optional, Any
import re

from llm_client import EthicsLLMClient


# Focus profiles for user selection (moved here from github_connector.py)
FOCUS_PROFILES = {
    "Responsibility & management": ["P1", "P2", "P3"],  #
    "Data safety & security": ["P4", "P5", "P6", "P7", "P8"],  #
    "Understanding, accessibility, impact": [
        "P9",
        "P10",
        "P11",
    ],  # Understanding, accessibility, impact
}

DEFAULT_FOCUS_PROFILE = "Data safety & security"

FOCUS_PROFILE_ALIASES = {
    "1": "Responsibility & management",
    "2": "Data safety & security",
    "3": "Understanding, accessibility, impact",
}


def normalize_focus_profile_name(profile_choice: Optional[str]) -> str:
    if not profile_choice:
        return DEFAULT_FOCUS_PROFILE
    return FOCUS_PROFILE_ALIASES.get(profile_choice, profile_choice)


def resolve_focus_profile(profile_choice: Optional[str]) -> List[str]:
    profile_name = normalize_focus_profile_name(profile_choice)
    return FOCUS_PROFILES.get(profile_name, FOCUS_PROFILES[DEFAULT_FOCUS_PROFILE])


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

    # ---------- 3 SIMPLE QUESTIONS PER PILLAR (passed to LLM for evaluation) ----------

    PILLAR_RULES: Dict[str, List[str]] = {
        "P1": [
            "Is there a clear owner or team responsible for this system?",
            "Is it clearly explained what this system is meant to do?",
            "Can users see what changed over time (version history or changelog)?",
        ],
        "P2": [
            "Does the project mention possible risks or harms?",
            "Are risks grouped by level (for example low, medium, high)?",
            "Is there a plan to review risks again after major changes?",
        ],
        "P3": [
            "Is there a human review or approval step?",
            "Can a person stop, override, or roll back the system if needed?",
            "Is there a clear support or escalation path for users?",
        ],
        "P4": [
            "Does the system collect only the data it really needs?",
            "Is consent or privacy notice information clearly provided?",
            "Is there a clear policy for data deletion or retention?",
        ],
        "P5": [
            "Does the project acknowledge fairness or bias concerns?",
            "Is there any fairness testing or measurement approach?",
            "Are there actions to reduce unfair outcomes?",
        ],
        "P6": [
            "Are users clearly told they are interacting with AI?",
            "Are system limits or failure cases explained in plain language?",
            "Is there basic information about the model or data source?",
        ],
        "P7": [
            "Are safety guardrails defined for harmful or risky outputs?",
            "Has the system been tested on edge cases or stressful inputs?",
            "Does it have a safe fallback for risky or unsupported requests?",
        ],
        "P8": [
            "Are secrets and keys kept out of source code?",
            "Are access control and input validation checks in place?",
            "Are there protections against abuse (like rate limits)?",
        ],
        "P9": [
            "Is there a clear README or system overview?",
            "Is there documentation for data or model behavior?",
            "Can important decisions be traced through logs?",
        ],
        "P10": [
            "Are accessibility needs or standards considered?",
            "Are error messages easy to understand for normal users?",
            "Does the interface avoid misleading or deceptive patterns?",
        ],
        "P11": [
            "Is there a clear positive social purpose for this system?",
            "Are possible misuse risks or social harms discussed?",
            "Is there any plan to reduce misuse or harmful impact?",
        ],
    }

    MIN_EFFECTIVE_LINES_PER_FILE = 3
    MIN_EFFECTIVE_LINES_FOR_REPO_EVAL = 8
    QUESTION_PASS_SCORE_MAP = {
        0: 0,
        1: 50,
        2: 75,
        3: 100,
    }

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
            insufficient_reason = (
                "Not enough meaningful code to evaluate ethics reliably."
            )
            llm_result = {
                "evaluation_status": "insufficient_code",
                "pillars": self._build_placeholder_pillars(insufficient_reason),
                "gen": {
                    "uses_generative_ai": False,
                    "score": 0,
                    "reason": insufficient_reason,
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
                            pillar_entry = pillar_scores[p]
                            question_results = pillar_entry.get("rules", {})

                            if isinstance(question_results, dict) and question_results:
                                passed_count = sum(
                                    1
                                    for question in question_results.values()
                                    if isinstance(question, dict)
                                    and question.get("passed") is True
                                )
                                llm_total += self.QUESTION_PASS_SCORE_MAP.get(
                                    passed_count, 0
                                )
                            else:
                                s_raw = pillar_entry.get("score", 0)
                                s = s_raw if isinstance(s_raw, (int, float)) else 0
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

    @staticmethod
    def count_passed_questions(pillar_entry: Optional[Dict[str, Any]]) -> Optional[int]:
        if not isinstance(pillar_entry, dict):
            return None

        question_results = pillar_entry.get("rules", {})
        if not isinstance(question_results, dict) or not question_results:
            return None

        return sum(
            1
            for question in question_results.values()
            if isinstance(question, dict) and question.get("passed") is True
        )

    @classmethod
    def get_pillar_status_label(cls, pillar_entry: Optional[Dict[str, Any]]) -> str:
        passed_count = cls.count_passed_questions(pillar_entry)
        if passed_count is None:
            return "NOT EVALUATED"
        if passed_count == 0:
            return "FAIL"
        if passed_count == 3:
            return "STRONG PASS"
        return "PARTIAL PASS"

    def _build_placeholder_pillars(self, reason: str) -> Dict[str, Dict[str, Any]]:
        placeholders: Dict[str, Dict[str, Any]] = {}
        for pillar_id in self.focus_pillars:
            rule_reasons = {
                str(index): {"passed": False, "reason": reason}
                for index, _ in enumerate(self.PILLAR_RULES.get(pillar_id, []), start=1)
            }
            placeholders[pillar_id] = {
                "score": None,
                "verdict": "not_evaluated",
                "rules": rule_reasons,
            }
        return placeholders
