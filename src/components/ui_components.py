"""
UI Components for Waze-like Navigation Interface
===============================================
Reusable UI components that render HTML templates and handle interactions.
"""

import streamlit as st
from pathlib import Path
from typing import Optional, List, Dict, Any
import jinja2

# Template loader
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
template_loader = jinja2.FileSystemLoader(searchpath=str(TEMPLATE_DIR))
template_env = jinja2.Environment(loader=template_loader)

def render_bottom_sheet(eta_minutes: Optional[float] = None, 
                       multiplier: Optional[float] = None, 
                       route_info: Optional[Dict] = None) -> str:
    """Render the bottom sheet with trip summary"""
    if not eta_minutes:
        return ""
    
    # Format ETA display
    if eta_minutes:
        h = int(eta_minutes // 60)
        mm = int(round(eta_minutes % 60))
        eta_display = f"{h}h {mm}m" if h else f"{mm}m"
    else:
        eta_display = "—"
    
    template = template_env.get_template("components/bottom_sheet.html")
    return template.render(
        eta_minutes=eta_minutes,
        eta_display=eta_display,
        multiplier=multiplier or 1.0,
        route_info=route_info
    )

def render_floating_buttons():
    """Render the floating action buttons with Streamlit functionality"""
    # Initialize session state for button states
    if "sound_enabled" not in st.session_state:
        st.session_state["sound_enabled"] = True
    if "dark_mode" not in st.session_state:
        st.session_state["dark_mode"] = True
    if "show_settings" not in st.session_state:
        st.session_state["show_settings"] = False
    
    # Create floating buttons container
    with st.container():
        # Position the buttons absolutely
        st.markdown("""
        <style>
        .floating-buttons {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .fab-button {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 50%;
            width: 56px;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
            color: #ffffff;
            font-size: 24px;
        }
        
        .fab-button:hover {
            background: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.4);
            transform: scale(1.1);
        }
        
        .fab-button.primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        .fab-button.primary:hover {
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Create buttons in columns for layout
        col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
        
        with col1:
            if st.button("🧭", key="nav_btn", help="Start Navigation"):
                st.info("Navigation started!")
        
        with col2:
            # Sound toggle button
            sound_icon = "🔊" if st.session_state["sound_enabled"] else "🔇"
            if st.button(sound_icon, key="sound_btn", help="Toggle Sound"):
                st.session_state["sound_enabled"] = not st.session_state["sound_enabled"]
                st.rerun()
        
        with col3:
            if st.button("▶️", key="drive_btn", help="Simulate Drive"):
                st.info("Drive simulation started!")
        
        with col4:
            if st.button("⚙️", key="settings_btn", help="Settings"):
                st.session_state["show_settings"] = not st.session_state["show_settings"]
                st.rerun()
        
        with col5:
            if st.button("🚨", key="report_btn", help="Report Traffic"):
                st.info("Traffic report submitted!")
    
    # Settings panel
    if st.session_state["show_settings"]:
        with st.sidebar:
            st.markdown("### ⚙️ Settings")
            
            # Dark/Light mode toggle
            dark_mode = st.toggle(
                "🌙 Dark Mode", 
                value=st.session_state["dark_mode"],
                key="dark_mode_toggle"
            )
            if dark_mode != st.session_state["dark_mode"]:
                st.session_state["dark_mode"] = dark_mode
                st.rerun()
            
            # Reset page button
            if st.button("🔄 Reset Page", key="reset_btn"):
                # Clear all session state
                for key in list(st.session_state.keys()):
                    if key not in ["sound_enabled", "dark_mode", "show_settings"]:
                        del st.session_state[key]
                st.rerun()
            
            st.markdown("---")
            st.markdown("*Settings panel will close automatically when you navigate away.*")

def render_route_chips(routes: List[Dict]) -> str:
    """Render route alternative chips"""
    if not routes:
        return ""
    
    # Generate route letters (A, B, C, etc.)
    route_letters = [chr(65 + i) for i in range(len(routes))]
    
    template = template_env.get_template("components/route_chips.html")
    return template.render(routes=routes, route_letters=route_letters)

def render_route_chips_streamlit(routes: List[Dict]):
    """Render route alternative chips using Streamlit buttons for better integration"""
    if not routes:
        return
    
    # Generate route letters (A, B, C, etc.)
    route_letters = [chr(65 + i) for i in range(len(routes))]
    
    # Create columns for route chips
    cols = st.columns(len(routes))
    
    for i, (col, route) in enumerate(zip(cols, routes)):
        with col:
            # Format route info
            minutes = int(route.get('minutes', 0))
            km = route.get('km', 0)
            route_letter = route_letters[i]
            
            # Create button with route info
            button_text = f"Route {route_letter}\n{minutes} min • {km:.1f} km"
            
            if st.button(
                button_text,
                key=f"route_chip_{i}",
                use_container_width=True,
                help=f"Select Route {route_letter}"
            ):
                # Update selected route
                st.session_state["selected_route"] = i
                st.rerun()
    
    # Add custom CSS for button styling
    st.markdown("""
    <style>
    [data-testid="stButton"] > button {
        background: rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 12px !important;
        color: #ffffff !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        padding: 12px 16px !important;
        transition: all 0.3s ease !important;
        min-height: 60px !important;
        white-space: pre-line !important;
    }
    [data-testid="stButton"] > button:hover {
        background: rgba(255, 255, 255, 0.2) !important;
        border: 1px solid rgba(255, 255, 255, 0.4) !important;
        transform: translateY(-2px) !important;
    }
    </style>
    """, unsafe_allow_html=True)

def render_error_messages(error_type: Optional[str] = None) -> str:
    """Render contextual error messages"""
    if not error_type:
        return ""
    
    template = template_env.get_template("components/error_messages.html")
    return template.render(error_type=error_type)

def render_weather_controls():
    """Render the floating weather and context controls"""
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
    
    return {
        "weather": weather,
        "time_of_day": time_of_day,
        "day_type": day_type,
        "road_problem": road_problem,
        "police_activity": police_activity,
        "driving_history": driving_history
    }
