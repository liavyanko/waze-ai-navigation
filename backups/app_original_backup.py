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

from typing import Optional, List, Dict

import folium
from streamlit_folium import st_folium
from folium.plugins import MiniMap, Fullscreen, MeasureControl, MousePosition, LocateControl

from pathlib import Path
css_path = Path(__file__).with_name("uiux.css")
try:
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)
except Exception:
    pass  # אם אין קובץ CSS, נמשיך כרגיל


# -----------------------------
# Helpers
# -----------------------------
def _safe_rerun():
    """
    Streamlit rerun that supports multiple versions.
    """
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def fmt_minutes(m: Optional[float]) -> str:
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
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@lru_cache(maxsize=256)
def nominatim_search(q: str) -> Optional[Tuple[float, float, str]]:
    """
    Text → (lat, lon, label) using Nominatim.
    """
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
    """
    Autocomplete via Photon (OpenStreetMap). Returns list of {label, lat, lon}.
    Designed to be lightweight and safe on failures.
    """
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
    """
    Query OSRM for a route. Returns (minutes, geometry as list of [lat, lon]).
    """
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

    # ---------- Weather (Open-Meteo) ----------
WMO_MAP = {
    # clear
    0: "clear",
    # mainly clear / partly cloudy / overcast
    1: "cloudy", 2: "cloudy", 3: "cloudy",
    # fog/mist
    45: "cloudy", 48: "cloudy",
    # drizzle
    51: "rain", 53: "rain", 55: "rain",
    # freezing drizzle
    56: "rain", 57: "rain",
    # rain
    61: "rain", 63: "rain", 65: "rain",
    # freezing rain
    66: "rain", 67: "rain",
    # snow fall
    71: "snow", 73: "snow", 75: "snow",
    # snow grains
    77: "snow",
    # rain showers
    80: "rain", 81: "rain", 82: "rain",
    # snow showers
    85: "snow", 86: "snow",
    # thunderstorm
    95: "storm",
    # thunderstorm with hail
    96: "storm", 99: "storm",
}

def map_wmo_to_category(code: int) -> str:
    return WMO_MAP.get(code, "cloudy")

def fetch_weather_auto(lat: float, lon: float) -> Dict[str, Any]:
    """
    Open-Meteo current weather by lat/lon.
    Returns: {"category": str, "code": int, "temp_c": float, "windspeed": float, "source": "open-meteo"}
    """
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


# ---------- OSRM Alternatives + caching ----------
def osrm_routes(lat1: float, lon1: float, lat2: float, lon2: float, max_routes: int = 3, avoid_motorways: bool = False):
    """
    מחזיר רשימת מסלולים: [{"minutes": float, "km": float, "geometry": [[lat,lon], ...]}, ...]
    אם אין מסלול – מחזיר [].
    """
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


# ---------- Calibration ----------
def add_calib_sample(hav_m: Optional[float], osrm_m: Optional[float]):
    if "calib_samples" not in st.session_state:
        st.session_state["calib_samples"] = []
    if hav_m and osrm_m and hav_m > 0:
        st.session_state["calib_samples"].append((hav_m, osrm_m))


def current_norm_factor() -> float:
    samples = st.session_state.get("calib_samples", [])
    if not samples:
        return AVERAGE_NORMALIZATION_FACTOR
    ratios = [osrm / hav for (hav, osrm) in samples if hav and hav > 0]
    if not ratios:
        return AVERAGE_NORMALIZATION_FACTOR
    return sum(ratios) / len(ratios)


def compute_base_times(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Optional[float]]:
    """
    Returns dict with osrm_minutes, haversine_minutes, normalized_haversine, normalization_factor.
    """
    osrm_minutes, _ = osrm_route(lat1, lon1, lat2, lon2)

    km = _haversine_km(lat1, lon1, lat2, lon2)
    haversine_minutes = (km / max(1e-6, AVERAGE_SPEED_KMH)) * 60.0

    normalization_factor = None
    normalized_haversine = None
    if osrm_minutes and haversine_minutes > 0:
        normalization_factor = osrm_minutes / haversine_minutes
        normalized_haversine = haversine_minutes * normalization_factor
    else:
        # Fallback: calibrated factor if available; otherwise project-average
        normalization_factor = current_norm_factor()
        normalized_haversine = haversine_minutes * normalization_factor

    return {
        "osrm_minutes": osrm_minutes,
        "haversine_minutes": haversine_minutes,
        "normalized_haversine": normalized_haversine,
        "normalization_factor": normalization_factor,
    }


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    return (lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0


def render_map(
    sp: Optional[Dict[str, float]],
    ep: Optional[Dict[str, float]],
    geometry: Optional[List[List[float]]],
) -> Any:
    """
    Renders a Folium map in all cases:
    - no points: default center
    - one point: center on that point
    - two points: fit bounds, draw polyline if provided
    Returns st_folium return dict (so we can read clicks).
    """
    # ברירת מחדל (ישראל בקירוב; שנה אם תרצה)
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

    # תוספים שימושיים
    try:
        MiniMap(toggle_display=True, minimized=True).add_to(m)
        Fullscreen().add_to(m)
        MeasureControl(primary_length_unit='kilometers').add_to(m)
        MousePosition(position='bottomleft').add_to(m)
        LocateControl(auto_start=False).add_to(m)
    except Exception:
        pass

    # סימונים אם קיימים
    if sp:
        folium.Marker([sp["lat"], sp["lon"]], tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    if ep:
        folium.Marker([ep["lat"], ep["lon"]], tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    # נתיב (אם יש), ואז התאמת גבולות
    if geometry and len(geometry) >= 2:
        folium.PolyLine(geometry, weight=6, opacity=0.85).add_to(m)
        try:
            m.fit_bounds(geometry)
        except Exception:
            pass
    elif sp and ep:
        m.fit_bounds([[sp["lat"], sp["lon"]], [ep["lat"], ep["lon"]]])

    # בלי עטיפות HTML — רק זה
    ret = st_folium(m, use_container_width=True, height=420)
    return ret


def _ensure_state():
    defaults = {
        "start_query": "",
        "end_query": "",
        "start_point": None,
        "end_point": None,
        # NEW: "pending" values to set BEFORE the widget is created on next run
        "start_pending_query": None,
        "end_pending_query": None,
        "start_suggestions": [],
        "end_suggestions": [],
        # New feature flags/data
        "favorites": [],
        "history": [],
        "calib_samples": [],
        "active_pick": "off",
        "avoid_motorways": False,
        "weather_mode": "auto",            # "auto" | "manual"
        "weather_pending": None,           # to set selectbox default safely
        "last_weather": None,              # dict returned from fetch_weather_auto
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _save_query_params():
    """שומר נקודות ל־URL כדי לשתף לינק מצב."""
    sp = st.session_state.get("start_point") or {}
    ep = st.session_state.get("end_point") or {}
    params = {
        "slat": f"{sp.get('lat','')}", "slon": f"{sp.get('lon','')}",
        "elat": f"{ep.get('lat','')}", "elon": f"{ep.get('lon','')}",
    }
    try:
        st.query_params.update(params)  # Streamlit ≥1.33
    except Exception:
        try:
            st.experimental_set_query_params(**params)  # ישן
        except Exception:
            pass


def _load_query_params():
    """טוען נקודות מה־URL (אם קיימות) בתחילת הריצה."""
    try:
        qp = dict(st.query_params)  # חדש
        # בפורמט החדש הערכים הם מחרוזות
        slat = qp.get("slat")
        slon = qp.get("slon")
        elat = qp.get("elat")
        elon = qp.get("elon")
        def _to_float(x):
            try: return float(x) if x not in (None, "", []) else None
            except: return None
        slat, slon, elat, elon = _to_float(slat), _to_float(slon), _to_float(elat), _to_float(elon)
    except Exception:
        qp = st.experimental_get_query_params()  # ישן
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
    st.session_state[f"{which}_point"] = {"label": label, "lat": lat, "lon": lon}
    # במקום לשנות את ערך הווידג׳ט עכשיו (אסור), נשמור "pending"
    st.session_state[f"{which}_pending_query"] = label
    _save_query_params()
    _safe_rerun()


def _point_ui(which: str, title: str):
    query_key   = f"{which}_query"
    point_key   = f"{which}_point"
    pending_key = f"{which}_pending_query"
    sugg_key    = f"{which}_suggestions"

    # אם יש pending – קובע את הערך לפני יצירת הווידג׳ט (חוקי)
    pending = st.session_state.get(pending_key)
    if pending:
        st.session_state[query_key] = pending
        st.session_state[pending_key] = None

    value = st.session_state.get(query_key, "")
    new_val = st.text_input(title, value=value, key=query_key)

    # אוטוקומפליט דינמי (מתעדכן בכל הקלדה)
    suggestions = photon_autocomplete(new_val, limit=6) if len(new_val) >= 2 else []
    st.session_state[sugg_key] = suggestions

    if suggestions:
        st.markdown('<div class="suggestion-list">', unsafe_allow_html=True)
        for i, s in enumerate(suggestions):
            if st.button(f"📍 {s['label']}", key=f"{which}_sugg_{i}", use_container_width=True):
                _select_point(which, s["label"], s["lat"], s["lon"])
                st.stop()
        st.markdown('</div>', unsafe_allow_html=True)


        pt = st.session_state.get(point_key)
        if pt:
            st.success(f"Selected: {pt['label']}  ({pt['lat']:.4f}, {pt['lon']:.4f})")


# === BEGIN: Topbar overlay (Waze-like) ===
def render_topbar():
    """
    Floating topbar like Waze: Start / Destination + key toggles.
    Uses existing _point_ui() for inputs, so state stays identical.
    """
    st.markdown(
        """
        <div style="
            position: sticky; top: 8px; z-index: 1002;
            background: rgba(15,34,56,.86);
            border: 1px solid rgba(255,255,255,.08);
            box-shadow: 0 10px 30px rgba(0,0,0,.35);
            backdrop-filter: blur(10px);
            border-radius: 18px;
            padding: 10px 12px;
        ">
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([3, 3, 2])
    with c1:
        _point_ui("start", "Start")
    with c2:
        _point_ui("end", "Destination")
    with c3:
        st.session_state["avoid_motorways"] = st.toggle(
            "Avoid motorways",
            value=st.session_state.get("avoid_motorways", False),
            key="avoid_motorways_topbar",
        )

        st.session_state["auto_eta"] = st.toggle(
            "Auto ETA",
            value=st.session_state.get("auto_eta", True),
            key="auto_eta_topbar",
        )



    st.markdown("</div>", unsafe_allow_html=True)
# === END: Topbar overlay (Waze-like) ===


def render_modern_search_bar():
    """Modern floating search bar with Waze-like design"""
    # Get current values
    start_value = st.session_state.get("start_query", "")
    end_value = st.session_state.get("end_query", "")
    
    st.markdown("""
    <div class="floating-search-bar">
        <div class="search-inputs">
    """, unsafe_allow_html=True)
    
    # Start location input
    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        start_new = st.text_input(
            "Start location", 
            value=start_value,
            key="start_query_modern",
            placeholder="Start location"
        )
        if start_new != start_value:
            st.session_state["start_query"] = start_new
            # Trigger autocomplete
            if len(start_new) >= 2:
                suggestions = photon_autocomplete(start_new, limit=5)
                st.session_state["start_suggestions"] = suggestions
    
    with col2:
        st.markdown('<div class="search-divider"></div>', unsafe_allow_html=True)
    
    with col3:
        end_new = st.text_input(
            "Destination", 
            value=end_value,
            key="end_query_modern", 
            placeholder="Destination"
        )
        if end_new != end_value:
            st.session_state["end_query"] = end_new
            # Trigger autocomplete
            if len(end_new) >= 2:
                suggestions = photon_autocomplete(end_new, limit=5)
                st.session_state["end_suggestions"] = suggestions
    
    # Show suggestions for start
    if st.session_state.get("start_suggestions") and len(st.session_state["start_query"]) >= 2:
        st.markdown('<div class="suggestion-list">', unsafe_allow_html=True)
        for i, suggestion in enumerate(st.session_state["start_suggestions"]):
            if st.button(f"📍 {suggestion['label']}", key=f"start_sugg_modern_{i}", use_container_width=True):
                _select_point("start", suggestion["label"], suggestion["lat"], suggestion["lon"])
                st.session_state["start_suggestions"] = []
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Show suggestions for end
    if st.session_state.get("end_suggestions") and len(st.session_state["end_query"]) >= 2:
        st.markdown('<div class="suggestion-list">', unsafe_allow_html=True)
        for i, suggestion in enumerate(st.session_state["end_suggestions"]):
            if st.button(f"📍 {suggestion['label']}", key=f"end_sugg_modern_{i}", use_container_width=True):
                _select_point("end", suggestion["label"], suggestion["lat"], suggestion["lon"])
                st.session_state["end_suggestions"] = []
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("""
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_bottom_sheet(eta_minutes=None, multiplier=None, route_info=None):
    """Modern bottom sheet for trip summary"""
    if not eta_minutes:
        return
    
    eta_display = fmt_minutes(eta_minutes)
    multiplier_text = f"{multiplier:.2f}x" if multiplier else "1.0x"
    
    st.markdown(f"""
    <div class="bottom-sheet">
        <div class="header">
            <div>
                <h3 class="title">Trip Summary</h3>
                <p class="subtitle">Route calculated with traffic conditions</p>
            </div>
        </div>
        <div class="content">
            <div class="trip-info">
                <div class="tags">
                    <span class="tag">Traffic: {multiplier_text}</span>
                    <span class="tag">Route A</span>
                    <span class="tag">Live Updates</span>
                </div>
            </div>
            <div class="eta-display">
                <h1 class="eta-time">{eta_display}</h1>
                <p class="eta-label">Estimated Arrival</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_floating_buttons():
    """Floating action buttons for quick actions"""
    st.markdown("""
    <div class="fabs">
        <div class="fab primary" onclick="startNavigation()">
            <span class="material-icons-outlined">navigation</span>
            <div class="fab-tooltip">Start Navigation</div>
        </div>
        <div class="fab" onclick="toggleMute()">
            <span class="material-icons-outlined">volume_up</span>
            <div class="fab-tooltip">Toggle Voice</div>
        </div>
        <div class="fab" onclick="simulateDrive()">
            <span class="material-icons-outlined">play_arrow</span>
            <div class="fab-tooltip">Simulate Drive</div>
        </div>
        <div class="fab" onclick="showSettings()">
            <span class="material-icons-outlined">settings</span>
            <div class="fab-tooltip">Settings</div>
        </div>
        <div class="fab" onclick="reportTraffic()">
            <span class="material-icons-outlined">report</span>
            <div class="fab-tooltip">Report Traffic</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_route_alternatives(routes):
    """Render A/B/C style route alternatives"""
    if not routes:
        return
    
    st.markdown('<div class="route-chips">', unsafe_allow_html=True)
    
    for i, route in enumerate(routes):
        route_letter = chr(65 + i)  # A, B, C
        route_time = f"{route['minutes']:.0f} min"
        route_distance = f"{route['km']:.1f} km"
        
        st.markdown(f"""
        <div class="route-chip" onclick="selectRoute({i})">
            <strong>Route {route_letter}</strong><br>
            <small>{route_time} • {route_distance}</small>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="🚗 Waze AI Navigation", 
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    logging.basicConfig(level=logging.INFO)

    _ensure_state()
    _load_query_params()

    # Modern floating search bar
    render_modern_search_bar()
    
    # Add some top padding for the floating search bar
    st.markdown('<div style="height: 100px;"></div>', unsafe_allow_html=True)



    # Modern layout with full-width map
    st.markdown("""
    <div style="position: relative; height: calc(100vh - 120px);">
    """, unsafe_allow_html=True)
    
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

    # Weather and context controls in a floating panel
    with st.container():
        st.markdown("""
        <div style="position: absolute; top: 20px; right: 20px; z-index: 1000; 
                    background: rgba(15, 22, 41, 0.95); backdrop-filter: blur(20px);
                    border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px;
                    padding: 16px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);">
        """, unsafe_allow_html=True)
        
        # Weather controls
        if st.session_state.get("weather_pending"):
            _default_weather = st.session_state["weather_pending"]
            st.session_state["weather_pending"] = None
        else:
            _default_weather = "clear"

        auto_on = st.toggle("🌤️ Auto Weather", value=(st.session_state.get("weather_mode") == "auto"))
        st.session_state["weather_mode"] = "auto" if auto_on else "manual"

        weather = st.selectbox(
            "Weather",
            ["clear", "cloudy", "rain", "storm", "snow"],
            index=["clear","cloudy","rain","storm","snow"].index(_default_weather) if _default_weather in ["clear","cloudy","rain","storm","snow"] else 0,
            key="weather_select",
        )
        
        if st.session_state.get("weather_mode") == "auto" and st.session_state.get("last_weather"):
            api_cat = st.session_state["last_weather"].get("category")
            if api_cat and api_cat != weather:
                weather = api_cat

        # Context controls in a compact layout
        col1, col2 = st.columns(2)
        with col1:
            time_of_day = st.selectbox("🕐 Time", ["night", "morning_peak", "midday", "evening_peak"], index=2)
            day_type = st.selectbox("📅 Day", ["weekday", "weekend", "holiday"], index=0)
        with col2:
            road_problem = st.selectbox("🚧 Road", ["none", "accident", "construction", "closure"], index=0)
            police_activity = st.selectbox("👮 Police", ["low", "medium", "high"], index=0)
        
        driving_history = st.selectbox("🚗 Driving", ["calm", "normal", "aggressive"], index=1)
        
        st.session_state["avoid_motorways"] = st.toggle(
            "🛣️ Avoid Motorways",
            value=st.session_state.get("avoid_motorways", False),
            key="avoid_motorways_modern",
        )
        
        st.markdown("</div>", unsafe_allow_html=True)

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
            # Use the first route by default, but allow selection
            route_idx = st.session_state.get("selected_route", 0)
            geometry = routes[route_idx]["geometry"]
        else:
            # fallback: single route
            try:
                _, geometry = osrm_route(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
            except Exception:
                geometry = None

    # Render the map
    ret = render_map(sp, ep, geometry)
    
    # Route alternatives display
    if routes and len(routes) > 1:
        render_route_alternatives(routes)
    
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
        osrm_minutes = base["osrm_minutes"]
        haversine_minutes = base["haversine_minutes"]
        normalized_haversine = base["normalized_haversine"]
        normalization_factor = base["normalization_factor"]
        
        base_used = osrm_minutes or normalized_haversine
        
        # Traffic multiplier calculation
        details = predict_travel_with_details(
            weather=weather,
            time_of_day=time_of_day,
            day_type=day_type,
            road_problem=road_problem,
            police_activity=police_activity,
            driving_history=driving_history,
        )
        multiplier = details["multiplier"]
        
        # Final ETA
        final_minutes = (base_used or 0.0) * multiplier
        
        # Add calibration sample
        add_calib_sample(haversine_minutes, osrm_minutes)
        
        # Store in session state for bottom sheet
        st.session_state["last_eta_min"] = final_minutes
        st.session_state["last_multiplier"] = multiplier

    # Close the map container
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Render floating action buttons
    render_floating_buttons()
    
    # Render bottom sheet with ETA if available
    if final_minutes:
        render_bottom_sheet(final_minutes, multiplier, routes[route_idx] if routes else None)
    
    # Error handling and notifications
    if not sp and not ep:
        st.markdown("""
        <div class="alert warning" style="position: fixed; top: 120px; left: 20px; right: 20px; z-index: 1000;">
            <strong>📍 Select Locations</strong><br>
            Choose start and destination points to begin navigation
        </div>
        """, unsafe_allow_html=True)
    elif not sp:
        st.markdown("""
        <div class="alert warning" style="position: fixed; top: 120px; left: 20px; right: 20px; z-index: 1000;">
            <strong>📍 Select Start Point</strong><br>
            Choose your starting location to calculate the route
        </div>
        """, unsafe_allow_html=True)
    elif not ep:
        st.markdown("""
        <div class="alert warning" style="position: fixed; top: 120px; left: 20px; right: 20px; z-index: 1000;">
            <strong>📍 Select Destination</strong><br>
            Choose your destination to calculate the route
        </div>
        """, unsafe_allow_html=True)
    
    # Add JavaScript for interactivity and animations
    st.markdown("""
    <script>
    // Modern Waze-like interactions
    function calculateRoute() {
        console.log('Calculating route...');
        // Add loading animation
        const button = document.querySelector('.modern-button');
        if (button) {
            button.innerHTML = '<div class="loading-spinner"></div>';
            setTimeout(() => {
                button.innerHTML = '<span class="material-icons-outlined">navigation</span>';
            }, 2000);
        }
    }
    
    function selectRoute(index) {
        console.log('Selected route:', index);
        // Update route selection in session state
        // This would need to be integrated with Streamlit's state management
    }
    
    function startNavigation() {
        console.log('Starting navigation...');
        // Show navigation mode
        showNotification('Navigation started!', 'success');
    }
    
    function toggleMute() {
        console.log('Toggling voice...');
        const icon = document.querySelector('.fab .material-icons-outlined');
        if (icon) {
            icon.textContent = icon.textContent === 'volume_up' ? 'volume_off' : 'volume_up';
        }
        showNotification('Voice guidance toggled', 'info');
    }
    
    function showSettings() {
        console.log('Showing settings...');
        showNotification('Settings panel opened', 'info');
    }
    
    function reportTraffic() {
        console.log('Reporting traffic...');
        showNotification('Traffic report submitted', 'success');
    }
    
    function simulateDrive() {
        console.log('Starting drive simulation...');
        showNotification('Drive simulation started', 'info');
        
        // Add a simple drive simulation
        const mapContainer = document.querySelector('iframe[title="st.iframe"]');
        if (mapContainer) {
            // Create a moving marker simulation
            const simulationMarker = document.createElement('div');
            simulationMarker.style.cssText = `
                position: absolute; width: 20px; height: 20px; background: #1daeff;
                border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(29, 174, 255, 0.5);
                z-index: 1000; transition: all 0.5s ease-out; pointer-events: none;
            `;
            simulationMarker.innerHTML = '<div style="width: 100%; height: 100%; background: #1daeff; border-radius: 50%; animation: pulse 1s infinite;"></div>';
            document.body.appendChild(simulationMarker);
            
            // Animate the marker
            let position = 0;
            const animate = () => {
                position += 2;
                simulationMarker.style.left = position + 'px';
                simulationMarker.style.top = (200 + Math.sin(position * 0.01) * 50) + 'px';
                
                if (position < window.innerWidth - 50) {
                    requestAnimationFrame(animate);
                } else {
                    simulationMarker.remove();
                    showNotification('Drive simulation completed!', 'success');
                }
            };
            animate();
        }
    }
    
    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert ${type}`;
        notification.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 10000;
            padding: 12px 16px; border-radius: 8px; color: white;
            background: ${type === 'success' ? '#00d4aa' : type === 'warning' ? '#ffb800' : '#1daeff'};
            box-shadow: 0 4px 16px rgba(0,0,0,0.3); animation: slideIn 0.3s ease-out;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
    
    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
    `;
    document.head.appendChild(style);
    
    // Initialize interactions
    document.addEventListener('DOMContentLoaded', function() {
        // Add button animations
        const buttons = document.querySelectorAll('.modern-button, .fab');
        buttons.forEach(button => {
            button.addEventListener('click', function() {
                this.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    this.style.transform = '';
                }, 150);
            });
        });
        
        // Add route chip selection
        const routeChips = document.querySelectorAll('.route-chip');
        routeChips.forEach((chip, index) => {
            chip.addEventListener('click', function() {
                routeChips.forEach(c => c.classList.remove('selected'));
                this.classList.add('selected');
                selectRoute(index);
            });
        });
        
        // Add search input focus effects
        const searchInputs = document.querySelectorAll('input[type="text"]');
        searchInputs.forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.style.transform = 'scale(1.02)';
            });
            input.addEventListener('blur', function() {
                this.parentElement.style.transform = 'scale(1)';
            });
        });
        
        // Add smooth scrolling for mobile
        if (window.innerWidth <= 768) {
            document.body.style.overflow = 'hidden';
        }
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth <= 768) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'auto';
        }
    });
    </script>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
