"""
TomTom Traffic Provider
======================
Real-time traffic data provider using TomTom Traffic API.
"""

import requests
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from .traffic_provider import TrafficProvider, TrafficData, TrafficFlow, TrafficIncident

logger = logging.getLogger(__name__)


class TomTomTrafficProvider(TrafficProvider):
    """
    TomTom Traffic API provider for real-time traffic data.
    
    Documentation: https://developer.tomtom.com/traffic-api
    """
    
    def __init__(self, api_key: str, cache_duration: int = 300):
        """
        Initialize TomTom provider.
        
        Args:
            api_key: TomTom API key
            cache_duration: Cache duration in seconds
        """
        super().__init__(api_key, cache_duration)
        self.base_url = "https://api.tomtom.com/traffic/services/4"
        self.version = "4"
        
    def is_available(self) -> bool:
        """Check if TomTom provider is available."""
        return bool(self.api_key)
    
    def get_traffic_data(
        self, 
        route_coordinates: List[Tuple[float, float]], 
        route_id: str
    ) -> TrafficData:
        """
        Get traffic data from TomTom API.
        
        Args:
            route_coordinates: List of (lat, lon) coordinates
            route_id: Unique route identifier
            
        Returns:
            TrafficData object
        """
        # Check cache first
        cached_data = self._get_cached_data(route_id)
        if cached_data:
            return cached_data
        
        try:
            # Get flow data
            flows = self._get_flow_data(route_coordinates)
            
            # Get incident data
            incidents = self._get_incident_data(route_coordinates)
            
            # Calculate overall metrics
            overall_jam_factor = self._calculate_overall_jam_factor(flows)
            average_speed = self._calculate_average_speed(flows)
            incident_count = len(incidents)
            
            # Create traffic data
            traffic_data = TrafficData(
                route_id=route_id,
                flows=flows,
                incidents=incidents,
                overall_jam_factor=overall_jam_factor,
                average_speed_kmh=average_speed,
                incident_count=incident_count,
                last_updated=datetime.now(),
                provider="TomTom",
                cache_until=datetime.now() + timedelta(seconds=self.cache_duration)
            )
            
            # Update cache
            self._update_cache(route_id, traffic_data)
            
            return traffic_data
            
        except Exception as e:
            logger.error(f"Error fetching TomTom traffic data: {e}")
            # Return empty traffic data on error
            return self._create_empty_traffic_data(route_id)
    
    def _get_flow_data(self, coordinates: List[Tuple[float, float]]) -> List[TrafficFlow]:
        """Get traffic flow data from TomTom."""
        try:
            # Create bounding box from coordinates
            lats = [coord[0] for coord in coordinates]
            lons = [coord[1] for coord in coordinates]
            
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
            
            # Build URL
            url = f"{self.base_url}/flowSegmentData/relative/{self.version}/json"
            params = {
                'key': self.api_key,
                'unit': 'KMPH',
                'style': 's3',
                'bbox': bbox,
                'zoom': '10'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            flows = []
            
            if 'flowSegmentData' in data:
                for segment in data['flowSegmentData'].get('flowSegmentData', []):
                    flow = TrafficFlow(
                        segment_id=segment.get('frc', 'unknown'),
                        speed_kmh=segment.get('currentSpeed', 0),
                        free_flow_speed_kmh=segment.get('freeFlowSpeed', 0),
                        jam_factor=segment.get('jamFactor', 0) / 100.0,  # Convert to 0-1 scale
                        confidence=segment.get('confidence', 0) / 100.0,
                        timestamp=datetime.now()
                    )
                    flows.append(flow)
            
            return flows
            
        except Exception as e:
            logger.error(f"Error fetching TomTom flow data: {e}")
            return []
    
    def _get_incident_data(self, coordinates: List[Tuple[float, float]]) -> List[TrafficIncident]:
        """Get traffic incident data from TomTom."""
        try:
            # Create bounding box from coordinates
            lats = [coord[0] for coord in coordinates]
            lons = [coord[1] for coord in coordinates]
            
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
            
            # Build URL
            url = f"{self.base_url}/incidentDetails/{self.version}/json"
            params = {
                'key': self.api_key,
                'bbox': bbox,
                'language': 'en-US',
                'style': 's3'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            incidents = []
            
            if 'tm' in data and 'poi' in data['tm']:
                for poi in data['tm']['poi']:
                    incident = TrafficIncident(
                        incident_id=poi.get('id', 'unknown'),
                        incident_type=self._map_incident_type(poi.get('ic', 0)),
                        severity=self._map_severity(poi.get('ty', 0)),
                        description=poi.get('d', 'Unknown incident'),
                        location=(poi.get('p', {}).get('y', 0), poi.get('p', {}).get('x', 0)),
                        affected_road=poi.get('r', 'Unknown road'),
                        start_time=datetime.now(),
                        end_time=None,
                        confidence=0.8
                    )
                    incidents.append(incident)
            
            return incidents
            
        except Exception as e:
            logger.error(f"Error fetching TomTom incident data: {e}")
            return []
    
    def _map_incident_type(self, ic: int) -> str:
        """Map TomTom incident code to incident type."""
        incident_types = {
            0: 'unknown',
            1: 'accident',
            2: 'congestion',
            3: 'disabled_vehicle',
            4: 'mass_transit',
            5: 'miscellaneous',
            6: 'other_news',
            7: 'planned_event',
            8: 'road_hazard',
            9: 'construction',
            10: 'alert',
            11: 'weather'
        }
        return incident_types.get(ic, 'unknown')
    
    def _map_severity(self, ty: int) -> str:
        """Map TomTom severity code to severity level."""
        severity_levels = {
            0: 'low',
            1: 'low',
            2: 'medium',
            3: 'high',
            4: 'high'
        }
        return severity_levels.get(ty, 'low')
    
    def _calculate_overall_jam_factor(self, flows: List[TrafficFlow]) -> float:
        """Calculate overall jam factor from flow data."""
        if not flows:
            return 0.0
        
        total_jam = sum(flow.jam_factor * flow.confidence for flow in flows)
        total_confidence = sum(flow.confidence for flow in flows)
        
        return total_jam / total_confidence if total_confidence > 0 else 0.0
    
    def _calculate_average_speed(self, flows: List[TrafficFlow]) -> float:
        """Calculate average speed from flow data."""
        if not flows:
            return 60.0  # Default speed
        
        total_speed = sum(flow.speed_kmh * flow.confidence for flow in flows)
        total_confidence = sum(flow.confidence for flow in flows)
        
        return total_speed / total_confidence if total_confidence > 0 else 60.0
    
    def _create_empty_traffic_data(self, route_id: str) -> TrafficData:
        """Create empty traffic data when API fails."""
        return TrafficData(
            route_id=route_id,
            flows=[],
            incidents=[],
            overall_jam_factor=0.0,
            average_speed_kmh=60.0,
            incident_count=0,
            last_updated=datetime.now(),
            provider="TomTom (fallback)",
            cache_until=datetime.now() + timedelta(seconds=60)  # Short cache for fallback
        )
