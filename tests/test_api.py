from fastapi.testclient import TestClient

from app.main import app, hospital_service


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_critical_triage_response() -> None:
    payload = {
        "query": "My uncle has chest pain and difficulty breathing right now.",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "critical"
    assert len(body["next_steps"]) >= 2


def test_scheme_lookup_from_chat() -> None:
    payload = {
        "query": "How can I get Ayushman Bharat card benefits?",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "normal"
    assert "Ayushman Bharat" in body["answer"]
    assert body["confidence"] >= 0.8


def test_low_confidence_safety_fallback() -> None:
    payload = {
        "query": "qwxz ptlm randomnotmedical term test",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "normal"
    assert body["confidence"] <= 0.3


def test_disease_chat_response() -> None:
    payload = {
        "query": "What are treatment medicines and home remedies for dengue?",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "normal"
    assert "Dengue" in body["answer"]
    assert "Medicines commonly used" in body["answer"]


def test_disease_search_endpoint() -> None:
    response = client.get("/diseases/search?q=diabetes&limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "diabetes"
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["name"] == "Type 2 Diabetes"
    assert len(payload["matches"][0]["medicine_guidance"]) > 0


def test_pregnancy_query_gets_clinical_guidance_not_scheme() -> None:
    payload = {
        "query": "I am pregnant for 7 months",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "Pregnancy support" in body["answer"]
    assert "Janani Suraksha" not in body["answer"]
    assert any("ANC" in step or "fetal" in step.lower() for step in body["next_steps"])


def test_invalid_pincode_returns_400() -> None:
    response = client.get("/hospitals/nearest?pincode=12345")
    assert response.status_code == 422


def test_nearest_hospitals_lookup(monkeypatch) -> None:
    def fake_lookup_nearest(pincode: str, limit: int = 5) -> dict:
        assert pincode == "560001"
        assert limit == 3
        return {
            "pincode": "560001",
            "location": "Bengaluru G.P.O, Karnataka, India",
            "source": "OpenStreetMap Nominatim + Overpass",
            "cached": False,
            "hospitals": [
                {
                    "name": "Bowring and Lady Curzon Hospital",
                    "distance_km": 2.0,
                    "address": "Shivaji Nagar, Bengaluru",
                    "latitude": 12.9852,
                    "longitude": 77.6075,
                    "source": "OpenStreetMap",
                }
            ],
        }

    monkeypatch.setattr(hospital_service, "lookup_nearest", fake_lookup_nearest)
    response = client.get("/hospitals/nearest?pincode=560001&limit=3")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pincode"] == "560001"
    assert payload["hospitals"][0]["name"] == "Bowring and Lady Curzon Hospital"


def test_symptom_query_does_not_return_generic_icd_template() -> None:
    payload = {
        "query": "I have headache and fever for 2 days",
        "language": "en",
    }
    response = client.post("/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "normal"
    assert body["answer"].startswith("Based on verified health resources")
    assert "Waiting period for investigation" not in body["answer"]
