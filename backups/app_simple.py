"""
Waze AI Navigation App - Clean Architecture
==========================================
Main application logic with clean separation of concerns.
UI components are handled by the components module.
"""

import streamlit as st
from typing import Optional, Tuple, Dict, Any, List
import requests
import math
import logging
from functools import lru_cache
import json

from config import (
    NOMINATIM_URL,
    OSRM_URL,
    USER_AGENT,
    AVERAGE_SPEED_KMH,
    REQUEST_TIMEOUT,
    AVERAGE_NORMALIZATION_FACTOR,
    PHOTON_URL,
    NOMINATIM_REVERSE_URL,
)
from bayes_model import predict_travel_multiplier, predict_travel_with_details
from components.ui_components import (
    render_search_bar,
    render_bottom_sheet,
    render_floating_buttons,
    render_route_chips,
    render_error_messages,
    render_modern_search_inputs,
    render_autocomplete_suggestions,
    render_weather_controls
)

from typing import Optional, List, Dict
import folium
from streamlit_folium import st_folium
from folium.plugins import MiniMap, Fullscreen, MeasureControl, MousePosition, LocateControl

from pathlib import Path

# Load CSS
css_path = Path(__file__).parent / "static" / "css" / "uiux.css"
try:
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)
except Exception:
    pass

# -----------------------------
# Core Business Logic
# -----------------------------

def _safe_rerun():
    """Streamlit rerun that supports multiple versions."""
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

def fmt_minutes(m: Optional[float]) -> str:
    """Format minutes as human-readable time."""
    if m is None:
        return "—"
    try:
        m = float(m)
    except Exception:
        return "—"
    h = int(m // 60)
    mm = int(round(m % 60))
    return f"{h}h {mm}m" if h else f"{mm}m"

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

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
        return float(item["lat"]), float(item["lon"]), item.get("display_name", q)
    except Exception as e:
        logging.warning(f"Nominatim search failed for '{q}': {e}")
        return None

@lru_cache(maxsize=256)
def nominatim_reverse(lat: float, lon: float) -> Optional[str]:
    """Reverse geocoding using Nominatim."""
    try:
        headers = {"User-Agent": USER_AGENT}
        params = {"lat": lat, "lon": lon, "format": "jsonv2"}
        r = requests.get(NOMINATIM_REVERSE_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data.get("display_name")
    except Exception as e:
        logging.warning(f"Nominatim reverse failed for {lat},{lon}: {e}")
        return None

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

def osrm_route(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[Optional[float], Optional[list]]:
    """Query OSRM for a route. Returns (minutes, geometry as list of [lat, lon])."""
    try:
        coords = f"{lon1},{lat1};{lon2},{lat2}"
        params = {"overview": "full", "geometries": "geojson"}
        headers = {"User-Agent": USER_AGENT}
        url = f"{OSRM_URL}/{coords}"
        r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        routes = data.get("routes", [])
        if not routes:
            return None, None
        duration_sec = float(routes[0]["duration"])
        minutes = duration_sec / 60.0
        geometry = routes[0]["geometry"]["coordinates"]
        # Folium expects [lat, lon] pairs
        geometry_latlon = [[lat, lon] for lon, lat in geometry]
        return minutes, geometry_latlon
    except Exception as e:
        logging.warning(f"OSRM route failed: {e}")
        return None, None

# Weather mapping
WMO_MAP = {
    0: "clear", 1: "cloudy", 2: "cloudy", 3: "cloudy",
    45: "cloudy", 48: "cloudy",
    51: "rain", 53: "rain", 55: "rain",
    56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain",
    66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow",
    77: "snow",
    80: "rain", 81: "rain", 82: "rain",
    85: "snow", 86: "snow",
    95: "storm",
    96: "storm", 99: "storm",
}

def map_wmo_to_category(code: int) -> str:
    return WMO_MAP.get(code, "cloudy")

def fetch_weather_auto(lat: float, lon: float) -> Dict[str, Any]:
    """Open-Meteo current weather by lat/lon."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "timezone": "auto",
        }
        r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json().get("current_weather", {})
        code = int(data.get("weathercode", 1))
        category = map_wmo_to_category(code)
        return {
            "category": category,
            "code": code,
            "temp_c": data.get("temperature"),
            "windspeed": data.get("windspeed"),
            "source": "open-meteo",
        }
    except Exception as e:
        logging.warning(f"weather fetch failed: {e}")
        return {"category": None, "code": None, "temp_c": None, "windspeed": None, "source": "open-meteo"}

def osrm_routes(lat1: float, lon1: float, lat2: float, lon2: float, max_routes: int = 3, avoid_motorways: bool = False):
    """Get multiple route alternatives from OSRM."""
    try:
        coords = f"{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "true",
            "steps": "false",
        }
        if avoid_motorways:
            params["exclude"] = "motorway"
        headers = {"User-Agent": USER_AGENT}
        url = f"{OSRM_URL}/{coords}"
        r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        routes = []
        for rt in data.get("routes", [])[:max_routes]:
            duration_min = float(rt["duration"]) / 60.0
            distance_km = float(rt["distance"]) / 1000.0
            geometry_lonlat = rt["geometry"]["coordinates"]
            geometry_latlon = [[lat, lon] for lon, lat in geometry_lonlat]
            routes.append({"minutes": duration_min, "km": distance_km, "geometry": geometry_latlon})
        return routes
    except Exception:
        return []

@st.cache_data(show_spinner=False, ttl=10*60)
def osrm_routes_cached(lat1: float, lon1: float, lat2: float, lon2: float, max_routes: int, avoid_motorways: bool):
    return osrm_routes(lat1, lon1, lat2, lon2, max_routes=max_routes, avoid_motorways=avoid_motorways)

def add_calib_sample(hav_m: Optional[float], osrm_m: Optional[float]):
    """Add calibration sample for normalization factor."""
    if "calib_samples" not in st.session_state:
        st.session_state["calib_samples"] = []
    if hav_m and osrm_m and hav_m > 0:
        st.session_state["calib_samples"].append((hav_m, osrm_m))

def current_norm_factor() -> float:
    """Get current normalization factor from calibration samples."""
    samples = st.session_state.get("calib_samples", [])
    if not samples:
        return AVERAGE_NORMALIZATION_FACTOR
    ratios = [osrm / hav for (hav, osrm) in samples if hav and hav > 0]
    if not ratios:
        return AVERAGE_NORMALIZATION_FACTOR
    return sum(ratios) / len(ratios)

def compute_base_times(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Optional[float]]:
    """Compute base travel times using OSRM and Haversine."""
    osrm_minutes, _ = osrm_route(lat1, lon1, lat2, lon2)

    km = _haversine_km(lat1, lon1, lat2, lon2)
    haversine_minutes = (km / max(1e-6, AVERAGE_SPEED_KMH)) * 60.0

    normalization_factor = None
    normalized_haversine = None
    if osrm_minutes and haversine_minutes > 0:
        normalization_factor = osrm_minutes / haversine_minutes
        normalized_haversine = haversine_minutes * normalization_factor
    else:
        normalization_factor = current_norm_factor()
        normalized_haversine = haversine_minutes * normalization_factor

    return {
        "osrm_minutes": osrm_minutes,
        "haversine_minutes": haversine_minutes,
        "normalized_haversine": normalized_haversine,
        "normalization_factor": normalization_factor,
    }

def render_map(sp: Optional[Dict[str, float]], ep: Optional[Dict[str, float]], geometry: Optional[List[List[float]]]) -> Any:
    """Render Folium map with route and markers."""
    DEFAULT_CENTER = (31.4118, 35.0818)
    DEFAULT_ZOOM = 7

    if sp and ep:
        center_lat = (sp["lat"] + ep["lat"]) / 2.0
        center_lon = (sp["lon"] + ep["lon"]) / 2.0
        zoom = 12
    elif sp:
        center_lat, center_lon = sp["lat"], sp["lon"]
        zoom = 13
    elif ep:
        center_lat, center_lon = ep["lat"], ep["lon"]
        zoom = 13
    else:
        center_lat, center_lon = DEFAULT_CENTER
        zoom = DEFAULT_ZOOM

    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, control_scale=True)

    # Add plugins
    try:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
        Fullscreen().add_to(m)
        MeasureControl(primary_length_unit='kilometers').add_to(m)
        MousePosition(position='bottomleft').add_to(m)
        LocateControl(auto_start=False).add_to(m)
    except Exception:
        pass

    # Add markers
    if sp:
        folium.Marker([sp["lat"], sp["lon"]], tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    if ep:
        folium.Marker([ep["lat"], ep["lon"]], tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    # Add route
    if geometry and len(geometry) >= 2:
        folium.PolyLine(geometry, weight=6, opacity=0.85).add_to(m)
        try:
            m.fit_bounds(geometry)
        except Exception:
            pass
    elif sp and ep:
        m.fit_bounds([[sp["lat"], sp["lon"]], [ep["lat"], ep["lon"]]])

    ret = st_folium(m, use_container_width=True, height=420)
    return ret

def _ensure_state():
    """Initialize session state with default values."""
    defaults = {
        "start_query": "",
        "end_query": "",
        "start_point": None,
        "end_point": None,
        "start_pending_query": None,
        "end_pending_query": None,
        "start_suggestions": [],
        "end_suggestions": [],
        "favorites": [],
        "history": [],
        "calib_samples": [],
        "active_pick": "off",
        "avoid_motorways": False,
        "weather_mode": "auto",
        "weather_pending": None,
        "last_weather": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _save_query_params():
    """Save points to URL for sharing."""
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

def _load_query_params():
    """Load points from URL."""
    try:
        qp = dict(st.query_params)
        slat = qp.get("slat")
        slon = qp.get("slon")
        elat = qp.get("elat")
        elon = qp.get("elon")
        def _to_float(x):
            try: return float(x) if x not in (None, "", []) else None
            except: return None
        slat, slon, elat, elon = _to_float(slat), _to_float(slon), _to_float(elat), _to_float(elon)
    except Exception:
        qp = st.experimental_get_query_params()
        def _get(k):
            v = qp.get(k, [""])
            return v[0] if isinstance(v, list) and v else ""
        def _to_float(x):
            try: return float(x) if x else None
            except: return None
        slat = _to_float(_get("slat")); slon = _to_float(_get("slon"))
        elat = _to_float(_get("elat")); elon = _to_float(_get("elon"))

    if slat is not None and slon is not None:
        st.session_state["start_point"] = {"label": f"LatLng({slat:.4f},{slon:.4f})", "lat": slat, "lon": slon}
    if elat is not None and elon is not None:
        st.session_state["end_point"] = {"label": f"LatLng({elat:.4f},{elon:.4f})", "lat": elat, "lon": elon}

def _select_point(which: str, label: str, lat: float, lon: float):
    """Select a point and update session state."""
    st.session_state[f"{which}_point"] = {"label": label, "lat": lat, "lon": lon}
    st.session_state[f"{which}_pending_query"] = label
    _save_query_params()
    _safe_rerun()

# -----------------------------
# Main Application
# -----------------------------

def main():
    """Main application function with clean architecture."""
    st.set_page_config(
        page_title="🚗 Waze AI Navigation", 
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    logging.basicConfig(level=logging.INFO)

    # Initialize state
    _ensure_state()
    _load_query_params()

    # Render modern search inputs with live autocomplete (ORIGINAL BEAUTIFUL DESIGN)
    search_html = '<div class="modern-search-container"><div class="search-inputs-wrapper"><div class="search-input-group"><div class="input-container"><input type="text" id="start-input" class="search-input-field" placeholder="Start location" autocomplete="off" oninput="handleStartInput(this.value)" onfocus="showStartSuggestions()" onblur="hideStartSuggestions()" /><div class="input-icon"><span class="material-icons-outlined">my_location</span></div></div><div id="start-suggestions" class="suggestions-dropdown" style="display: none;"></div></div><div class="search-divider"><div class="divider-line"></div><div class="divider-arrow"><span class="material-icons-outlined">arrow_downward</span></div></div><div class="search-input-group"><div class="input-container"><input type="text" id="end-input" class="search-input-field" placeholder="Destination" autocomplete="off" oninput="handleEndInput(this.value)" onfocus="showEndSuggestions()" onblur="hideEndSuggestions()" /><div class="input-icon"><span class="material-icons-outlined">place</span></div></div><div id="end-suggestions" class="suggestions-dropdown" style="display: none;"></div></div><button class="search-button" onclick="calculateRoute()"><span class="material-icons-outlined">navigation</span></button></div></div>'
    st.markdown(search_html, unsafe_allow_html=True)
    
    # Add simple working JavaScript
    st.markdown("""
    <script>
    // Simple working autocomplete functions
    window.handleStartInput = function(value) {
        if (value.length < 2) {
            const dropdown = document.getElementById('start-suggestions');
            if (dropdown) dropdown.style.display = 'none';
            return;
        }
        
        // Generate mock suggestions
        const suggestions = [
            { label: value + ' City Center', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Station', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Mall', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Park', lat: 32.0853, lon: 34.7818 }
        ];
        
        // Show suggestions
        const dropdown = document.getElementById('start-suggestions');
        if (dropdown) {
            dropdown.innerHTML = suggestions.map(s => 
                '<div class="suggestion-item" onclick="selectStartLocation(\\'' + s.label + '\\', ' + s.lat + ', ' + s.lon + ')">' +
                '<span class="location-icon material-icons-outlined">my_location</span>' +
                '<div><div class="location-text">' + s.label + '</div>' +
                '<div class="location-details">Tel Aviv, Israel</div></div></div>'
            ).join('');
            dropdown.style.display = 'block';
        }
    };
    
    window.handleEndInput = function(value) {
        if (value.length < 2) {
            const dropdown = document.getElementById('end-suggestions');
            if (dropdown) dropdown.style.display = 'none';
            return;
        }
        
        // Generate mock suggestions
        const suggestions = [
            { label: value + ' City Center', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Station', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Mall', lat: 32.0853, lon: 34.7818 },
            { label: value + ' Park', lat: 32.0853, lon: 34.7818 }
        ];
        
        // Show suggestions
        const dropdown = document.getElementById('end-suggestions');
        if (dropdown) {
            dropdown.innerHTML = suggestions.map(s => 
                '<div class="suggestion-item" onclick="selectEndLocation(\\'' + s.label + '\\', ' + s.lat + ', ' + s.lon + ')">' +
                '<span class="location-icon material-icons-outlined">place</span>' +
                '<div><div class="location-text">' + s.label + '</div>' +
                '<div class="location-details">Tel Aviv, Israel</div></div></div>'
            ).join('');
            dropdown.style.display = 'block';
        }
    };
    
    // Simple location selection functions
    window.selectStartLocation = function(label, lat, lon) {
        const input = document.getElementById('start-input');
        if (input) input.value = label;
        
        // Hide suggestions
        const dropdown = document.getElementById('start-suggestions');
        if (dropdown) dropdown.style.display = 'none';
        
        // Store in localStorage
        localStorage.setItem('waze_start_location', JSON.stringify({label: label, lat: lat, lon: lon}));
        
        // Show success message
        alert('📍 Start location set: ' + label);
    };
    
    window.selectEndLocation = function(label, lat, lon) {
        const input = document.getElementById('end-input');
        if (input) input.value = label;
        
        // Hide suggestions
        const dropdown = document.getElementById('end-suggestions');
        if (dropdown) dropdown.style.display = 'none';
        
        // Store in localStorage
        localStorage.setItem('waze_end_location', JSON.stringify({label: label, lat: lat, lon: lon}));
        
        // Show success message
        alert('🏁 End location set: ' + label);
    };
    
    // Simple route calculation
    window.calculateRoute = function() {
        const startLoc = localStorage.getItem('waze_start_location');
        const endLoc = localStorage.getItem('waze_end_location');
        
        if (startLoc && endLoc) {
            const start = JSON.parse(startLoc);
            const end = JSON.parse(endLoc);
            alert('🚗 Route calculation: ' + start.label + ' → ' + end.label);
        } else {
            alert('⚠️ Please select both start and end locations');
        }
    };
    
    // Show/hide functions
    window.showStartSuggestions = function() {
        // Suggestions are shown by handleStartInput
    };
    
    window.showEndSuggestions = function() {
        // Suggestions are shown by handleEndInput
    };
    
    window.hideStartSuggestions = function() {
        const dropdown = document.getElementById('start-suggestions');
        if (dropdown) dropdown.style.display = 'none';
    };
    
    window.hideEndSuggestions = function() {
        const dropdown = document.getElementById('end-suggestions');
        if (dropdown) dropdown.style.display = 'none';
    };
    </script>
    """, unsafe_allow_html=True)
    
    # Add top padding for floating elements
    st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)

    # Get current points
    sp = st.session_state.get("start_point")
    ep = st.session_state.get("end_point")
    
    # Auto weather update
    focus_lat = focus_lon = None
    if sp and ep:
        focus_lat, focus_lon = (sp["lat"] + ep["lat"]) / 2.0, (sp["lon"] + ep["lon"]) / 2.0
    elif sp:
        focus_lat, focus_lon = sp["lat"], sp["lon"]
    elif ep:
        focus_lat, focus_lon = ep["lat"], ep["lon"]

    if st.session_state.get("weather_mode") == "auto" and focus_lat is not None:
        wx = fetch_weather_auto(focus_lat, focus_lon)
        st.session_state["last_weather"] = wx
        if wx.get("category"):
            st.session_state["weather_pending"] = wx["category"]

    # Render weather controls
    context = render_weather_controls()

    # Map and route handling
    routes = []
    route_idx = 0
    geometry = None
    final_minutes = None
    multiplier = None
    
    if sp and ep:
        try:
            routes = osrm_routes_cached(sp["lat"], sp["lon"], ep["lat"], ep["lon"], max_routes=3, avoid_motorways=st.session_state.get("avoid_motorways", False))
        except Exception:
            routes = []

        if routes:
            route_idx = st.session_state.get("selected_route", 0)
            geometry = routes[route_idx]["geometry"]
        else:
            try:
                _, geometry = osrm_route(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
            except Exception:
                geometry = None

    # Render the map
    ret = render_map(sp, ep, geometry)
    
    # Route alternatives display
    if routes and len(routes) > 1:
        st.markdown(render_route_chips(routes), unsafe_allow_html=True)
    
    # Map click handling
    if ret and ret.get("last_clicked"):
        lat = ret["last_clicked"]["lat"]
        lon = ret["last_clicked"]["lng"]
        mode = st.session_state.get("active_pick", "off")
        if mode == "start":
            _select_point("start", f"LatLng({lat:.4f},{lon:.4f})", lat, lon)
        elif mode == "end":
            _select_point("end", f"LatLng({lat:.4f},{lon:.4f})", lat, lon)
    
    # Calculate ETA if we have both points
    if sp and ep:
        # Base time calculation
        base = compute_base_times(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
        base_used = base["osrm_minutes"] or base["normalized_haversine"]
        
        # Traffic multiplier calculation
        details = predict_travel_with_details(
            weather=context["weather"],
            time_of_day=context["time_of_day"],
            day_type=context["day_type"],
            road_problem=context["road_problem"],
            police_activity=context["police_activity"],
            driving_history=context["driving_history"],
        )
        multiplier = details["multiplier"]
        
        # Final ETA
        final_minutes = (base_used or 0.0) * multiplier
        
        # Add calibration sample
        add_calib_sample(base["haversine_minutes"], base["osrm_minutes"])
        
        # Store in session state
        st.session_state["last_eta_min"] = final_minutes
        st.session_state["last_multiplier"] = multiplier

    # Render UI components
    st.markdown(render_floating_buttons(), unsafe_allow_html=True)
    
    if final_minutes:
        st.markdown(render_bottom_sheet(final_minutes, multiplier, routes[route_idx] if routes else None), unsafe_allow_html=True)
    
    # Error handling
    error_type = None
    if not sp and not ep:
        error_type = "no_locations"
    elif not sp:
        error_type = "no_start"
    elif not ep:
        error_type = "no_end"
    
    if error_type:
        st.markdown(render_error_messages(error_type), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
