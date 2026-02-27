import re

from app.models import ChatResponse, SourceItem
from app.services.diseases import DiseaseService
from app.services.localization import t
from app.services.pregnancy import PregnancyService
from app.services.retriever import KnowledgeRetriever, KnowledgeDocument
from app.services.schemes import SchemeService
from app.services.triage import assess_triage


RESPONSE_STOPWORDS = {
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
    "what",
    "how",
    "why",
    "can",
    "should",
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


class HealthAssistant:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        scheme_service: SchemeService,
        disease_service: DiseaseService,
        pregnancy_service: PregnancyService,
    ):
        self.retriever = retriever
        self.scheme_service = scheme_service
        self.disease_service = disease_service
        self.pregnancy_service = pregnancy_service

    def answer(self, query: str, language: str) -> ChatResponse:
        triage_result = assess_triage(query=query, language=language)
        disclaimer = t(language, "disclaimer")

        if triage_result.is_critical:
            return ChatResponse(
                answer=f"{t(language, 'critical_header')} {t(language, 'critical_body')}",
                language=language,
                urgency="critical",
                disclaimer=disclaimer,
                next_steps=triage_result.next_steps,
                confidence=1.0,
                sources=[
                    SourceItem(
                        title="Emergency Triage Guidance",
                        source="MoHFW Emergency Protocol",
                        score=1.0,
                    )
                ],
            )

        scheme_intent = self.scheme_service.has_scheme_intent(query)

        if not scheme_intent and self.pregnancy_service.has_pregnancy_context(query):
            pregnancy_answer, next_steps, confidence, source = self.pregnancy_service.build_guidance(query)
            return ChatResponse(
                answer=pregnancy_answer,
                language=language,
                urgency="normal",
                disclaimer=f"{disclaimer} Pregnancy symptoms should be clinically reviewed; do not self-medicate.",
                next_steps=next_steps,
                confidence=confidence,
                sources=[SourceItem(title="Pregnancy ANC Guidance", source=source, score=confidence)],
            )

        if scheme_intent:
            scheme_matches = self.scheme_service.search(query=query, language=language)
            if scheme_matches:
                scheme_answer, next_steps, source_payload = self.scheme_service.format_response(
                    matches=scheme_matches,
                    language=language,
                )
                return ChatResponse(
                    answer=scheme_answer,
                    language=language,
                    urgency="normal",
                    disclaimer=disclaimer,
                    next_steps=next_steps,
                    confidence=0.88,
                    sources=[SourceItem(**item) for item in source_payload],
                )

        disease_matches = self.disease_service.search(query=query, limit=5)
        if disease_matches:
            top_disease, disease_score = disease_matches[0]
            for candidate, candidate_score in disease_matches:
                if not self.disease_service.is_contextual_or_admin(candidate):
                    top_disease, disease_score = candidate, candidate_score
                    break

            high_quality = self.disease_service.is_high_quality_match(top_disease, disease_score, query)
            explicit_disease_query = self.disease_service.query_mentions_disease(query, top_disease)
            disease_lookup_intent = self.disease_service.has_medical_lookup_intent(query)

            if high_quality and (explicit_disease_query or disease_lookup_intent):
                return ChatResponse(
                    answer=self.disease_service.to_chat_answer(top_disease),
                    language=language,
                    urgency="normal",
                    disclaimer=f"{disclaimer} Never start/stop prescription medicines without a licensed doctor.",
                    next_steps=self._build_next_steps(query=query, language=language),
                    confidence=round(min(max(disease_score, 0.48), 0.97), 2),
                    sources=[
                        SourceItem(
                            title=top_disease.name,
                            source=top_disease.source,
                            score=round(disease_score, 2),
                        )
                    ],
                )

        search_results = self.retriever.search(query=query, language=language)
        if not search_results or search_results[0][1] < 0.16:
            return self._build_low_information_response(query=query, language=language, disclaimer=disclaimer)

        answer_text = self._compose_grounded_answer(search_results=search_results, language=language, query=query)
        confidence = min(max(search_results[0][1], 0.35), 0.9)

        return ChatResponse(
            answer=answer_text,
            language=language,
            urgency="normal",
            disclaimer=disclaimer,
            next_steps=self._build_next_steps(query=query, language=language),
            confidence=round(confidence, 2),
            sources=[
                SourceItem(title=item.title, source=item.source, score=round(score, 2))
                for item, score in search_results[:3]
            ],
        )

    @staticmethod
    def _extract_summary(document: KnowledgeDocument) -> str:
        sentence_end = document.content.find(".")
        if sentence_end == -1:
            return document.content[:220]
        return document.content[: sentence_end + 1]

    @staticmethod
    def _topic_from_query(query: str) -> str:
        tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
        filtered = [token for token in tokens if token not in RESPONSE_STOPWORDS and len(token) > 2]
        if not filtered:
            return "your health concern"
        return " ".join(filtered[:4])

    def _compose_grounded_answer(
        self,
        search_results: list[tuple[KnowledgeDocument, float]],
        language: str,
        query: str,
    ) -> str:
        topic = self._topic_from_query(query)
        lines = [f"{t(language, 'grounded_intro')} Topic: {topic}."]
        for document, _ in search_results[:3]:
            lines.append(f"- {document.title}: {self._extract_summary(document)}")
        return "\n".join(lines)

    def _build_next_steps(self, query: str, language: str) -> list[str]:
        lowered_query = query.lower()
        steps = [t(language, "follow_up")]

        if any(token in lowered_query for token in ["fever", "temperature", "cough", "cold", "sore throat"]):
            steps.append("Track fever/breathing symptoms every 6-8 hours and keep hydration adequate.")

        if any(token in lowered_query for token in ["sugar", "diabetes", "bp", "pressure", "hypertension"]):
            steps.append("Check sugar/BP readings regularly and carry the log to your next clinic visit.")

        if any(token in lowered_query for token in ["pregnan", "fetal", "trimester", "weeks"]):
            steps.append("If pregnant, keep ANC visits on schedule and seek urgent care for bleeding or reduced fetal movement.")

        deduped: list[str] = []
        for step in steps:
            if step not in deduped:
                deduped.append(step)

        return deduped[:3]

    def _build_low_information_response(self, query: str, language: str, disclaimer: str) -> ChatResponse:
        topic = self._topic_from_query(query)
        answer = (
            f"I need a little more detail to give safe and useful guidance for {topic}. "
            "Share symptoms, duration, age, and known conditions (for example diabetes, pregnancy, BP)."
        )

        next_steps = [
            f"Describe your main symptom and duration clearly (example: '{query[:80]}').",
            "Mention age, pregnancy status, chronic diseases, and current medicines.",
            t(language, "no_info_step_2"),
        ]

        return ChatResponse(
            answer=answer,
            language=language,
            urgency="normal",
            disclaimer=disclaimer,
            next_steps=next_steps,
            confidence=0.22,
            sources=[],
        )
