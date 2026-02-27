from __future__ import annotations

import re


class PregnancyService:
    PREGNANCY_TERMS = {
        "pregnant",
        "pregnancy",
        "trimester",
        "weeks pregnant",
        "months pregnant",
        "gestation",
        "7 months",
        "8 months",
        "9 months",
    }

    @classmethod
    def has_pregnancy_context(cls, query: str) -> bool:
        lowered_query = query.lower()
        return any(term in lowered_query for term in cls.PREGNANCY_TERMS)

    @staticmethod
    def _extract_months(query: str) -> int | None:
        lowered_query = query.lower()
        month_match = re.search(r"\b([1-9]|1[0-2])\s*months?\b", lowered_query)
        if month_match:
            return int(month_match.group(1))

        week_match = re.search(r"\b([1-4][0-9]|[1-9])\s*weeks?\b", lowered_query)
        if week_match:
            weeks = int(week_match.group(1))
            return max(1, min(9, round(weeks / 4.35)))

        return None

    @classmethod
    def build_guidance(cls, query: str) -> tuple[str, list[str], float, str]:
        months = cls._extract_months(query)

        if months and months >= 7:
            stage = "third trimester"
            stage_guidance = (
                "At this stage, monitor baby movements daily and keep regular ANC visits (usually every 2 weeks or as advised)."
            )
        elif months and months >= 4:
            stage = "second trimester"
            stage_guidance = (
                "Continue scheduled ANC visits, anemia prevention, and routine fetal growth monitoring."
            )
        else:
            stage = "pregnancy"
            stage_guidance = "Register and continue antenatal care early with regular checkups at PHC/obstetric clinic."

        answer = "\n".join(
            [
                f"Pregnancy support ({stage})",
                stage_guidance,
                "Track blood pressure, swelling, headache, vision changes, bleeding, fever, or reduced fetal movement.",
                "Use only doctor-approved medicines and supplements (iron, calcium, folic acid as prescribed).",
                "Plan hospital delivery location, emergency transport, and keep MCP/ANC records ready.",
            ]
        )

        next_steps = [
            "Book/continue ANC checkup at nearest PHC/OB clinic this week.",
            "If 7+ months, count fetal movements and seek urgent care if movement is reduced.",
            "Emergency now if bleeding, severe headache, blurred vision, fits, breathlessness, or severe abdominal pain.",
        ]

        source = "RMNCH+A maternal care guidance + National Health Portal"
        return answer, next_steps, 0.82, source

