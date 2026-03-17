# llm_client.py

import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv
from anthropic import Anthropic, APIError, RateLimitError, APIConnectionError

load_dotenv()  # make sure .env is loaded here


class EthicsLLMClient:
    """
    Wrapper for Anthropic Claude API.
    Evaluates selected P1–P11 pillars + GEN overlay.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = None,
    ):
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required. Check .env file.")

        self.client = Anthropic()

        # Use a valid model name from your screenshot
        self.model = model or "claude-haiku-4-5"  # ← recommended default

        print(f"Claude client initialized with model: {self.model}")

    def _build_default_rules(
        self,
        pillar_id: str,
        pillar_rules: Optional[Dict[str, List[str]]],
        reason: str,
    ) -> Dict[str, Dict[str, object]]:
        rule_count = len((pillar_rules or {}).get(pillar_id, [])) or 3
        return {
            str(index): {
                "passed": False,
                "reason": reason,
                "evidence": "",
                "suggestion": "",
            }
            for index in range(1, rule_count + 1)
        }

    def _default_fail_suggestion(self, question_text: str) -> str:
        text = (question_text or "").lower()
        if "owner" in text or "team" in text or "responsible" in text:
            return (
                "Add an OWNER section in README.md with one primary owner, one backup owner, "
                "and a team contact channel."
            )
        if "explained" in text or "meant to do" in text or "purpose" in text:
            return (
                "Add a project overview in README.md with purpose, inputs, outputs, and a 3-step "
                "usage example."
            )
        if (
            "version history" in text
            or "changelog" in text
            or "changed over time" in text
        ):
            return (
                "Create CHANGELOG.md and add dated entries per release (Added/Changed/Fixed), then "
                "link it from README.md."
            )
        if "privacy" in text or "personal" in text or "pii" in text:
            return (
                "Document a privacy policy with what data is collected, why it is needed, where it is "
                "stored, and when it is deleted."
            )
        if "fair" in text or "bias" in text:
            return (
                "Add a fairness checklist with at least two representative test groups and acceptance "
                "thresholds for each release."
            )
        if "security" in text or "secret" in text or "token" in text:
            return (
                "Move all secrets to environment variables or a secret manager, rotate exposed keys, "
                "and add a pre-commit secret scan."
            )
        if "documentation" in text:
            return (
                "Add README.md sections for architecture, setup, and known limitations."
            )
        if "accessibility" in text:
            return (
                "Add accessibility checks (keyboard navigation, labels, contrast) and include results "
                "in the release checklist."
            )
        if "misuse" in text or "harm" in text or "social" in text:
            return (
                "Add a misuse and harm section listing top risks, blocked use cases, and response "
                "actions for incidents."
            )
        return "Add a clear project policy section in README.md with concrete rules and ownership."

    def _format_api_error_reason(self, error: Exception) -> str:
        raw = str(error)
        lowered = raw.lower()

        if "authentication_error" in lowered or "invalid x-api-key" in lowered:
            return (
                "LLM evaluation is unavailable because the Anthropic API key is invalid. "
                "Update ANTHROPIC_API_KEY in your environment and run again."
            )

        if "rate" in lowered and "limit" in lowered:
            return (
                "LLM evaluation is temporarily unavailable due to rate limiting. "
                "Please retry in a moment."
            )

        if "connection" in lowered or "timeout" in lowered:
            return (
                "LLM evaluation could not connect to the API service. "
                "Please check your network and try again."
            )

        return f"LLM evaluation failed: {raw}"

    def _normalize_llm_result(
        self,
        result: Dict,
        focus_pillars: List[str],
        pillar_rules: Optional[Dict[str, List[str]]] = None,
    ) -> Dict:
        normalized = result if isinstance(result, dict) else {}
        pillars = normalized.get("pillars")
        if not isinstance(pillars, dict):
            pillars = {}

        fallback_reason = (
            normalized.get("overall_comment") or "No evaluation details were returned."
        )

        normalized_pillars: Dict[str, Dict] = {}
        for pillar_id in focus_pillars:
            entry = pillars.get(pillar_id, {}) if isinstance(pillars, dict) else {}
            score = entry.get("score") if isinstance(entry, dict) else None
            verdict = entry.get("verdict") if isinstance(entry, dict) else None
            rules = entry.get("rules") if isinstance(entry, dict) else None

            if not isinstance(rules, dict):
                rules = {}

            default_rule_reason = entry.get("reason") or fallback_reason
            normalized_rules = self._build_default_rules(
                pillar_id, pillar_rules, default_rule_reason
            )
            question_lookup = {
                str(i): question
                for i, question in enumerate((pillar_rules or {}).get(pillar_id, []), 1)
            }

            for rule_id, rule_value in rules.items():
                if isinstance(rule_value, dict):
                    passed_flag = bool(rule_value.get("passed", False))
                    question_text = question_lookup.get(str(rule_id), "")
                    suggestion = (rule_value.get("suggestion") or "").strip()
                    if (not passed_flag) and not suggestion:
                        suggestion = self._default_fail_suggestion(question_text)

                    normalized_rules[str(rule_id)] = {
                        "passed": passed_flag,
                        "reason": rule_value.get("reason") or default_rule_reason,
                        "evidence": (rule_value.get("evidence") or "").strip(),
                        "suggestion": suggestion,
                    }

            if verdict not in {"pass", "fail", "not_evaluated"}:
                if isinstance(score, (int, float)):
                    verdict = "pass" if score >= 1 else "fail"
                else:
                    verdict = "not_evaluated"

            normalized_pillars[pillar_id] = {
                "score": score,
                "verdict": verdict,
                "rules": normalized_rules,
            }

        normalized["pillars"] = normalized_pillars
        normalized.setdefault(
            "gen",
            {
                "uses_generative_ai": False,
                "score": 0,
                "reason": fallback_reason,
            },
        )
        normalized.setdefault("overall_comment", fallback_reason)
        return normalized

    def _extract_json_payload(self, content: str) -> str:
        text = (content or "").strip()
        if not text:
            return "{}"

        if text.startswith("```json"):
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text

    def evaluate_repo(
        self,
        repo_name: str,
        files_summary: str,
        focus_pillars: List[str],
        pillar_rules: Optional[Dict[str, List[str]]] = None,
    ) -> Dict:
        focus_str = ", ".join(focus_pillars)

        # Build the question section for focus pillars only
        rules_lines: List[str] = []
        if pillar_rules:
            rules_lines.append("For each pillar, answer ONLY these 3 simple questions:")
            for pid in focus_pillars:
                if pid in pillar_rules:
                    rules_lines.append(f"  {pid}:")
                    for i, rule in enumerate(pillar_rules[pid], 1):
                        rules_lines.append(f"    {i}. {rule}")
        rules_block = "\n".join(rules_lines)

        system_prompt = (
            "You are an AI ethics auditor assessing a software repository against pillars P1–P11 "
            "and a GENERATIVE overlay GEN.\n"
            "Pillars: P1 governance, P2 risk, P3 human_oversight, P4 privacy, P5 fairness, "
            "P6 transparency, P7 safety, P8 security, P9 documentation, P10 accessibility, "
            "P11 societal.\n"
            "GEN overlay focuses on generative AI content safety, hallucinations, prompt/data leakage, "
            "retention of prompts, and misuse monitoring.\n\n"
            f"Only evaluate these pillars: {focus_str}.\n\n"
            f"{rules_block}\n\n"
            "Evaluation style:\n"
            "- Be practical and lenient; do not over-penalize minimal or prototype code.\n"
            "- score=1 (pass/partial) if there is any credible evidence for even 1 of the 3 questions.\n"
            "- score=2 (pass/strong) if evidence clearly supports 2 or more questions.\n"
            "- score=0 (fail) only when evidence supports none of the questions and obvious risk is present.\n"
            "- PASS/FAIL: score >= 1 = PASS, score = 0 = FAIL.\n\n"
            "Output STRICT JSON with this schema:\n"
            "{\n"
            '  "pillars": {\n'
            '    "P1": {\n'
            '      "score": int,\n'
            '      "verdict": "pass"|"fail",\n'
            '      "rules": {\n'
            '        "1": {"passed": bool, "reason": str, "evidence": str, "suggestion": str},\n'
            '        "2": {"passed": bool, "reason": str, "evidence": str, "suggestion": str},\n'
            '        "3": {"passed": bool, "reason": str, "evidence": str, "suggestion": str}\n'
            "      }\n"
            "    },\n"
            "    ... only for the pillars you were asked to evaluate ...\n"
            "  },\n"
            '  "gen": {\n'
            '    "uses_generative_ai": bool,\n'
            '    "score": int,\n'
            '    "reason": str\n'
            "  },\n"
            '  "overall_comment": str\n'
            "}\n\n"
            "Scoring: 0 = fail, 1 = pass/partial, 2 = pass/strong.\n"
            "Writing style for 'reason' in each question entry (IMPORTANT):\n"
            "- Write 2 short sentences for each question.\n"
            "- Sentence 1 should clearly say yes/no for the question.\n"
            "- Sentence 2 should explain what evidence was found or what is missing.\n"
            "- Fill 'evidence' with at least one short code snippet quote and filename if passed=true.\n"
            "- Keep evidence compact: '<filename>: <quoted snippet>' (max 160 chars).\n"
            "- If passed=false, fill 'suggestion' with one definitive action the team should do next.\n"
            "- Suggestions must be concrete and implementable, not generic advice.\n"
            "- For failed questions, write suggestion in this exact style: 'What this means: ... Do this: ...'.\n"
            "- Keep failed suggestions to 1-2 short sentences in plain English.\n"
            "- Do not assume similarly named files are version history (e.g., app.py vs app_2.py).\n"
            "- For changelog/history failures, define it clearly: CHANGELOG.md with dated release entries and Added/Changed/Fixed notes.\n"
            "- Use plain, simple English.\n"
            "Output ONLY the JSON object — no markdown, no extra text."
        )

        user_message = (
            f"Repository: {repo_name}\n\n"
            "Relevant code/docs snippets:\n"
            f"{files_summary}\n\n"
            "Produce ONLY the requested JSON."
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=12000,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            content = message.content[0].text.strip()

            json_payload = self._extract_json_payload(content)
            result = json.loads(json_payload)
            result = self._normalize_llm_result(result, focus_pillars, pillar_rules)
            print(f"Claude response received for {repo_name}")
            return result

        except (
            APIError,
            RateLimitError,
            APIConnectionError,
            json.JSONDecodeError,
        ) as e:
            friendly_reason = self._format_api_error_reason(e)
            print(f"Claude API error: {str(e)}")
            return self._normalize_llm_result(
                {
                    "pillars": {},
                    "gen": {
                        "uses_generative_ai": False,
                        "score": 0,
                        "reason": friendly_reason,
                    },
                    "overall_comment": friendly_reason,
                },
                focus_pillars,
                pillar_rules,
            )
