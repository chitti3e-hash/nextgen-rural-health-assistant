import re

from app.models import ChatResponse, SourceItem
from app.services.diseases import DiseaseService
from app.services.hospitals import HospitalLocator, HospitalLookupError
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

PINCODE_PATTERN = re.compile(r"\b[1-9][0-9]{5}\b")
AGE_PATTERN = re.compile(r"\b(?:age\s*)?(\d{1,3})\s*(?:years?|yrs?|year old|year-old|yo|y/o)\b", re.IGNORECASE)

GOVERNMENT_HOSPITAL_MARKERS = {
    "government",
    "govt",
    "district hospital",
    "civil hospital",
    "medical college",
    "aiims",
    "cg",
    "phc",
    "chc",
}

SPECIALTY_HINTS = {
    "cancer": "Oncology",
    "oncology": "Oncology",
    "cardiac": "Cardiology",
    "heart": "Cardiology",
    "neuro": "Neurology",
    "ortho": "Orthopedics",
    "pediatric": "Pediatrics",
    "children": "Pediatrics",
    "maternity": "Obstetrics & Gynecology",
    "women": "Obstetrics & Gynecology",
    "eye": "Ophthalmology",
    "ent": "ENT",
    "kidney": "Nephrology/Urology",
    "renal": "Nephrology/Urology",
    "trauma": "Emergency/Trauma",
    "emergency": "Emergency/Trauma",
}


class HealthAssistant:
    def __init__(
        self,
        retriever: KnowledgeRetriever,
        scheme_service: SchemeService,
        disease_service: DiseaseService,
        pregnancy_service: PregnancyService,
        hospital_service: HospitalLocator | None = None,
    ):
        self.retriever = retriever
        self.scheme_service = scheme_service
        self.disease_service = disease_service
        self.pregnancy_service = pregnancy_service
        self.hospital_service = hospital_service

    def answer(
        self,
        query: str,
        language: str,
        location: str | None = None,
        age_years: int | None = None,
    ) -> ChatResponse:
        triage_result = assess_triage(query=query, language=language)
        disclaimer = t(language, "disclaimer")
        age_group = self._derive_age_group(query=query, age_years=age_years)
        hospital_section = self._build_hospital_section(query=query, location=location, emergency=triage_result.is_critical)

        if triage_result.is_critical:
            answer = self._format_medical_guidance(
                condition_name="Emergency symptoms detected",
                age_group=age_group,
                overview=t(language, "critical_body"),
                treatment_summary="Immediate emergency triage and hospital stabilization are required.",
                medicine_guidance=[
                    "Emergency medicines should be given only by trained clinicians.",
                    "Do not self-administer high-risk medicines or injections at home.",
                ],
                lifestyle_steps=triage_result.next_steps,
                avoid_items=[
                    "Do not delay emergency transfer.",
                    "Do not wait for symptoms to settle on their own.",
                ],
                red_flags=triage_result.matched_keywords or ["Severe chest pain", "Unconsciousness", "Severe bleeding"],
                emotional_support="Stay calm, keep the patient accompanied, and use clear communication with emergency staff.",
            )
            if hospital_section:
                answer = f"{answer}\n\n{hospital_section}"

            return ChatResponse(
                answer=answer,
                language=language,
                urgency="critical",
                disclaimer=disclaimer,
                next_steps=triage_result.next_steps,
                confidence=0.99,
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
            answer = self._format_medical_guidance(
                condition_name="Pregnancy support",
                age_group=age_group,
                overview=pregnancy_answer,
                treatment_summary="Antenatal care, blood pressure monitoring, fetal monitoring, and obstetric review are the core approaches.",
                medicine_guidance=[
                    "Pregnancy-safe medicines should be chosen only by a qualified doctor.",
                    "Iron, folic acid, calcium, and vaccines should follow ANC protocol and doctor advice.",
                    "Avoid over-the-counter painkillers, herbal medicines, or antibiotics without prescription.",
                ],
                lifestyle_steps=next_steps,
                avoid_items=[
                    "Do not skip scheduled ANC/PNC checkups.",
                    "Do not self-medicate during pregnancy.",
                ],
                red_flags=[
                    "Vaginal bleeding",
                    "Severe headache or blurred vision",
                    "Reduced fetal movement",
                    "Convulsions or severe breathlessness",
                ],
                emotional_support="Seek family support, discuss concerns with ANM/doctor, and ask for counselling if anxiety is high.",
            )
            if hospital_section:
                answer = f"{answer}\n\n{hospital_section}"

            return ChatResponse(
                answer=answer,
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
                answer = self._format_medical_guidance(
                    condition_name=top_disease.name,
                    age_group=age_group,
                    overview=top_disease.overview,
                    treatment_summary=top_disease.treatment_summary,
                    medicine_guidance=top_disease.medicine_guidance,
                    lifestyle_steps=top_disease.home_care,
                    avoid_items=[
                        "Do not start or stop prescription medicines without medical advice.",
                        "Do not use leftover antibiotics or steroid combinations without diagnosis.",
                    ],
                    red_flags=top_disease.red_flags,
                    emotional_support="Chronic symptoms can be stressful—consider counselling/support groups and involve family in care planning.",
                )
                if hospital_section:
                    answer = f"{answer}\n\n{hospital_section}"

                return ChatResponse(
                    answer=answer,
                    language=language,
                    urgency="normal",
                    disclaimer=f"{disclaimer} Never start/stop prescription medicines without a licensed doctor.",
                    next_steps=self._build_next_steps(query=query, language=language),
                    confidence=round(min(max(disease_score, 0.55), 0.99), 2),
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
            return self._build_low_information_response(
                query=query,
                language=language,
                disclaimer=disclaimer,
                location=location,
            )

        answer_text = self._compose_grounded_answer(search_results=search_results, language=language, query=query)
        if hospital_section:
            answer_text = f"{answer_text}\n\n{hospital_section}"
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

    def _build_low_information_response(
        self,
        query: str,
        language: str,
        disclaimer: str,
        location: str | None,
    ) -> ChatResponse:
        topic = self._topic_from_query(query)
        answer = (
            f"I need a little more detail to give safe and useful guidance for {topic}. "
            "Share symptoms, duration, age, and known conditions (for example diabetes, pregnancy, BP)."
        )

        hospital_section = self._build_hospital_section(query=query, location=location, emergency=False)
        if hospital_section:
            answer = f"{answer}\n\n{hospital_section}"

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

    @staticmethod
    def _derive_age_group(query: str, age_years: int | None = None) -> str:
        if age_years is not None:
            if age_years <= 12:
                return "Child (0–12)"
            if age_years <= 18:
                return "Teen (13–18)"
            if age_years <= 59:
                return "Adult (19–59)"
            return "Elderly (60+)"

        lowered = query.lower()
        age_match = AGE_PATTERN.search(query)
        if age_match:
            age = int(age_match.group(1))
            if age <= 12:
                return "Child (0–12)"
            if age <= 18:
                return "Teen (13–18)"
            if age <= 59:
                return "Adult (19–59)"
            return "Elderly (60+)"

        if any(token in lowered for token in ["newborn", "infant", "child", "kid"]):
            return "Child (0–12)"
        if any(token in lowered for token in ["teen", "adolescent"]):
            return "Teen (13–18)"
        if any(token in lowered for token in ["elderly", "senior", "aged"]):
            return "Elderly (60+)"
        return "Adult (19–59)"

    @staticmethod
    def _age_group_impact(condition_name: str, age_group: str) -> str:
        if age_group.startswith("Child"):
            return f"{condition_name} in children can progress quickly due to lower physiological reserve; early pediatric review is important."
        if age_group.startswith("Teen"):
            return f"{condition_name} in teens may affect growth, school performance, and emotional wellbeing; age-appropriate counselling helps."
        if age_group.startswith("Elderly"):
            return f"{condition_name} in older adults can worsen faster with comorbidities (diabetes/BP/heart/kidney disease), so close monitoring is needed."
        return f"{condition_name} in adults may affect daily function and work capacity; timely diagnosis improves outcomes."

    @staticmethod
    def _format_list(items: list[str], default_item: str) -> list[str]:
        cleaned = [item.strip() for item in items if item and item.strip()]
        return cleaned if cleaned else [default_item]

    def _format_medical_guidance(
        self,
        *,
        condition_name: str,
        age_group: str,
        overview: str,
        treatment_summary: str,
        medicine_guidance: list[str],
        lifestyle_steps: list[str],
        avoid_items: list[str],
        red_flags: list[str],
        emotional_support: str,
    ) -> str:
        medicines = self._format_list(medicine_guidance[:5], "Doctor-guided medicine choice after confirmed diagnosis.")
        lifestyle = self._format_list(lifestyle_steps[:5], "Maintain hydration, rest, and follow-up with a licensed doctor.")
        avoid_list = self._format_list(avoid_items[:4], "Avoid self-medication or delaying medical consultation.")
        emergency_flags = self._format_list(red_flags[:5], "Severe breathing difficulty or altered consciousness.")

        lines = [
            "------------------------------------------------------",
            "",
            "MEDICAL GUIDANCE SECTION",
            "",
            "1. Condition Overview",
            f"- {condition_name}: {overview}",
            "",
            "2. How it affects this age group",
            f"- Age group identified: {age_group}",
            f"- {self._age_group_impact(condition_name, age_group)}",
            "",
            "3. Common treatment approaches (categories only)",
            f"- {treatment_summary}",
            "- Categories: clinical evaluation, doctor-guided medicines, monitoring, specialist referral if needed.",
            "",
            "4. Medicine types commonly used (no dosage)",
            "- Medicines commonly used (doctor-guided):",
        ]
        lines.extend([f"  - {item}" for item in medicines])
        lines.extend(
            [
                "",
                "5. Lifestyle recommendations",
            ]
        )
        lines.extend([f"- {item}" for item in lifestyle])
        lines.extend(
            [
                "",
                "6. What to avoid",
            ]
        )
        lines.extend([f"- {item}" for item in avoid_list])
        lines.extend(
            [
                "",
                "7. Warning signs requiring emergency care",
            ]
        )
        lines.extend([f"- {item}" for item in emergency_flags])
        lines.extend(
            [
                "",
                "8. Emotional and mental health support advice",
                f"- {emotional_support}",
                "- Speak with a qualified doctor/counsellor if fear, stress, or low mood is persistent.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_pincode(value: str | None) -> str | None:
        if not value:
            return None
        match = PINCODE_PATTERN.search(value)
        return match.group(0) if match else None

    @staticmethod
    def _infer_hospital_type(name: str) -> str:
        lowered = name.lower()
        if any(marker in lowered for marker in GOVERNMENT_HOSPITAL_MARKERS):
            return "Government"
        return "Private"

    @staticmethod
    def _infer_specialty(name: str) -> str:
        lowered = name.lower()
        for keyword, specialty in SPECIALTY_HINTS.items():
            if keyword in lowered:
                return specialty
        return "General"

    def _build_hospital_section(self, query: str, location: str | None, emergency: bool) -> str:
        if not self.hospital_service:
            return ""

        pincode = self._extract_pincode(query) or self._extract_pincode(location)
        hospital_payload = None
        try:
            if pincode:
                hospital_payload = self.hospital_service.lookup_nearest(pincode=pincode, limit=5)
            elif location and location.strip():
                hospital_payload = self.hospital_service.lookup_nearest_by_location(location=location.strip(), limit=5)
        except HospitalLookupError:
            return (
                "------------------------------------------------------\n\n"
                "HOSPITAL FINDER SECTION (India Only)\n\n"
                "Hospital lookup is temporarily unavailable. Please call 108 or visit the nearest PHC/government hospital immediately."
            )

        if not hospital_payload:
            return ""

        hospitals = hospital_payload.get("hospitals", [])[:5]
        if not hospitals:
            return ""

        lines = [
            "------------------------------------------------------",
            "",
            "HOSPITAL FINDER SECTION (India Only)",
            "",
            "Method: Input location/pincode → latitude/longitude → Haversine distance → nearest-first sorting.",
        ]
        if emergency:
            lines.append("Emergency note: Critical symptoms detected. Please proceed immediately to the nearest emergency-capable hospital.")

        lines.append("")
        lines.append("Top 5 nearest hospitals:")

        for index, hospital in enumerate(hospitals, start=1):
            name = hospital.get("name", "Unnamed Hospital")
            address = hospital.get("address", "Address details not available")
            hospital_type = self._infer_hospital_type(name)
            specialty = self._infer_specialty(name)
            distance = hospital.get("distance_km", "NA")
            hospital_pincode = self._extract_pincode(address) or hospital_payload.get("pincode") or "Not available"
            contact = hospital.get("contact") or "Not available"

            lines.extend(
                [
                    f"{index}. Hospital Name: {name}",
                    f"   - Type: {hospital_type}",
                    f"   - Specialty: {specialty}",
                    f"   - Full Address: {address}",
                    f"   - Pincode: {hospital_pincode}",
                    f"   - Distance in KM: {distance}",
                    f"   - Contact: {contact}",
                ]
            )

        return "\n".join(lines)
