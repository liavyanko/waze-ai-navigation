"""
HERE Traffic Provider
=====================
Real-time traffic data provider using HERE Traffic API.
"""

import requests
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from .traffic_provider import TrafficProvider, TrafficData, TrafficFlow, TrafficIncident

logger = logging.getLogger(__name__)


class HereTrafficProvider(TrafficProvider):
    """
    HERE Traffic API provider for real-time traffic data.
    
    Documentation: https://developer.here.com/documentation/traffic-api
    """
    
    def __init__(self, api_key: str, cache_duration: int = 300):
        """
        Initialize HERE provider.
        
        Args:
            api_key: HERE API key
            cache_duration: Cache duration in seconds
        """
        super().__init__(api_key, cache_duration)
        self.base_url = "https://traffic.ls.hereapi.com/traffic/6.2"
        
    def is_available(self) -> bool:
        """Check if HERE provider is available."""
        return bool(self.api_key)
    
    def get_traffic_data(
        self, 
        route_coordinates: List[Tuple[float, float]], 
        route_id: str
    ) -> TrafficData:
        """
        Get traffic data from HERE API.
        
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
                provider="HERE",
                cache_until=datetime.now() + timedelta(seconds=self.cache_duration)
            )
            
            # Update cache
            self._update_cache(route_id, traffic_data)
            
            return traffic_data
            
        except Exception as e:
            logger.error(f"Error fetching HERE traffic data: {e}")
            # Return empty traffic data on error
            return self._create_empty_traffic_data(route_id)
    
    def _get_flow_data(self, coordinates: List[Tuple[float, float]]) -> List[TrafficFlow]:
        """Get traffic flow data from HERE."""
        try:
            # Create bounding box from coordinates
            lats = [coord[0] for coord in coordinates]
            lons = [coord[1] for coord in coordinates]
            
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
            
            # Build URL
            url = f"{self.base_url}/flow.json"
            params = {
                'apiKey': self.api_key,
                'bbox': bbox,
                'responseattributes': 'sh,fc',
                'unit': 'km'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            flows = []
            
            if 'RWS' in data:
                for rw in data['RWS']:
                    if 'RW' in rw:
                        for road in rw['RW']:
                            if 'FIS' in road:
                                for flow in road['FIS']:
                                    if 'FI' in flow:
                                        for item in flow['FI']:
                                            # Extract speed and jam factor
                                            speed = item.get('CF', {}).get('SPEED', {}).get('value', 60)
                                            jam_factor = item.get('CF', {}).get('JF', {}).get('value', 0) / 100.0
                                            
                                            flow_data = TrafficFlow(
                                                segment_id=road.get('id', 'unknown'),
                                                speed_kmh=float(speed),
                                                free_flow_speed_kmh=float(speed) * (1 + jam_factor),
                                                jam_factor=jam_factor,
                                                confidence=0.8,
                                                timestamp=datetime.now()
                                            )
                                            flows.append(flow_data)
            
            return flows
            
        except Exception as e:
            logger.error(f"Error fetching HERE flow data: {e}")
            return []
    
    def _get_incident_data(self, coordinates: List[Tuple[float, float]]) -> List[TrafficIncident]:
        """Get traffic incident data from HERE."""
        try:
            # Create bounding box from coordinates
            lats = [coord[0] for coord in coordinates]
            lons = [coord[1] for coord in coordinates]
            
            bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
            
            # Build URL
            url = f"{self.base_url}/incidents.json"
            params = {
                'apiKey': self.api_key,
                'bbox': bbox,
                'responseattributes': 'sh,fc',
                'unit': 'km'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            incidents = []
            
            if 'TRAFFICITEMS' in data:
                for item in data['TRAFFICITEMS'].get('TRAFFICITEM', []):
                    incident = TrafficIncident(
                        incident_id=item.get('TRAFFICITEMID', 'unknown'),
                        incident_type=self._map_incident_type(item.get('TRAFFICITEMTYPEDESC', '')),
                        severity=self._map_severity(item.get('CRITICALITY', {}).get('DESCRIPTION', '')),
                        description=item.get('TRAFFICITEMDESCRIPTION', 'Unknown incident'),
                        location=(item.get('GEOLOC', {}).get('ORIGIN', {}).get('LATITUDE', 0),
                                 item.get('GEOLOC', {}).get('ORIGIN', {}).get('LONGITUDE', 0)),
                        affected_road=item.get('LOCATION', {}).get('DESCRIPTION', 'Unknown road'),
                        start_time=datetime.now(),
                        end_time=None,
                        confidence=0.8
                    )
                    incidents.append(incident)
            
            return incidents
            
        except Exception as e:
            logger.error(f"Error fetching HERE incident data: {e}")
            return []
    
    def _map_incident_type(self, description: str) -> str:
        """Map HERE incident description to incident type."""
        description_lower = description.lower()
        
        if 'accident' in description_lower:
            return 'accident'
        elif 'construction' in description_lower:
            return 'construction'
        elif 'closure' in description_lower:
            return 'closure'
        elif 'weather' in description_lower:
            return 'weather'
        elif 'congestion' in description_lower:
            return 'congestion'
        else:
            return 'unknown'
    
    def _map_severity(self, description: str) -> str:
        """Map HERE severity description to severity level."""
        description_lower = description.lower()
        
        if 'critical' in description_lower or 'high' in description_lower:
            return 'high'
        elif 'medium' in description_lower:
            return 'medium'
        else:
            return 'low'
    
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
            provider="HERE (fallback)",
            cache_until=datetime.now() + timedelta(seconds=60)  # Short cache for fallback
        )
