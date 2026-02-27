from pathlib import Path
import json


class SchemeService:
    def __init__(self, schemes: list[dict]):
        self.schemes = schemes

    @classmethod
    def from_json(cls, data_path: Path) -> "SchemeService":
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        return cls(payload)

    def search(self, query: str, language: str) -> list[dict]:
        lowered_query = query.lower()
        matches: list[dict] = []
        for scheme in self.schemes:
            for keyword in scheme.get("keywords", []):
                if keyword.lower() in lowered_query:
                    matches.append(scheme)
                    break

        if matches:
            return matches

        if self.has_scheme_intent(query):
            return self.schemes[:2]

        return []

    @staticmethod
    def has_scheme_intent(query: str) -> bool:
        lowered_query = query.lower()
        scheme_intent_words = {
            "scheme",
            "insurance",
            "card",
            "benefit",
            "yojana",
            "eligibility",
            "apply",
            "registration",
            "cashless",
            "pmjay",
            "ayushman",
            "esanjeevani",
            "jsy",
            "pmmvy",
        }

        clinical_intent_words = {
            "pain",
            "fever",
            "bleeding",
            "vomiting",
            "headache",
            "swelling",
            "dizziness",
            "breath",
            "symptom",
            "month",
            "weeks",
            "pregnant",
            "pregnancy",
            "sugar",
            "bp",
        }

        has_scheme_word = any(word in lowered_query for word in scheme_intent_words)
        if not has_scheme_word:
            return False

        has_clinical_word = any(word in lowered_query for word in clinical_intent_words)
        return not has_clinical_word or "scheme" in lowered_query or "yojana" in lowered_query

    def format_response(self, matches: list[dict], language: str) -> tuple[str, list[str], list[dict]]:
        answer_lines = []
        next_steps = []
        sources = []

        for scheme in matches[:2]:
            content = scheme.get("summaries", {}).get(language) or scheme.get("summaries", {}).get("en", "")
            answer_lines.append(f"{scheme['name']}: {content}")

            for step in scheme.get("next_steps", [])[:2]:
                if step not in next_steps:
                    next_steps.append(step)

            sources.append(
                {
                    "title": scheme["name"],
                    "source": scheme.get("source", "Government Scheme Repository"),
                    "score": 0.88,
                }
            )

        return "\n".join(answer_lines), next_steps[:3], sources
