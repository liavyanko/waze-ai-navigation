"""
Utility functions for the Waze AI Navigation app
===============================================
Functions that are used across multiple modules to avoid circular imports.
"""

from typing import Optional, List, Dict, Any, Tuple
import requests
import math
from functools import lru_cache
import logging

from config import (
    NOMINATIM_URL,
    OSRM_URL,
    USER_AGENT,
    REQUEST_TIMEOUT,
    PHOTON_URL,
    NOMINATIM_REVERSE_URL,
)

@lru_cache(maxsize=256)
def photon_autocomplete(q: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Autocomplete via Photon (OpenStreetMap)."""
    if not q or len(q) < 2:
        return []
    try:
        headers = {"User-Agent": USER_AGENT}
        params = {"q": q, "limit": limit, "lang": "en"}
        r = requests.get(f"{PHOTON_URL}",
                         params=params,
                         headers=headers,
                         timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        out: List[Dict[str, Any]] = []
        for feat in data.get("features", []):
            props = feat.get("properties", {}) or {}
            coords = feat.get("geometry", {}).get("coordinates", [])
            if not coords or len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            label_parts = [props.get(k) for k in ("name", "city", "state", "country")]
            label = ", ".join([p for p in label_parts if p])
            if not label:
                label = props.get("name", "Unknown")
            out.append({"label": label, "lat": lat, "lon": lon})
        return out
    except Exception as e:
        logging.warning(f"Photon autocomplete failed for '{q}': {e}")
        return []

@lru_cache(maxsize=256)
def nominatim_search(q: str) -> Optional[Tuple[float, float, str]]:
    """Text → (lat, lon, label) using Nominatim."""
    if not q:
        return None
    try:
        headers = {"User-Agent": USER_AGENT}
        params = {"q": q, "format": "json", "limit": 1}
        r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        item = data[0]
        lat = float(item["lat"])
        lon = float(item["lon"])
        label = item.get("display_name", q)
        return lat, lon, label
    except Exception as e:
        logging.warning(f"Nominatim search failed for '{q}': {e}")
        return None

def _select_point(which: str, label: str, lat: float, lon: float):
    """Select a point and update session state."""
    import streamlit as st
    st.session_state[f"{which}_point"] = {"label": label, "lat": lat, "lon": lon}
    st.session_state[f"{which}_pending_query"] = label
    
    # Save query params
    try:
        sp = st.session_state.get("start_point") or {}
        ep = st.session_state.get("end_point") or {}
        params = {
            "slat": f"{sp.get('lat','')}", "slon": f"{sp.get('lon','')}",
            "elat": f"{ep.get('lat','')}", "elon": f"{ep.get('lon','')}",
        }
        try:
            st.query_params.update(params)
        except Exception:
            try:
                st.experimental_set_query_params(**params)
            except Exception:
                pass
    except Exception:
        pass
    
    # Safe rerun
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass
