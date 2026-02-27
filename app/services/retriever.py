from dataclasses import dataclass
from pathlib import Path
import json
import re


RETRIEVER_STOPWORDS = {
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
    "was",
    "were",
    "be",
    "been",
    "being",
    "what",
    "how",
    "why",
    "when",
    "where",
    "can",
    "should",
    "could",
    "would",
    "please",
    "about",
    "need",
    "help",
    "have",
    "has",
    "had",
    "this",
    "that",
    "it",
    "from",
}


CATEGORY_HINTS = {
    "maternal": {"pregnant", "pregnancy", "fetal", "delivery", "antenatal", "anc", "newborn"},
    "chronic": {"diabetes", "sugar", "hypertension", "bp", "pressure", "thyroid", "kidney"},
    "infectious": {"fever", "infection", "flu", "cough", "malaria", "dengue", "tb", "diarrhea"},
    "child-health": {"child", "baby", "newborn", "infant", "vaccination"},
    "mental-health": {"anxiety", "depression", "stress", "sad", "sleep"},
    "nutrition": {"anemia", "weakness", "iron", "diet", "nutrition"},
    "prevention": {"prevention", "hygiene", "water", "handwash", "sanitation"},
}


@dataclass
class KnowledgeDocument:
    doc_id: str
    title: str
    category: str
    language: str
    content: str
    source: str


class KnowledgeRetriever:
    def __init__(self, documents: list[KnowledgeDocument]):
        self.documents = documents
        self.doc_tokens = [set(self._tokenize(f"{item.title}. {item.content}")) for item in documents]
        self.title_tokens = [set(self._tokenize(item.title)) for item in documents]

    @classmethod
    def from_json(cls, data_path: Path) -> "KnowledgeRetriever":
        return cls.from_json_files([data_path])

    @classmethod
    def from_json_files(cls, data_paths: list[Path]) -> "KnowledgeRetriever":
        docs: list[KnowledgeDocument] = []
        for data_path in data_paths:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            for item in payload:
                docs.append(
                    KnowledgeDocument(
                        doc_id=item["id"],
                        title=item["title"],
                        category=item["category"],
                        language=item.get("language", "en"),
                        content=item["content"],
                        source=item["source"],
                    )
                )

        return cls(docs)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        raw = re.findall(r"[\w\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0980-\u09FF]+", text.lower())
        return [token for token in raw if token not in RETRIEVER_STOPWORDS and len(token) > 1]

    @staticmethod
    def _score(query_tokens: set[str], doc_tokens: set[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0

        overlap = len(query_tokens.intersection(doc_tokens))
        if overlap == 0:
            return 0.0

        if len(query_tokens) >= 4 and overlap == 1:
            return 0.0

        coverage = overlap / max(len(query_tokens), 1)
        density = overlap / max(len(doc_tokens), 1)
        overlap_bonus = min(overlap / 3.0, 1.0) * 0.08
        return round((0.75 * coverage) + (0.17 * density) + overlap_bonus, 4)

    @staticmethod
    def _query_categories(query_tokens: set[str]) -> set[str]:
        hinted_categories: set[str] = set()
        for category, keywords in CATEGORY_HINTS.items():
            if query_tokens.intersection(keywords):
                hinted_categories.add(category)
        return hinted_categories

    def search(
        self,
        query: str,
        language: str = "en",
        top_k: int = 3,
    ) -> list[tuple[KnowledgeDocument, float]]:
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return []

        hinted_categories = self._query_categories(query_tokens)
        adjusted_scores: list[float] = []

        for idx, doc in enumerate(self.documents):
            score = self._score(query_tokens, self.doc_tokens[idx])

            title_overlap = len(query_tokens.intersection(self.title_tokens[idx]))
            if title_overlap:
                score += min(0.04 * title_overlap, 0.12)

            if doc.language == language:
                score += 0.03

            if hinted_categories and doc.category in hinted_categories:
                score += 0.05

            adjusted_scores.append(round(min(score, 0.99), 4))

        top_indices = sorted(range(len(adjusted_scores)), key=lambda idx: adjusted_scores[idx], reverse=True)[:top_k]
        results: list[tuple[KnowledgeDocument, float]] = []

        for idx in top_indices:
            score = float(adjusted_scores[idx])
            if score >= 0.1:
                results.append((self.documents[idx], round(score, 4)))

        return results
