from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import ChatRequest, ChatResponse, DiseaseItem, DiseaseLookupResponse, HospitalLookupResponse
from app.services.diseases import DiseaseService
from app.services.hospitals import HospitalLocator, HospitalLookupError, InvalidPincodeError
from app.services.localization import normalize_language
from app.services.pregnancy import PregnancyService
from app.services.retriever import KnowledgeRetriever
from app.services.responder import HealthAssistant
from app.services.schemes import SchemeService


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
FRONTEND_DIR = BASE_DIR / "frontend"

retriever = KnowledgeRetriever.from_json_files(
    [
        DATA_DIR / "medical_knowledge.json",
        DATA_DIR / "national_health_portal.json",
    ]
)
scheme_service = SchemeService.from_json(DATA_DIR / "schemes.json")
disease_service = DiseaseService.from_json(DATA_DIR / "disease_knowledge.json")
pregnancy_service = PregnancyService()
hospital_service = HospitalLocator(
    cache_path=DATA_DIR / "hospital_cache.json",
    seed_path=DATA_DIR / "pincode_hospitals_seed.json",
)
assistant = HealthAssistant(
    retriever=retriever,
    scheme_service=scheme_service,
    disease_service=disease_service,
    pregnancy_service=pregnancy_service,
)

app = FastAPI(
    title="NextGen Multilingual Health Assistant",
    version="0.1.0",
    description="RAG + triage + scheme navigator MVP for rural India use-cases",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "nextgen-health-assistant"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    language = normalize_language(payload.language)
    return assistant.answer(query=payload.query, language=language)


@app.get("/schemes")
def scheme_lookup(q: str, language: str = "en") -> dict:
    normalized_language = normalize_language(language)
    matches = scheme_service.search(query=q, language=normalized_language)
    answer, next_steps, sources = scheme_service.format_response(matches, normalized_language)
    return {
        "query": q,
        "language": normalized_language,
        "answer": answer,
        "next_steps": next_steps,
        "sources": sources,
    }


@app.get("/hospitals/nearest", response_model=HospitalLookupResponse)
def hospitals_nearest(
    pincode: str = Query(..., min_length=6, max_length=6),
    limit: int = Query(default=5, ge=1, le=10),
) -> HospitalLookupResponse:
    try:
        payload = hospital_service.lookup_nearest(pincode=pincode, limit=limit)
        return HospitalLookupResponse(**payload)
    except InvalidPincodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HospitalLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/diseases/search", response_model=DiseaseLookupResponse)
def disease_search(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=3, ge=1, le=5),
) -> DiseaseLookupResponse:
    matches = disease_service.search(query=q, limit=limit)
    payload = [DiseaseItem(**disease_service.to_public_item(item, score)) for item, score in matches]
    return DiseaseLookupResponse(query=q, matches=payload)
