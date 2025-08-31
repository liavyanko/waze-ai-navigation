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


def main():
    st.set_page_config(page_title="🚗 Waze AI Prototype", layout="wide")
    logging.basicConfig(level=logging.INFO)

    _ensure_state()
    # טען נקודות מה-URL אם יש
    _load_query_params()

    st.title("🚗 Waze AI Prototype")
    st.write("Prototype that simulates Waze-like logic with Bayesian-inspired multiplier + OSRM base time.")

    # === Top overlay (Waze-like) ===
    render_topbar()



    # --- Inputs (left) ---
    left, right = st.columns([1, 1])

    with left:

        # בחירת נקודות בלחיצה על המפה
        st.session_state["active_pick"] = st.radio("Set by map click", ["off", "start", "end"], horizontal=True, index=["off", "start", "end"].index(st.session_state.get("active_pick", "off")))

        # --- Auto weather update BEFORE context controls ---
        sp = st.session_state.get("start_point")
        ep = st.session_state.get("end_point")

        # נקודת מיקוד למזג אוויר: אם יש 2 נק', midpoint; אם אחת – היא; אם אין – אל תשלוף
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
            # הכנה לערך ברירת מחדל ל-selectbox – מגדירים לפני יצירת הווידג'ט
            if wx.get("category"):
                st.session_state["weather_pending"] = wx["category"]


        st.subheader("Context")

        # ▼ Weather: auto/manual safe pattern
        # אם יש pending – קובע את הערך לפני יצירת הווידג׳ט
        if st.session_state.get("weather_pending"):
            _default_weather = st.session_state["weather_pending"]
            st.session_state["weather_pending"] = None
        else:
            _default_weather = "clear"

        # מצב אוטומטי/ידני
        mode_col1, mode_col2 = st.columns([1, 2])
        with mode_col1:
            auto_on = st.toggle("Auto weather", value=(st.session_state.get("weather_mode") == "auto"))
            st.session_state["weather_mode"] = "auto" if auto_on else "manual"

        with mode_col2:
            # ה-selectbox תמיד קיים; במצב auto הוא מתעדכן לפי API, ובכל מקרה אפשר לדרוס ידנית
            weather = st.selectbox(
                "Weather",
                ["clear", "cloudy", "rain", "storm", "snow"],
                index=["clear","cloudy","rain","storm","snow"].index(_default_weather) if _default_weather in ["clear","cloudy","rain","storm","snow"] else 0,
                key="weather_select",
            )
            # אם ב-auto והגיע ערך מה-API – דואגים שיהיה תואם גם למודל
            if st.session_state.get("weather_mode") == "auto" and st.session_state.get("last_weather"):
                api_cat = st.session_state["last_weather"].get("category")
                if api_cat and api_cat != weather:
                    # לא נוגעים ב-widget מיד אחרי שנוצר; פשוט נעדכן את המשתנה המקומי לחישוב
                    weather = api_cat

            # תצוגת מקור הנתון
            wx_info = st.session_state.get("last_weather") or {}
            src = wx_info.get("source", "—")
            code = wx_info.get("code", "—")
            temp = wx_info.get("temp_c")
            wind = wx_info.get("windspeed")
            meta = []
            if temp is not None: meta.append(f"{temp}°C")
            if wind is not None: meta.append(f"wind {wind} km/h")
            meta_txt = " • ".join(meta) if meta else ""
            st.caption(f"Weather source: {src} (WMO {code}) {meta_txt}")

        time_of_day = st.selectbox("Time of day", ["night", "morning_peak", "midday", "evening_peak"], index=2)
        day_type = st.selectbox("Day type", ["weekday", "weekend", "holiday"], index=0)
        road_problem = st.selectbox("Road problem", ["none", "accident", "construction", "closure"], index=0)
        police_activity = st.selectbox("Police activity", ["low", "medium", "high"], index=0)
        driving_history = st.selectbox("Driving history", ["calm", "normal", "aggressive"], index=1)

        # אפשרות להימנע מכבישים מהירים
        st.session_state["avoid_motorways"] = st.toggle(
            "Avoid motorways",
            value=st.session_state.get("avoid_motorways", False),
            key="avoid_motorways_top",   # ← הוסף key ייחודי
        )
        run = st.button("Calculate ETA", use_container_width=True)

        auto_trigger = (
            st.session_state.get("auto_eta", True)
            and st.session_state.get("start_point") is not None
            and st.session_state.get("end_point") is not None
        )

        if run or auto_trigger:
            # >>> כאן נשאר בדיוק אותו קוד חישוב ETA שהיה בתוך if run
            # לדוגמה:
            # base = compute_base_times(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
            # details = predict_travel_with_details(...)
            # final_minutes = (base_used or 0.0) * details["multiplier"]
            # st.session_state["last_eta_min"] = final_minutes
            # ...
            pass


        # Favorites & History
        with st.expander("⭐ Favorites & History"):
            col1, col2 = st.columns(2)
            with col1:
                fav_name = st.text_input("Save current START as favorite (name)")
                if fav_name and st.button("Save Start ★"):
                    sp = st.session_state.get("start_point")
                    if sp:
                        st.session_state["favorites"].append({"name": fav_name, "lat": sp["lat"], "lon": sp["lon"]})
                        st.success(f"Saved: {fav_name}")

            with col2:
                fav_name2 = st.text_input("Save current END as favorite (name)")
                if fav_name2 and st.button("Save End ★"):
                    ep = st.session_state.get("end_point")
                    if ep:
                        st.session_state["favorites"].append({"name": fav_name2, "lat": ep["lat"], "lon": ep["lon"]})
                        st.success(f"Saved: {fav_name2}")

            if st.session_state["favorites"]:
                pick = st.selectbox("Go to favorite", options=[f['name'] for f in st.session_state["favorites"]])
                cols = st.columns(2)
                with cols[0]:
                    if st.button("Set as START"):
                        f = next(x for x in st.session_state["favorites"] if x["name"] == pick)
                        st.session_state["start_point"] = {"label": pick, "lat": f["lat"], "lon": f["lon"]}; _save_query_params(); _safe_rerun()
                with cols[1]:
                    if st.button("Set as END"):
                        f = next(x for x in st.session_state["favorites"] if x["name"] == pick)
                        st.session_state["end_point"] = {"label": pick, "lat": f["lat"], "lon": f["lon"]}; _save_query_params(); _safe_rerun()

    with right:
        st.subheader("Map")
        sp = st.session_state.get("start_point")
        ep = st.session_state.get("end_point")

        # מסלולים חלופיים (אם יש שתי נקודות)
        routes = []
        route_idx = 0
        geometry = None
        if sp and ep:
            try:
                routes = osrm_routes_cached(sp["lat"], sp["lon"], ep["lat"], ep["lon"], max_routes=3, avoid_motorways=st.session_state.get("avoid_motorways", False))
            except Exception:
                routes = []

            if routes:
                labels = [f"Route {chr(65+i)} — {r['km']:.1f} km, {r['minutes']:.0f} min" for i, r in enumerate(routes)]
                route_idx = st.radio("Choose route", options=list(range(len(routes))), format_func=lambda i: labels[i], horizontal=True)
                geometry = routes[route_idx]["geometry"]
            else:
                # fallback: מסלול בודד
                try:
                    _, geometry = osrm_route(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
                except Exception:
                    geometry = None

        ret = render_map(sp, ep, geometry)  # מציג מפה גם בלי נקודות / עם נקודה אחת

                # הצגת מזג אוויר חי מתחת למפה
        wx = st.session_state.get("last_weather") or {}
        if wx.get("category"):
                st.markdown(
                    f"**Live weather:** `{wx['category']}` "
                    f"(WMO {wx.get('code','—')}) • {wx.get('temp_c','—')}°C • wind {wx.get('windspeed','—')} km/h"
                )


        # בחירת נקודות בלחיצה על המפה
        if ret and ret.get("last_clicked"):
            lat = ret["last_clicked"]["lat"]; lon = ret["last_clicked"]["lng"]
            mode = st.session_state.get("active_pick", "off")
            if mode == "start":
                _select_point("start", f"LatLng({lat:.4f},{lon:.4f})", lat, lon)
            elif mode == "end":
                _select_point("end", f"LatLng({lat:.4f},{lon:.4f})", lat, lon)

    if run:
        if not (sp and ep):
            st.error("Please select both Start and Destination.")
            return

        # --- Base time (OSRM + Haversine fallback) ---
        st.subheader("Base Time Comparison")
        base = compute_base_times(sp["lat"], sp["lon"], ep["lat"], ep["lon"])
        osrm_minutes = base["osrm_minutes"]
        haversine_minutes = base["haversine_minutes"]
        normalized_haversine = base["normalized_haversine"]
        normalization_factor = base["normalization_factor"]

        if osrm_minutes:
            st.info(f"OSRM result: {fmt_minutes(osrm_minutes)}")
        if haversine_minutes:
            st.info(f"Haversine (speed={AVERAGE_SPEED_KMH} km/h): {fmt_minutes(haversine_minutes)}")
        if normalized_haversine:
            st.success(f"Haversine normalized: {fmt_minutes(normalized_haversine)} (factor={normalization_factor:.2f})")

        # הוסף דגימת קליברציה לשיפור פקטור עתידי
        add_calib_sample(haversine_minutes, osrm_minutes)

        base_used = osrm_minutes or normalized_haversine

        # --- Bayesian/Heuristic multiplier ---
        st.subheader("Traffic Multiplier (Bayesian-inspired)")
        details = predict_travel_with_details(
            weather=weather,
            time_of_day=time_of_day,
            day_type=day_type,
            road_problem=road_problem,
            police_activity=police_activity,
            driving_history=driving_history,
        )
        multiplier = details["multiplier"]
        rows = details.get("rows", [])
        marginals = details.get("marginals", {})

        if rows:
            st.write("Contributions:")
            st.dataframe(rows, use_container_width=True)

        # Final ETA
        final_minutes = (base_used or 0.0) * multiplier
        st.subheader("Final ETA")
        st.metric("Multiplier", multiplier)
        if base_used:
            st.success(f"ETA: {fmt_minutes(final_minutes)}  (Base={fmt_minutes(base_used)})")
        else:
            st.warning("No base time available; ETA cannot be computed.")

        # Internal reasoning
        if marginals:
            st.subheader("Most likely internal states")
            for var, info in marginals.items():
                st.write(f"- **{var}**: {info['top']}  |  dist={info['dist']}")

        # היסטוריה
        try:
            st.session_state["history"].append({
                "start": st.session_state.get("start_point"),
                "end": st.session_state.get("end_point"),
                "base": base_used,
                "multiplier": multiplier,
                "eta": final_minutes,
            })
        except Exception:
            pass


if __name__ == "__main__":
    main()
