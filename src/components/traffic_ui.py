"""
Traffic UI Components
====================
UI components for real-time traffic integration.
"""

import streamlit as st
from typing import Dict, Any, Optional
from datetime import datetime
import json


def render_traffic_toggle() -> bool:
    """
    Render the live traffic toggle.
    
    Returns:
        True if live traffic is enabled
    """
    st.markdown("### 🚦 Live Traffic (Beta)")
    
    # Initialize session state
    if "live_traffic_enabled" not in st.session_state:
        st.session_state.live_traffic_enabled = False
    
    # Traffic toggle
    live_traffic = st.toggle(
        "Enable Live Traffic Data",
        value=st.session_state.live_traffic_enabled,
        help="Enable real-time traffic data from TomTom/HERE APIs"
    )
    
    # Update session state
    st.session_state.live_traffic_enabled = live_traffic
    
    return live_traffic


def render_traffic_status(traffic_data: Optional[Dict[str, Any]]) -> None:
    """
    Render traffic status information.
    
    Args:
        traffic_data: Traffic data from provider
    """
    if not traffic_data:
        return
    
    st.markdown("### 📊 Traffic Status")
    
    # Create columns for traffic metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Jam factor indicator
        jam_factor = traffic_data.get('jam_factor', 0.0)
        jam_percent = jam_factor * 100
        
        if jam_percent < 20:
            color = "🟢"
            status = "Clear"
        elif jam_percent < 50:
            color = "🟡"
            status = "Moderate"
        else:
            color = "🔴"
            status = "Heavy"
        
        st.metric(
            label=f"{color} Congestion",
            value=f"{jam_percent:.1f}%",
            delta=status
        )
    
    with col2:
        # Average speed
        avg_speed = traffic_data.get('average_speed_kmh', 60.0)
        st.metric(
            label="🚗 Avg Speed",
            value=f"{avg_speed:.0f} km/h"
        )
    
    with col3:
        # Incident count
        incident_count = traffic_data.get('incident_count', 0)
        st.metric(
            label="⚠️ Incidents",
            value=incident_count
        )
    
    # Provider info
    provider = traffic_data.get('provider', 'Unknown')
    last_updated = traffic_data.get('last_updated')
    
    if last_updated:
        try:
            updated_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            time_ago = datetime.now() - updated_time.replace(tzinfo=None)
            minutes_ago = int(time_ago.total_seconds() / 60)
            
            st.caption(f"📡 Data from {provider} • Updated {minutes_ago} min ago")
        except:
            st.caption(f"📡 Data from {provider}")


def render_traffic_incidents(traffic_data: Optional[Dict[str, Any]]) -> None:
    """
    Render traffic incidents list.
    
    Args:
        traffic_data: Traffic data from provider
    """
    if not traffic_data or not traffic_data.get('incidents'):
        return
    
    incidents = traffic_data.get('incidents', [])
    
    if incidents:
        st.markdown("### ⚠️ Active Incidents")
        
        for i, incident in enumerate(incidents):
            incident_type = incident.get('type', 'unknown')
            severity = incident.get('severity', 'low')
            description = incident.get('description', 'Unknown incident')
            
            # Color coding based on severity
            if severity == 'high':
                color = "🔴"
            elif severity == 'medium':
                color = "🟡"
            else:
                color = "🟢"
            
            # Type icon
            type_icons = {
                'accident': '🚗💥',
                'construction': '🚧',
                'closure': '🚫',
                'weather': '🌧️',
                'congestion': '🚦'
            }
            type_icon = type_icons.get(incident_type, '⚠️')
            
            st.markdown(f"{color} **{type_icon} {description}** ({severity.title()})")


def render_traffic_legend() -> None:
    """Render traffic color legend."""
    st.markdown("### 🎨 Traffic Legend")
    
    legend_html = """
    <div style="display: flex; flex-direction: column; gap: 8px; font-size: 14px;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 20px; height: 20px; background-color: #4CAF50; border-radius: 50%;"></div>
            <span>🟢 Clear (0-20%)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 20px; height: 20px; background-color: #FFC107; border-radius: 50%;"></div>
            <span>🟡 Moderate (20-50%)</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <div style="width: 20px; height: 20px; background-color: #F44336; border-radius: 50%;"></div>
            <span>🔴 Heavy (50%+)</span>
        </div>
    </div>
    """
    
    st.markdown(legend_html, unsafe_allow_html=True)


def render_traffic_provider_status(provider_status: Dict[str, Any]) -> None:
    """
    Render traffic provider status.
    
    Args:
        provider_status: Status of traffic providers
    """
    st.markdown("### 🔧 Traffic Provider Status")
    
    # Overall status
    enabled = provider_status.get('enabled', False)
    active_provider = provider_status.get('active_provider', 'None')
    
    status_color = "🟢" if enabled else "🔴"
    st.markdown(f"{status_color} **Live Traffic:** {'Enabled' if enabled else 'Disabled'}")
    st.markdown(f"📡 **Active Provider:** {active_provider}")
    
    # Provider details
    providers = provider_status.get('providers', {})
    
    for name, details in providers.items():
        available = details.get('available', False)
        cache_stats = details.get('cache_stats', {})
        
        status_icon = "🟢" if available else "🔴"
        st.markdown(f"{status_icon} **{name.title()}:** {'Available' if available else 'Unavailable'}")
        
        if cache_stats:
            cached_routes = cache_stats.get('cached_routes', 0)
            st.caption(f"   📦 {cached_routes} cached routes")


def render_traffic_settings() -> Dict[str, Any]:
    """
    Render traffic settings panel.
    
    Returns:
        Dictionary of traffic settings
    """
    st.markdown("### ⚙️ Traffic Settings")
    
    # Initialize session state
    if "traffic_settings" not in st.session_state:
        st.session_state.traffic_settings = {
            'auto_refresh': True,
            'refresh_interval': 60,
            'cache_duration': 300,
            'fallback_to_mock': True
        }
    
    settings = st.session_state.traffic_settings
    
    # Auto-refresh toggle
    settings['auto_refresh'] = st.checkbox(
        "Auto-refresh traffic data",
        value=settings['auto_refresh'],
        help="Automatically refresh traffic data at regular intervals"
    )
    
    # Refresh interval
    if settings['auto_refresh']:
        settings['refresh_interval'] = st.slider(
            "Refresh interval (seconds)",
            min_value=30,
            max_value=300,
            value=settings['refresh_interval'],
            step=30,
            help="How often to refresh traffic data"
        )
    
    # Cache duration
    settings['cache_duration'] = st.slider(
        "Cache duration (seconds)",
        min_value=60,
        max_value=600,
        value=settings['cache_duration'],
        step=60,
        help="How long to cache traffic data"
    )
    
    # Fallback to mock
    settings['fallback_to_mock'] = st.checkbox(
        "Fallback to mock data",
        value=settings['fallback_to_mock'],
        help="Use mock data when real providers are unavailable"
    )
    
    # Update session state
    st.session_state.traffic_settings = settings
    
    return settings


def render_traffic_debug_info(traffic_data: Optional[Dict[str, Any]]) -> None:
    """
    Render debug information for traffic data (development only).
    
    Args:
        traffic_data: Traffic data from provider
    """
    if not traffic_data:
        return
    
    with st.expander("🔍 Traffic Debug Info"):
        st.json(traffic_data)
