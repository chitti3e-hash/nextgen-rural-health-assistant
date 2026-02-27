from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=800)
    language: str = Field(default="en", min_length=2, max_length=5)
    mode: Literal["text", "voice"] = "text"
    location: str | None = Field(default=None, max_length=120)


class SourceItem(BaseModel):
    title: str
    source: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    language: str
    urgency: Literal["normal", "critical"]
    disclaimer: str
    next_steps: list[str]
    confidence: float
    sources: list[SourceItem]


class HospitalItem(BaseModel):
    name: str
    distance_km: float
    address: str
    latitude: float
    longitude: float
    source: str


class HospitalLookupResponse(BaseModel):
    pincode: str
    location: str
    source: str
    cached: bool
    hospitals: list[HospitalItem]


class DiseaseItem(BaseModel):
    id: str
    name: str
    category: str
    score: float
    overview: str
    treatment_summary: str
    medicine_guidance: list[str]
    home_care: list[str]
    red_flags: list[str]
    source: str


class DiseaseLookupResponse(BaseModel):
    query: str
    matches: list[DiseaseItem]
