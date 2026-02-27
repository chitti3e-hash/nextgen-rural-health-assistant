from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re


DISEASE_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "my",
    "me",
    "i",
    "am",
    "is",
    "are",
    "do",
    "does",
    "what",
    "why",
    "how",
    "can",
    "should",
    "please",
    "about",
    "need",
    "help",
    "have",
    "has",
    "had",
    "from",
    "this",
    "that",
    "it",
    "be",
    "treatment",
    "medicine",
    "medicines",
    "remedy",
    "remedies",
    "care",
    "cure",
    "manage",
    "management",
    "disease",
    "diseases",
    "symptom",
    "symptoms",
}


NONSPECIFIC_LABELS = {
    "pain",
    "chest pain",
    "abdominal pain",
    "cough",
    "fever",
    "headache",
    "nausea",
    "vomiting",
    "dizziness",
    "fatigue",
    "weakness",
    "palpitations",
}

QUERY_TOKEN_EXPANSIONS = {
    "blood": {"hematologic", "haematologic", "leukemia", "leukaemia"},
    "kidney": {"renal"},
    "stone": {"calculus", "nephrolithiasis"},
    "ear": {"hearing", "otitis"},
    "heart": {"cardiac"},
    "bp": {"pressure", "hypertension"},
    "sugar": {"diabetes"},
    "cancer": {"neoplasm", "malignant", "malignancy", "tumor", "tumour", "oncology"},
    "tumor": {"tumour", "neoplasm", "cancer"},
    "tumour": {"tumor", "neoplasm", "cancer"},
    "pregnant": {"pregnancy"},
}

ONCOLOGY_TERMS = {"cancer", "neoplasm", "tumor", "tumour", "oncology", "malignant", "malignancy"}

CONTEXTUAL_NAME_MARKERS = {
    "fear of",
    "follow-up",
    "follow up",
    "history of",
    "screening for",
    "contact with",
    "encounter for",
    "counselling",
    "counseling",
}


@dataclass
class DiseaseRecord:
    id: str
    name: str
    aliases: list[str]
    category: str
    overview: str
    treatment_summary: str
    medicine_guidance: list[str]
    home_care: list[str]
    red_flags: list[str]
    source: str


class DiseaseService:
    def __init__(self, records: list[DiseaseRecord]):
        self.records = records
        self._record_tokens: list[set[str]] = []
        self._low_signal_ids: set[str] = set()

        for record in records:
            token_source = " ".join([record.name, *record.aliases, record.category])
            self._record_tokens.append(set(self._normalize_tokens(self._tokenize(token_source))))

            if self._is_low_signal_record(record):
                self._low_signal_ids.add(record.id)

    @classmethod
    def from_json(cls, data_path: Path) -> "DiseaseService":
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        records = [
            DiseaseRecord(
                id=item["id"],
                name=item["name"],
                aliases=item.get("aliases", []),
                category=item["category"],
                overview=item["overview"],
                treatment_summary=item["treatment_summary"],
                medicine_guidance=item.get("medicine_guidance", []),
                home_care=item.get("home_care", []),
                red_flags=item.get("red_flags", []),
                source=item.get("source", "Verified medical sources"),
            )
            for item in payload
        ]
        return cls(records)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9]+", text.lower())

    @staticmethod
    def _normalize_tokens(tokens: list[str]) -> list[str]:
        return [token for token in tokens if token not in DISEASE_STOPWORDS and len(token) > 1]

    @staticmethod
    def _expand_query_tokens(tokens: set[str]) -> set[str]:
        expanded = set(tokens)
        for token in list(tokens):
            expanded.update(QUERY_TOKEN_EXPANSIONS.get(token, set()))
        return expanded

    @staticmethod
    def _has_treatment_intent(tokens: set[str]) -> bool:
        intent_words = {
            "treatment",
            "medicine",
            "medicines",
            "drug",
            "drugs",
            "remedy",
            "remedies",
            "care",
            "cure",
            "manage",
            "management",
        }
        return bool(tokens.intersection(intent_words))

    @staticmethod
    def _is_curated_record(record: DiseaseRecord) -> bool:
        return record.id.startswith("dis-")

    @staticmethod
    def _is_low_signal_record(record: DiseaseRecord) -> bool:
        if not record.id.startswith("icd-"):
            return False
        treatment = record.treatment_summary.lower()
        return (
            "management depends on confirmed diagnosis" in treatment
            or "care depends on clinical severity" in treatment
            or "symptom-based entries indicate the need for structured clinical evaluation" in treatment
        )

    @staticmethod
    def _normalized_id_code(record_id: str) -> str:
        code = record_id.lower().replace("icd-", "")
        return code.replace("-", ".")

    def _is_exact_phrase_match(self, lowered_query: str, record: DiseaseRecord) -> bool:
        if record.name.lower() in lowered_query:
            return True
        if any(alias.lower() in lowered_query for alias in record.aliases):
            return True

        normalized_code = self._normalized_id_code(record.id)
        return normalized_code in lowered_query or record.id.lower() in lowered_query

    def _is_nonspecific_record(self, record: DiseaseRecord) -> bool:
        if not record.id.startswith("icd-"):
            return False
        return record.name.lower() in NONSPECIFIC_LABELS

    @staticmethod
    def _is_contextual_record(record: DiseaseRecord) -> bool:
        if not record.id.startswith("icd-"):
            return False
        lowered = record.name.lower()
        return any(marker in lowered for marker in CONTEXTUAL_NAME_MARKERS)

    def query_mentions_disease(self, query: str, record: DiseaseRecord) -> bool:
        return self._is_exact_phrase_match(query.lower(), record)

    def is_contextual_or_admin(self, record: DiseaseRecord) -> bool:
        return self._is_contextual_record(record)

    def has_medical_lookup_intent(self, query: str) -> bool:
        tokens = set(self._tokenize(query))
        intent_words = {
            "disease",
            "condition",
            "diagnosis",
            "treatment",
            "medicine",
            "medicines",
            "drug",
            "drugs",
            "remedy",
            "remedies",
            "cancer",
            "infection",
            "syndrome",
            "icd",
        }
        return bool(tokens.intersection(intent_words))

    def is_high_quality_match(self, record: DiseaseRecord, score: float, query: str) -> bool:
        lowered_query = query.lower()
        exact_match = self._is_exact_phrase_match(lowered_query, record)

        if self._is_nonspecific_record(record):
            diagnostic_intent = any(term in lowered_query for term in {"disease", "diagnosis", "condition", "icd", "code"})
            if not diagnostic_intent:
                return False

        if self._is_curated_record(record):
            return score >= 0.26 or exact_match

        if record.id in self._low_signal_ids:
            return exact_match and score >= 0.45

        return score >= 0.62 or exact_match

    def search(self, query: str, limit: int = 3) -> list[tuple[DiseaseRecord, float]]:
        lowered_query = query.lower()
        raw_query_tokens = set(self._tokenize(query))
        base_query_tokens = set(self._normalize_tokens(list(raw_query_tokens)))
        if not base_query_tokens:
            return []
        query_tokens = self._expand_query_tokens(base_query_tokens)

        scored: list[tuple[DiseaseRecord, float, bool, int, bool, bool, bool]] = []
        treatment_intent = self._has_treatment_intent(raw_query_tokens)
        oncology_intent = bool(base_query_tokens.intersection(ONCOLOGY_TERMS))

        for idx, record in enumerate(self.records):
            record_tokens = self._record_tokens[idx]
            primary_overlap = len(base_query_tokens.intersection(record_tokens))
            expansion_only_tokens = query_tokens.difference(base_query_tokens)
            expansion_overlap = len(expansion_only_tokens.intersection(record_tokens))
            overlap = primary_overlap + expansion_overlap
            if overlap == 0:
                continue

            exact_match = self._is_exact_phrase_match(lowered_query, record)
            is_curated = self._is_curated_record(record)
            is_contextual = self._is_contextual_record(record)

            if not exact_match and primary_overlap == 0 and len(base_query_tokens) >= 2 and not oncology_intent:
                continue
            if not exact_match and primary_overlap <= 1 and len(base_query_tokens) >= 4:
                continue

            weighted_overlap = primary_overlap + (0.35 * expansion_overlap)
            coverage = weighted_overlap / max(len(base_query_tokens), 1)
            match_density = weighted_overlap / max(len(record_tokens), 1)
            score = (0.7 * coverage) + (0.3 * match_density)

            if exact_match:
                score += 0.26
            if primary_overlap >= 2:
                score += 0.06
            if is_curated:
                score += 0.1
            if treatment_intent and is_curated:
                score += 0.06
            if record.id in self._low_signal_ids:
                score -= 0.15
            if is_contextual:
                score -= 0.08
                if not exact_match:
                    score -= 0.18
            has_oncology_signal = bool(record_tokens.intersection(ONCOLOGY_TERMS))
            if oncology_intent:
                score += 0.12 if has_oncology_signal else -0.15

            if score > 0:
                scored.append(
                    (record, round(min(score, 0.99), 4), exact_match, overlap, is_curated, has_oncology_signal, is_contextual)
                )

        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored:
            return []

        curated_scored = [item for item in scored if item[4]]
        candidate_pool = scored
        if not oncology_intent and curated_scored and curated_scored[0][1] >= 0.24:
            candidate_pool = curated_scored

        results: list[tuple[DiseaseRecord, float]] = []
        for record, score, exact_match, overlap, is_curated, has_oncology_signal, is_contextual in candidate_pool:
            min_score = 0.32 if is_curated else 0.52
            if exact_match:
                min_score -= 0.08
            if overlap >= 2 and not is_curated:
                min_score -= 0.03
            if treatment_intent and is_curated:
                min_score -= 0.02
            if oncology_intent and has_oncology_signal:
                min_score -= 0.08
            if is_contextual:
                min_score += 0.06
                if not exact_match:
                    min_score += 0.12

            if score < min_score:
                continue

            results.append((record, score))
            if len(results) >= max(1, min(limit, 5)):
                break

        return results

    @staticmethod
    def to_public_item(record: DiseaseRecord, score: float) -> dict:
        return {
            "id": record.id,
            "name": record.name,
            "category": record.category,
            "score": round(score, 2),
            "overview": record.overview,
            "treatment_summary": record.treatment_summary,
            "medicine_guidance": record.medicine_guidance,
            "home_care": record.home_care,
            "red_flags": record.red_flags,
            "source": record.source,
        }

    @staticmethod
    def to_chat_answer(record: DiseaseRecord) -> str:
        lines = [
            f"{record.name} ({record.category})",
            f"Overview: {record.overview}",
            f"Treatment approach: {record.treatment_summary}",
            "Medicines commonly used (doctor-guided):",
        ]

        medicine_items = record.medicine_guidance[:4] if record.medicine_guidance else [
            "Use medicines only after diagnosis confirmation by a licensed clinician."
        ]
        lines.extend([f"- {item}" for item in medicine_items])

        lines.append("Home care/remedies:")
        home_care_items = record.home_care[:4] if record.home_care else ["Maintain hydration, rest, and hygiene precautions."]
        lines.extend([f"- {item}" for item in home_care_items])

        lines.append("Urgent red flags:")
        red_flag_items = record.red_flags[:4] if record.red_flags else ["Breathing difficulty", "Confusion"]
        lines.extend([f"- {item}" for item in red_flag_items])

        return "\n".join(lines)
