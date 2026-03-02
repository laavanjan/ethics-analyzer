from groq import Groq  # pip install groq
import os
import json


class EthicsLLMClient:
    """
    Thin wrapper around Groq chat completion API to evaluate selected P1–P11 controls
    plus the GEN overlay. Scores 0–2 and returns reasons that include code excerpts.
    """

    def __init__(self, api_key: str | None = None, model: str = "llama-3.3-70b-versatile"):
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is required")
        self.client = Groq(api_key=api_key)
        self.model = model

    def evaluate_repo(
        self,
        repo_name: str,
        files_summary: str,
        focus_pillars: list[str],
    ) -> dict:
        """
        Call LLM once per repo.

        Args:
            repo_name: "owner/repo" or any identifier.
            files_summary: concatenated snippets of key files.
            focus_pillars: list of pillar IDs to score, e.g. ["P1","P2","P3"].

        Returns:
            dict with:
            {
              "pillars": { "P1": {"score": int, "reason": str}, ... },
              "gen": {
                  "uses_generative_ai": bool,
                  "score": int,
                  "reason": str
              },
              "overall_comment": str
            }
        """
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
            "  'pillars': {\n"
            "    'P1': {'score': int, 'reason': str},\n"
            "    ... only for the pillars you were asked to evaluate ...\n"
            "  },\n"
            "  'gen': {\n"
            "    'uses_generative_ai': bool,\n"
            "    'score': int,\n"
            "    'reason': str\n"
            "  },\n"
            "  'overall_comment': str\n"
            "}\n\n"
            "Scoring for each pillar: 0 = no evidence / serious gaps; "
            "1 = partial evidence; 2 = strong evidence.\n"
            "If the repo does not use generative AI at all, set uses_generative_ai=false and score=0.\n\n"
            "IMPORTANT:\n"
            "- For every pillar you include, the 'reason' MUST reference at least one concrete code "
            "  excerpt or file path from the provided snippets whenever the score is 1 or 2.\n"
            "- Quote small parts of the code directly in the reason, e.g. \"in app.py: logging.request(...)\".\n"
            "- Keep reasons short (1–3 sentences per pillar).\n"
            "- Do NOT add any fields outside the schema.\n"
        )

        user_prompt = (
            f"Repository: {repo_name}\n\n"
            "Relevant code/docs snippets:\n"
            f"{files_summary}\n\n"
            "Now produce ONLY the JSON object described above."
        )

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        content = completion.choices[0].message.content
        return json.loads(content)
