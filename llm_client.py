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
    Evaluates selected P1–P11 controls + GEN overlay.
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
        self.model = model or "claude-haiku-4-5"   # ← recommended default


        print(f"Claude client initialized with model: {self.model}")

    def evaluate_repo(
        self,
        repo_name: str,
        files_summary: str,
        focus_pillars: List[str],
    ) -> Dict:
        focus_str = ", ".join(focus_pillars)

        system_prompt = (
            "You are an AI ethics auditor assessing a software repository against a control "
            "framework with PRIMARY pillars P1–P11 and a GENERATIVE overlay GEN.\n"
            "Pillars: P1 governance, P2 risk, P3 human_oversight, P4 privacy, P5 fairness, "
            "P6 transparency, P7 safety, P8 security, P9 documentation, P10 accessibility, "
            "P11 societal.\n"
            "GEN overlay focuses on generative AI content safety, hallucinations, prompt/data leakage, "
            "retention of prompts, and misuse monitoring.\n\n"
            f"Only evaluate these pillars: {focus_str}.\n\n"
            "You must output STRICT JSON with this schema:\n"
            "{\n"
            "  \"pillars\": {\n"
            "    \"P1\": {\"score\": int, \"reason\": str},\n"
            "    ... only for the pillars you were asked to evaluate ...\n"
            "  },\n"
            "  \"gen\": {\n"
            "    \"uses_generative_ai\": bool,\n"
            "    \"score\": int,\n"
            "    \"reason\": str\n"
            "  },\n"
            "  \"overall_comment\": str\n"
            "}\n\n"
            "Scoring: 0 = no evidence / serious gaps; 1 = partial; 2 = strong.\n"
            "If no generative AI usage detected, set uses_generative_ai=false and score=0.\n"
            "In 'reason' fields: always reference at least one concrete file path or code excerpt "
            "when score is 1 or 2. Quote small parts of code directly.\n"
            "Keep reasons concise (1–3 sentences).\n"
            "Output ONLY the JSON object – no other text, no markdown."
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
                messages=[{"role": "user", "content": user_message}]
            )

            content = message.content[0].text.strip()

            # Clean possible markdown fences
            if content.startswith("```json"):
                content = content.split("```json", 1)[1].split("```", 1)[0].strip()

            result = json.loads(content)
            print(f"Claude response received for {repo_name}")
            return result

        except (APIError, RateLimitError, APIConnectionError, json.JSONDecodeError) as e:
            print(f"Claude API error: {str(e)}")
            return {
                "pillars": {},
                "gen": {"uses_generative_ai": False, "score": 0, "reason": f"API error: {str(e)}"},
                "overall_comment": f"Evaluation failed: {str(e)}"
            }