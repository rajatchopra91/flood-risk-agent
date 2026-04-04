"""
geocoder.py — Unified geocoding with Photon primary + Nominatim fallback.

Photon (by Komoot): https://photon.komoot.io
- Faster for Indian city names, handles typos better
- No strict rate limit for reasonable use
- Returns GeoJSON FeatureCollection

Nominatim (OSM): fallback only
- Slower, 1 req/sec limit
- More complete for obscure Indian addresses
"""

import requests
from typing import Optional


PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "flood-risk-agent/1.0"


def _build_display_name(props: dict) -> str:
    """Build a human-readable display name from Photon properties."""
    parts = []
    for key in ["name", "locality", "district", "city", "county", "state", "country"]:
        val = props.get(key)
        if val and val not in parts:
            parts.append(val)
    return ", ".join(parts[:4]) if parts else "Unknown location"


def geocode_photon(query: str, country_code: str = "IN") -> Optional[dict]:
    """
    Geocode using Photon API.
    Returns: {lat, lon, display_name, source: 'photon'} or None
    """
    try:
        resp = requests.get(
            PHOTON_URL,
            params={"q": f"{query} India", "limit": 3, "lang": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=8
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None

        # Filter to India results, prefer city/locality over airports/amenities
        india_features = [
            f for f in features
            if f.get("properties", {}).get("countrycode", "").upper() == "IN"
        ]
        candidates = india_features if india_features else features

        # Prefer city/locality/district types over airports/amenities
        PREFERRED = {"city", "locality", "district", "borough", "suburb", "neighbourhood"}
        AVOIDED = {"aeroway", "aerodrome", "amenity"}
        preferred = [
            f for f in candidates
            if f.get("properties", {}).get("type", "").lower() in PREFERRED
        ]
        avoided = [
            f for f in candidates
            if f.get("properties", {}).get("type", "").lower() in AVOIDED
        ]
        # Pick best: preferred first, then non-avoided, then anything
        feat = (preferred or [f for f in candidates if f not in avoided] or candidates)[0]

        props = feat.get("properties", {})
        coords = feat["geometry"]["coordinates"]  # [lon, lat]
        lon, lat = coords[0], coords[1]

        # Round to 2dp for cache key consistency
        lat = round(lat, 2)
        lon = round(lon, 2)

        display_name = _build_display_name(props)

        return {
            "lat": lat,
            "lon": lon,
            "display_name": display_name,
            "source": "photon"
        }
    except Exception as e:
        print(f"Photon geocoding failed for '{query}': {e}")
        return None


def geocode_nominatim(query: str) -> Optional[dict]:
    """
    Geocode using Nominatim (OSM) — fallback only.
    Returns: {lat, lon, display_name, source: 'nominatim'} or None
    """
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": f"{query}, India", "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=10
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        if not data:
            return None

        result = data[0]
        lat = round(float(result["lat"]), 2)
        lon = round(float(result["lon"]), 2)

        return {
            "lat": lat,
            "lon": lon,
            "display_name": result.get("display_name", query),
            "source": "nominatim"
        }
    except Exception as e:
        print(f"Nominatim geocoding failed for '{query}': {e}")
        return None


def geocode(place_name: str) -> dict:
    """
    Geocode a place name with Photon -> Nominatim fallback chain.
    Raises ValueError if both fail.
    """
    # Try Photon first
    result = geocode_photon(place_name)
    if result:
        print(f"Geocoded '{place_name}' via Photon: {result['lat']}, {result['lon']}")
        return result

    # Fallback to Nominatim
    print(f"Photon failed for '{place_name}', trying Nominatim...")
    result = geocode_nominatim(place_name)
    if result:
        print(f"Geocoded '{place_name}' via Nominatim: {result['lat']}, {result['lon']}")
        return result

    raise ValueError(
        f"Could not geocode '{place_name}'. "
        "Try a major nearby city (e.g. 'Pune' instead of 'Urse, Pune')."
    )


def geocode_bbox(place_name: str, offset: float = 0.10) -> dict:
    """
    Geocode and return a bounding box for DEM download.
    offset: degrees (~11km at 0.10)
    """
    result = geocode(place_name)
    lat, lon = result["lat"], result["lon"]
    return {
        "south": lat - offset,
        "north": lat + offset,
        "west": lon - offset,
        "east": lon + offset,
        "center_lat": lat,
        "center_lon": lon,
        "city": place_name,
        "display_name": result["display_name"],
        "geocoder": result["source"]
    }
