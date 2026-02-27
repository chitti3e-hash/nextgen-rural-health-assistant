from dataclasses import dataclass

from app.services.localization import t


RED_FLAG_KEYWORDS = {
    "en": [
        "chest pain",
        "difficulty breathing",
        "shortness of breath",
        "unconscious",
        "seizure",
        "stroke",
        "severe bleeding",
        "suicidal",
    ],
    "hi": [
        "सीने में दर्द",
        "सांस लेने में दिक्कत",
        "बेहोश",
        "दौरा",
        "स्ट्रोक",
        "ज्यादा खून",
    ],
    "ta": [
        "மார்பு வலி",
        "மூச்சுத்திணறல்",
        "மயக்கம்",
        "fits",
        "பக்கவாதம்",
    ],
    "te": [
        "ఛాతి నొప్పి",
        "శ్వాస తీసుకోవడంలో ఇబ్బంది",
        "అపస్మారక స్థితి",
        "ఫిట్స్",
        "స్ట్రోక్",
    ],
    "bn": [
        "বুকে ব্যথা",
        "শ্বাসকষ্ট",
        "অজ্ঞান",
        "খিঁচুনি",
        "স্ট্রোক",
    ],
}


@dataclass
class TriageResult:
    is_critical: bool
    matched_keywords: list[str]
    next_steps: list[str]


def assess_triage(query: str, language: str) -> TriageResult:
    lowered_query = query.lower()
    matched = []

    for lang in [language, "en"]:
        for keyword in RED_FLAG_KEYWORDS.get(lang, []):
            if keyword.lower() in lowered_query:
                matched.append(keyword)

    if matched:
        return TriageResult(
            is_critical=True,
            matched_keywords=sorted(set(matched)),
            next_steps=[
                t(language, "critical_steps_1"),
                t(language, "critical_steps_2"),
                t(language, "critical_steps_3"),
            ],
        )

    return TriageResult(
        is_critical=False,
        matched_keywords=[],
        next_steps=[t(language, "follow_up")],
    )

