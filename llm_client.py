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

    def evaluate_repo(
        self,
        repo_name: str,
        files_summary: str,
        focus_pillars: List[str],
        pillar_rules: Optional[Dict[str, List[str]]] = None,
    ) -> Dict:
        focus_str = ", ".join(focus_pillars)

        # Build the rules section for focus pillars only
        rules_lines: List[str] = []
        if pillar_rules:
            rules_lines.append(
                "For each pillar, evaluate ONLY against these 3 specific rules:"
            )
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
            "- score=1 (pass/partial) if there is any credible evidence for even 1 of the 3 rules.\n"
            "- score=2 (pass/strong) if evidence clearly covers 2 or more rules.\n"
            "- score=0 (fail) only when no evidence exists AND an obvious risk is present.\n"
            "- PASS/FAIL: score >= 1 = PASS, score = 0 = FAIL.\n\n"
            "Output STRICT JSON with this schema:\n"
            "{\n"
            '  "pillars": {\n'
            '    "P1": {\n'
            '      "score": int,\n'
            '      "verdict": "pass"|"fail",\n'
            '      "rules": {\n'
            '        "1": {"passed": bool, "reason": str},\n'
            '        "2": {"passed": bool, "reason": str},\n'
            '        "3": {"passed": bool, "reason": str}\n'
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
            "Writing style for 'reason' in each rule entry (IMPORTANT):\n"
            "- Write exactly one short sentence explaining whether that specific rule is met or not.\n"
            "- Use plain, simple English. No jargon, acronyms, or technical terms.\n"
            "- Be specific: say what was found (or not found) that relates to that rule.\n"
            "- Do not use file names; say 'the main script' or 'the configuration file' instead.\n"
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
                max_tokens=2000,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            content = message.content[0].text.strip()

            # Clean possible markdown fences
            if content.startswith("```json"):
                content = content.split("```json", 1)[1].split("```", 1)[0].strip()

            result = json.loads(content)
            print(f"Claude response received for {repo_name}")
            return result

        except (
            APIError,
            RateLimitError,
            APIConnectionError,
            json.JSONDecodeError,
        ) as e:
            print(f"Claude API error: {str(e)}")
            return {
                "pillars": {},
                "gen": {
                    "uses_generative_ai": False,
                    "score": 0,
                    "reason": f"API error: {str(e)}",
                },
                "overall_comment": f"Evaluation failed: {str(e)}",
            }
