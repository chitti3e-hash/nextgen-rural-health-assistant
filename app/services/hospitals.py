from __future__ import annotations

from pathlib import Path
import json
import math
import re
import time

import httpx


class InvalidPincodeError(ValueError):
    pass


class HospitalLookupError(RuntimeError):
    pass


class HospitalLocator:
    def __init__(self, cache_path: Path, seed_path: Path | None = None, cache_ttl_hours: int = 12):
        self.cache_path = cache_path
        self.seed_path = seed_path
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self._cache = self._load_json(cache_path, default={})
        self._seed_data = self._load_json(seed_path, default={}) if seed_path else {}

    @staticmethod
    def _load_json(path: Path | None, default: dict | list) -> dict | list:
        if not path or not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def _save_cache(self) -> None:
        self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_pincode(pincode: str) -> str:
        normalized = pincode.strip()
        if not re.fullmatch(r"[1-9][0-9]{5}", normalized):
            raise InvalidPincodeError("Pincode must be a valid 6-digit Indian postal code.")
        return normalized

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_km = 6371.0
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        lat_diff = math.radians(lat2 - lat1)
        lon_diff = math.radians(lon2 - lon1)
        a = (
            math.sin(lat_diff / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(lon_diff / 2) ** 2
        )
        return round(2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)

    @staticmethod
    def _format_address(tags: dict) -> str:
        fields = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:city"),
            tags.get("addr:state"),
        ]
        cleaned = [field for field in fields if field]
        if cleaned:
            return ", ".join(cleaned)
        return "Address details not available"

    @staticmethod
    def _nominatim_request_params(pincode: str) -> list[dict[str, str]]:
        return [
            {
                "postalcode": pincode,
                "country": "India",
                "format": "jsonv2",
                "addressdetails": "1",
                "limit": "1",
            },
            {
                "q": f"{pincode}, India",
                "format": "jsonv2",
                "addressdetails": "1",
                "limit": "1",
            },
        ]

    def _resolve_coordinates(self, pincode: str) -> tuple[float, float, str]:
        headers = {"User-Agent": "nextgen-health-assistant/1.0"}
        with httpx.Client(timeout=15.0, headers=headers) as client:
            for params in self._nominatim_request_params(pincode):
                response = client.get("https://nominatim.openstreetmap.org/search", params=params)
                response.raise_for_status()
                payload = response.json()
                if payload:
                    top = payload[0]
                    latitude = float(top["lat"])
                    longitude = float(top["lon"])
                    location = top.get("display_name", f"Pincode {pincode}, India")
                    return latitude, longitude, location

        raise HospitalLookupError("Unable to resolve pincode location at the moment.")

    def _search_hospitals(self, latitude: float, longitude: float, max_results: int) -> list[dict]:
        query = f"""
[out:json][timeout:30];
(
  node["amenity"="hospital"](around:30000,{latitude},{longitude});
  way["amenity"="hospital"](around:30000,{latitude},{longitude});
  relation["amenity"="hospital"](around:30000,{latitude},{longitude});
);
out center {max_results};
""".strip()

        headers = {"User-Agent": "nextgen-health-assistant/1.0"}
        with httpx.Client(timeout=30.0, headers=headers) as client:
            response = client.post("https://overpass-api.de/api/interpreter", data={"data": query})
            response.raise_for_status()
            payload = response.json()

        candidates: list[dict] = []
        dedupe: set[str] = set()
        for item in payload.get("elements", []):
            tags = item.get("tags", {})
            if item.get("type") == "node":
                hospital_lat = item.get("lat")
                hospital_lon = item.get("lon")
            else:
                center = item.get("center", {})
                hospital_lat = center.get("lat")
                hospital_lon = center.get("lon")

            if hospital_lat is None or hospital_lon is None:
                continue

            name = tags.get("name") or "Unnamed Hospital"
            dedupe_key = f"{name}:{round(float(hospital_lat), 4)}:{round(float(hospital_lon), 4)}"
            if dedupe_key in dedupe:
                continue
            dedupe.add(dedupe_key)

            candidates.append(
                {
                    "name": name,
                    "distance_km": self._haversine_km(latitude, longitude, float(hospital_lat), float(hospital_lon)),
                    "address": self._format_address(tags),
                    "latitude": round(float(hospital_lat), 6),
                    "longitude": round(float(hospital_lon), 6),
                    "source": "OpenStreetMap",
                }
            )

        candidates.sort(key=lambda item: item["distance_km"])
        return candidates[:max_results]

    def _get_seed_fallback(self, pincode: str, limit: int) -> dict | None:
        entry = self._seed_data.get(pincode)
        if not entry:
            return None
        return {
            "pincode": pincode,
            "location": entry.get("location", f"Pincode {pincode}, India"),
            "source": "Seed hospital dataset",
            "cached": True,
            "hospitals": entry.get("hospitals", [])[:limit],
        }

    def lookup_nearest(self, pincode: str, limit: int = 5) -> dict:
        normalized_pincode = self._normalize_pincode(pincode)
        normalized_limit = max(1, min(limit, 10))
        now = int(time.time())

        cached_entry = self._cache.get(normalized_pincode)
        if cached_entry and (now - int(cached_entry.get("timestamp", 0)) < self.cache_ttl_seconds):
            return {
                "pincode": normalized_pincode,
                "location": cached_entry["location"],
                "source": cached_entry["source"],
                "cached": True,
                "hospitals": cached_entry["hospitals"][:normalized_limit],
            }

        try:
            latitude, longitude, location = self._resolve_coordinates(normalized_pincode)
            hospitals = self._search_hospitals(latitude, longitude, max_results=25)
            if not hospitals:
                raise HospitalLookupError("No hospitals were found near this pincode.")

            entry = {
                "timestamp": now,
                "location": location,
                "source": "OpenStreetMap Nominatim + Overpass",
                "hospitals": hospitals,
            }
            self._cache[normalized_pincode] = entry
            self._save_cache()

            return {
                "pincode": normalized_pincode,
                "location": location,
                "source": entry["source"],
                "cached": False,
                "hospitals": hospitals[:normalized_limit],
            }
        except (httpx.HTTPError, HospitalLookupError):
            fallback = self._get_seed_fallback(normalized_pincode, normalized_limit)
            if fallback:
                return fallback
            raise HospitalLookupError(
                "Hospital lookup failed right now. Please try again, or ask a nearby PHC/ASHA worker."
            )

