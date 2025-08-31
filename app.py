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

from src.config.config import (
    NOMINATIM_URL,
    OSRM_URL,
    USER_AGENT,
    AVERAGE_SPEED_KMH,
    REQUEST_TIMEOUT,
    AVERAGE_NORMALIZATION_FACTOR,
    PHOTON_URL,
    NOMINATIM_REVERSE_URL,
)
from src.models.normalized_eta_model import predict_travel_multiplier, predict_travel_with_details
from src.services.traffic_manager import TrafficManager, TrafficConfig
from src.components.ui_components import (
    render_bottom_sheet,
    render_floating_buttons,
    render_route_chips,
    render_route_chips_streamlit,
    render_error_messages,
    render_weather_controls
)
from src.components.traffic_ui import (
    render_traffic_toggle,
    render_traffic_status,
    render_traffic_incidents,
    render_traffic_legend,
    render_traffic_provider_status,
    render_traffic_settings
)

from typing import Optional, List, Dict
import folium
from streamlit_folium import st_folium
from folium.plugins import MiniMap, Fullscreen, MeasureControl, MousePosition, LocateControl

from pathlib import Path

# Load CSS
css_path = Path(__file__).parent / "static" / "uiux.css"
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
    # Clear suggestions when a point is selected
    st.session_state[f"{which}_suggestions"] = []
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

    # Main search container
    with st.container():
        st.markdown("""
        <style>
        /* Hide any gray bars and reduce spacing */
        .stApp > header { background-color: transparent !important; }
        .stApp > div { background-color: transparent !important; }
        #MainMenu { visibility: hidden !important; }
        footer { visibility: hidden !important; }
        
        /* Reduce top margins and padding */
        .main .block-container { padding-top: 0 !important; }
        .stApp { padding-top: 0 !important; }
        
        /* Modern search container styling */
        .search-container {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            padding: 20px;
            margin: 0;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }
        
        /* Search input styling */
        .stTextInput > div > div > input {
            background: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
            border-radius: 12px !important;
            color: #ffffff !important;
            font-size: 16px !important;
            padding: 12px 16px !important;
            transition: all 0.3s ease !important;
        }
        
        .stTextInput > div > div > input:focus {
            background: rgba(255, 255, 255, 0.15) !important;
            border: 1px solid rgba(255, 255, 255, 0.5) !important;
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1) !important;
        }
        
        .stTextInput > div > div > input::placeholder {
            color: rgba(255, 255, 255, 0.6) !important;
        }
        
        /* Search button styling */
        .stButton > button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            border: none !important;
            border-radius: 12px !important;
            color: white !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            padding: 12px 20px !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4) !important;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6) !important;
        }
        
        /* Suggestion button styling */
        .suggestion-btn {
            background: rgba(255, 255, 255, 0.1) !important;
            border: 1px solid rgba(255, 255, 255, 0.2) !important;
            border-radius: 8px !important;
            color: #ffffff !important;
            font-size: 14px !important;
            padding: 8px 12px !important;
            margin: 4px 0 !important;
            transition: all 0.3s ease !important;
            text-align: left !important;
        }
        
        .suggestion-btn:hover {
            background: rgba(255, 255, 255, 0.2) !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            transform: translateX(4px) !important;
        }
        
        /* Divider styling */
        .search-divider {
            display: flex;
            align-items: center;
            justify-content: center;
            color: rgba(255, 255, 255, 0.6);
            font-size: 18px;
            margin: 10px 0;
        }
        
        /* Container spacing */
        .main-container {
            padding: 20px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="search-container">', unsafe_allow_html=True)
        
        # Search title
        st.markdown("### 🗺️ Plan Your Route", help="Enter start and destination locations")
        
        # Search inputs in columns
        col1, col2, col3 = st.columns([1, 0.2, 1])
        
        with col1:
            # Start location
            start_value = st.session_state.get("start_query", "")
            start_new = st.text_input(
                "📍 Start Location",
                value=start_value,
                key="start_query_input",
                placeholder="Enter start location...",
                help="Type to search for locations"
            )
            
            # Handle start location changes and autocomplete
            if start_new != start_value:
                st.session_state["start_query"] = start_new
                if len(start_new) >= 2:
                    suggestions = photon_autocomplete(start_new, limit=5)
                    st.session_state["start_suggestions"] = suggestions
                else:
                    st.session_state["start_suggestions"] = []
            
            # Show start suggestions
            if st.session_state.get("start_suggestions") and len(st.session_state.get("start_query", "")) >= 2:
                for i, suggestion in enumerate(st.session_state["start_suggestions"]):
                    if st.button(
                        f"📍 {suggestion['label']}", 
                        key=f"start_sugg_{i}", 
                        help=f"Select: {suggestion['label']}"
                    ):
                        _select_point("start", suggestion["label"], suggestion["lat"], suggestion["lon"])
                        st.session_state["start_suggestions"] = []
                        st.session_state["start_query"] = suggestion["label"]
                        st.rerun()
        
        with col2:
            # Arrow divider
            st.markdown('<div class="search-divider">↓</div>', unsafe_allow_html=True)
        
        with col3:
            # End location
            end_value = st.session_state.get("end_query", "")
            end_new = st.text_input(
                "🏁 Destination",
                value=end_value,
                key="end_query_input",
                placeholder="Enter destination...",
                help="Type to search for locations"
            )
            
            # Handle end location changes and autocomplete
            if end_new != end_value:
                st.session_state["end_query"] = end_new
                if len(end_new) >= 2:
                    suggestions = photon_autocomplete(end_new, limit=5)
                    st.session_state["end_suggestions"] = suggestions
                else:
                    st.session_state["end_suggestions"] = []
            
            # Show end suggestions
            if st.session_state.get("end_suggestions") and len(st.session_state.get("end_query", "")) >= 2:
                for i, suggestion in enumerate(st.session_state["end_suggestions"]):
                    if st.button(
                        f"🏁 {suggestion['label']}", 
                        key=f"end_sugg_{i}", 
                        help=f"Select: {suggestion['label']}"
                    ):
                        _select_point("end", suggestion["label"], suggestion["lat"], suggestion["lon"])
                        st.session_state["end_suggestions"] = []
                        st.session_state["end_query"] = suggestion["label"]
                        st.rerun()
        
        # Search button row
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        
        with col_btn2:
            if st.button("🔍 Find Route", key="search_route_btn", use_container_width=True):
                # Check if we have both points or if we need to search for them
                start_point = st.session_state.get("start_point")
                end_point = st.session_state.get("end_point")
                
                # If we have text queries but no points, try to search for them
                if not start_point and st.session_state.get("start_query"):
                    result = nominatim_search(st.session_state["start_query"])
                    if result:
                        lat, lon, label = result
                        _select_point("start", label, lat, lon)
                
                if not end_point and st.session_state.get("end_query"):
                    result = nominatim_search(st.session_state["end_query"])
                    if result:
                        lat, lon, label = result
                        _select_point("end", label, lat, lon)
                
                # Check final state
                if st.session_state.get("start_point") and st.session_state.get("end_point"):
                    # Clear all suggestions when route is found
                    st.session_state["start_suggestions"] = []
                    st.session_state["end_suggestions"] = []
                    st.success("Route calculation started!")
                    st.rerun()
                else:
                    st.warning("Please select both start and destination locations")
        
        st.markdown('</div>', unsafe_allow_html=True)

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

    # Initialize traffic manager
    traffic_manager = initialize_traffic_manager()
    
    # Render traffic toggle
    live_traffic_enabled = render_traffic_toggle()
    
    # Get traffic data if enabled
    traffic_data = None
    traffic_conditions = None  # Initialize traffic_conditions
    
    if live_traffic_enabled and sp and ep:
        try:
            # Create route coordinates for traffic analysis
            route_coordinates = [(sp["lat"], sp["lon"]), (ep["lat"], ep["lon"])]
            route_id = f"{sp['lat']:.4f},{sp['lon']:.4f}_{ep['lat']:.4f},{ep['lon']:.4f}"
            
            # Get traffic data
            traffic_data = traffic_manager.get_traffic_data(route_coordinates, route_id)
            
            # Convert to conditions format for ETA model
            if traffic_data:
                traffic_conditions = traffic_manager.get_traffic_conditions(traffic_data)
            else:
                traffic_conditions = None
                
        except Exception as e:
            st.error(f"Error fetching traffic data: {e}")
            traffic_conditions = None
    
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
        render_route_chips_streamlit(routes)
    
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
        
        # Traffic multiplier calculation with duration awareness and live traffic
        details = predict_travel_with_details(
            weather=context["weather"],
            time_of_day=context["time_of_day"],
            day_type=context["day_type"],
            road_problem=context["road_problem"],
            police_activity=context["police_activity"],
            driving_history=context["driving_history"],
            base_minutes=base_used or 60.0,  # Pass base duration for duration-aware scaling
            traffic_data=traffic_conditions  # Pass live traffic data
        )
        multiplier = details["multiplier"]

        # Final ETA
        final_minutes = (base_used or 0.0) * multiplier
        
        # Add calibration sample
        add_calib_sample(base["haversine_minutes"], base["osrm_minutes"])
        
        # Store in session state
        st.session_state["last_eta_min"] = final_minutes
        st.session_state["last_multiplier"] = multiplier

    # Render traffic information if available
    if live_traffic_enabled and traffic_data:
        render_traffic_status(traffic_conditions)
        render_traffic_incidents(traffic_conditions)
    
    # Render traffic legend
    if live_traffic_enabled:
        render_traffic_legend()
    
    # Render UI components
    render_floating_buttons()
    
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

# Initialize traffic manager globally
traffic_manager = None

def initialize_traffic_manager():
    """Initialize the traffic manager."""
    global traffic_manager
    if traffic_manager is None:
        config = TrafficConfig(
            enabled=True,
            provider_priority=['tomtom', 'here', 'mock'],
            cache_duration=300,
            fallback_to_mock=True,
            auto_refresh_interval=60
        )
        traffic_manager = TrafficManager(config)
    return traffic_manager

if __name__ == "__main__":
    main()
