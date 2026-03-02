from dataclasses import dataclass, field
from typing import List, Dict, Optional
import re

from llm_client import EthicsLLMClient


# ---------- Data structures ----------

@dataclass
class EthicsIssue:
    file_path: str
    line_number: int
    issue_type: str          # e.g. "governance", "privacy", "fairness"
    severity: str            # "critical" | "high" | "medium" | "low"
    message: str
    suggestion: str
    code_snippet: str = ""


@dataclass
class ControlStatus:
    control_id: str          # e.g. "GOV-01"
    pillar: str              # e.g. "P1"
    name: str                # short description
    satisfied: bool
    evidence_files: List[str] = field(default_factory=list)
    notes: Optional[str] = None


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

    # Subset of PRIMARY controls per pillar (expand later)
    PRIMARY_CONTROLS = {
        # P1 Governance
        "GOV-01": ("P1", "Ownership & accountability"),
        "GOV-02": ("P1", "Documented purpose, scope, limits"),
        "GOV-05": ("P1", "Human oversight plan"),
        "GOV-06": ("P1", "Incident response / escalation"),
        "GOV-08": ("P1", "Change management / versioning"),

        # P2 Risk
        "RISK-01": ("P2", "System context captured"),
        "RISK-02": ("P2", "Risk classification"),
        "RISK-03": ("P2", "Ethical impact assessment"),
        "RISK-06": ("P2", "Reassessment triggers"),

        # P3 Human Oversight
        "HUMO-01": ("P3", "Oversight roles defined"),
        "HUMO-03": ("P3", "User recourse process"),

        # P4 Privacy
        "PRIV-01": ("P4", "Data minimization"),
        "PRIV-02": ("P4", "Lawful basis / consent"),
        "PRIV-03": ("P4", "Notice & transparency"),
        "PRIV-04": ("P4", "Retention & deletion"),
        "PRIV-05": ("P4", "Access control"),
        "PRIV-06": ("P4", "Data provenance"),
        "PRIV-08": ("P4", "De-identification evaluation"),

        # P5 Fairness
        "FAIR-01": ("P5", "Protected groups considered"),
        "FAIR-02": ("P5", "Bias testing plan"),
        "FAIR-03": ("P5", "Bias testing executed"),
        "FAIR-04": ("P5", "Mitigation documented"),

        # P6 Transparency
        "TRAN-01": ("P6", "User-facing AI disclosure"),
        "TRAN-02": ("P6", "Limitations & failure modes"),
        "TRAN-04": ("P6", "Model/dataset documentation"),

        # P7 Safety
        "SAFE-01": ("P7", "Safety requirements & harms"),
        "SAFE-02": ("P7", "Edge-case / stress testing"),
        "SAFE-04": ("P7", "Safe fallback behaviour"),

        # P8 Security
        "SEC-01": ("P8", "Threat model"),
        "SEC-02": ("P8", "Prompt injection / exfil"),
        "SEC-03": ("P8", "Secure SDLC / secrets"),
        "SEC-04": ("P8", "Abuse reporting / rate limit"),

        # P9 Documentation
        "DOC-01": ("P9", "System description pack"),
        "DOC-02": ("P9", "Dataset documentation"),
        "DOC-03": ("P9", "Model card"),
        "DOC-04": ("P9", "Decision traceability"),

        # P10 Accessibility
        "ACC-01": ("P10", "Accessibility requirements"),
        "ACC-03": ("P10", "Human‑factors hazards"),
        "ACC-07": ("P10", "Avoid dark patterns"),

        # P11 Societal
        "SOC-01": ("P11", "Intended societal benefit"),
        "SOC-02": ("P11", "Societal harms identified"),
        "SOC-06": ("P11", "Dual‑use / misuse assessed"),
    }

    # ---------- GEN & REL overlays (derived from anchors) ----------

    GEN_ANCHORS = {
        "GEN-01": ["SAFE-01", "SAFE-04"],            # content safety
        "GEN-02": ["TRAN-01", "TRAN-06"],            # disclosure (TRAN-06 inferred)
        "GEN-03": ["TRAN-02", "SAFE-06", "TRAN-04"], # hallucination
        "GEN-04": ["SEC-02", "PRIV-05"],             # prompt leakage
        "GEN-05": ["PRIV-04", "PRIV-03"],            # retention boundaries
        "GEN-06": ["SEC-04", "SAFE-06"],             # misuse monitoring
    }

    REL_ANCHORS = {
        "REL-01": ["SEC-01", "PRIV-06", "PRIV-07"],  # vendor terms
        "REL-02": ["SEC-03", "SEC-05"],              # dependency risk
        "REL-03": ["SAFE-05", "GOV-04"],             # release risk
        "REL-04": ["GOV-08", "TRAN-05"],             # distribution control
        "REL-05": ["DOC-01", "DOC-08"],              # external docs
    }

    def __init__(
        self,
        use_llm: bool = False,
        groq_api_key: Optional[str] = None,
        focus_pillars: Optional[List[str]] = None,
    ):
        # which pillars the user wants (P1–P11)
        self.focus_pillars = focus_pillars or list(self.PILLARS.keys())

        # issues + control state
        self.issues: List[EthicsIssue] = []
        self.controls: Dict[str, ControlStatus] = {
            cid: ControlStatus(
                control_id=cid,
                pillar=self.PRIMARY_CONTROLS[cid][0],
                name=self.PRIMARY_CONTROLS[cid][1],
                satisfied=False,
            )
            for cid in self.PRIMARY_CONTROLS
        }

        # LLM integration
        self.use_llm = use_llm
        self.llm_client = EthicsLLMClient(groq_api_key) if use_llm else None
        self._repo_snippets: List[str] = []  # accumulated code snippets for LLM

    # ---------- Public API called from github_connector ----------

    def analyze_file(self, file_path: str, content: str):
        """
        1) Run lightweight heuristic checks.
        2) Accumulate truncated snippet for LLM P1–P11/GEN analysis.
        """
        lowered = content.lower()

        # Simple rule: hard‑coded secrets -> security/privacy critical
        if re.search(r"(api_key|secret_key|access_token)\s*=", lowered):
            self._add_issue(
                file_path=file_path,
                line_number=1,
                issue_type="security",
                severity="critical",
                message="Possible hard‑coded secret detected.",
                suggestion="Move secrets to env vars or secret manager; rotate exposed keys.",
                code_snippet="...api_key = '***'...",
            )
            self._mark_unsatisfied("SEC-03", file_path, "Hard‑coded secrets found.")

        # Ethics config present -> some governance / docs controls satisfied
        if "ethics_config.yml" in lowered or "ethics_config.yaml" in lowered:
            self._mark_satisfied("GOV-01", file_path)
            self._mark_satisfied("GOV-02", file_path)
            self._mark_satisfied("DOC-01", file_path)

        # Logging of requests/responses -> traceability
        if "logging" in lowered and ("request" in lowered or "response" in lowered):
            self._mark_satisfied("DOC-04", file_path, "Logging of requests/responses present.")

        # Accumulate snippet for LLM – short, so LLM can quote it back
        snippet = content[:500]
        self._repo_snippets.append(f"# File: {file_path}\n{snippet}")

    def generate_report(self, repo_full_name: str = "unknown/repo") -> Dict:
        """
        Compute ethics score, derive overlays, and optionally fuse Groq LLM
        P1–P11 + GEN scores, restricted to focus_pillars.
        """
        # 1) Deterministic score from PRIMARY controls
        total_primary = len(self.controls)
        satisfied_primary = sum(1 for c in self.controls.values() if c.satisfied)
        ethical_score = round(100.0 * satisfied_primary / total_primary, 1) if total_primary else 100.0

        issues_by_severity: Dict[str, int] = {}
        issues_by_type: Dict[str, int] = {}
        for issue in self.issues:
            issues_by_severity[issue.severity] = issues_by_severity.get(issue.severity, 0) + 1
            issues_by_type[issue.issue_type] = issues_by_type.get(issue.issue_type, 0) + 1

        overlays = {
            "GEN": self._derive_overlay_status(self.GEN_ANCHORS),
            "REL": self._derive_overlay_status(self.REL_ANCHORS),
        }

        # 2) Optional LLM evaluation for selected pillars + GEN overlay
        llm_result = None
        if self.use_llm and self.llm_client:
            summary_text = "\n\n".join(self._repo_snippets)
            llm_result = self.llm_client.evaluate_repo(
                repo_name=repo_full_name,
                files_summary=summary_text,
                focus_pillars=self.focus_pillars,
            )

            # Fuse P1–P11 scores: 0/1/2 -> 0/50/100 and average with heuristic score
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
                        gen_score = gen_raw * 50  # 0/1/2 -> 0/50/100
                        llm_score = (llm_score + gen_score) / 2.0

                    ethical_score = round((ethical_score + llm_score) / 2, 1)

        return {
            "ethical_score": ethical_score,
            "total_issues": len(self.issues),
            "issues_by_severity": issues_by_severity,
            "issues_by_type": issues_by_type,
            "issues": self.issues,
            "controls": self.controls,
            "overlays": overlays,
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

    def _mark_satisfied(self, control_id: str, file_path: str, notes: Optional[str] = None):
        if control_id in self.controls:
            cs = self.controls[control_id]
            cs.satisfied = True
            if file_path not in cs.evidence_files:
                cs.evidence_files.append(file_path)
            if notes:
                cs.notes = notes

    def _mark_unsatisfied(self, control_id: str, file_path: str, notes: Optional[str] = None):
        if control_id in self.controls:
            cs = self.controls[control_id]
            cs.satisfied = False
            if file_path not in cs.evidence_files:
                cs.evidence_files.append(file_path)
            if notes:
                cs.notes = notes

    def _derive_overlay_status(self, mapping: Dict[str, List[str]]) -> Dict[str, str]:
        status: Dict[str, str] = {}
        for overlay_id, anchors in mapping.items():
            anchor_controls = [self.controls[a] for a in anchors if a in self.controls]
            if not anchor_controls:
                status[overlay_id] = "not_applicable"
                continue

            if any(not c.satisfied and c.evidence_files for c in anchor_controls):
                status[overlay_id] = "unmet"
            elif all(c.satisfied for c in anchor_controls):
                status[overlay_id] = "satisfied"
            else:
                status[overlay_id] = "conditional"
        return status
