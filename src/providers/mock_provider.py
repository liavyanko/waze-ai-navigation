"""
Mock Traffic Provider
====================
Mock traffic data provider for testing and fallback scenarios.
"""

import random
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from .traffic_provider import TrafficProvider, TrafficData, TrafficFlow, TrafficIncident

logger = logging.getLogger(__name__)


class MockTrafficProvider(TrafficProvider):
    """
    Mock traffic data provider for testing and development.
    
    Generates realistic mock traffic data without requiring API keys.
    """
    
    def __init__(self, cache_duration: int = 300):
        """
        Initialize mock provider.
        
        Args:
            cache_duration: Cache duration in seconds
        """
        super().__init__(None, cache_duration)
        self._seed = random.randint(1, 10000)
        
    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True
    
    def get_traffic_data(
        self, 
        route_coordinates: List[Tuple[float, float]], 
        route_id: str
    ) -> TrafficData:
        """
        Generate mock traffic data.
        
        Args:
            route_coordinates: List of (lat, lon) coordinates
            route_id: Unique route identifier
            
        Returns:
            TrafficData object with mock data
        """
        # Check cache first
        cached_data = self._get_cached_data(route_id)
        if cached_data:
            return cached_data
        
        try:
            # Generate mock flows based on route length
            flows = self._generate_mock_flows(route_coordinates)
            
            # Generate mock incidents
            incidents = self._generate_mock_incidents(route_coordinates)
            
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
                provider="Mock",
                cache_until=datetime.now() + timedelta(seconds=self.cache_duration)
            )
            
            # Update cache
            self._update_cache(route_id, traffic_data)
            
            return traffic_data
            
        except Exception as e:
            logger.error(f"Error generating mock traffic data: {e}")
            return self._create_empty_traffic_data(route_id)
    
    def _generate_mock_flows(self, coordinates: List[Tuple[float, float]]) -> List[TrafficFlow]:
        """Generate mock traffic flow data."""
        flows = []
        
        # Use route length to determine number of segments
        route_length = len(coordinates)
        num_segments = max(1, min(route_length // 5, 10))  # 1-10 segments
        
        # Generate time-based variation
        hour = datetime.now().hour
        base_jam_factor = self._get_time_based_jam_factor(hour)
        
        for i in range(num_segments):
            # Add some randomness based on segment position
            segment_factor = (i / num_segments) * 0.3 + 0.7  # 0.7-1.0
            
            # Generate jam factor with realistic variation
            jam_factor = max(0.0, min(1.0, base_jam_factor * segment_factor + random.uniform(-0.1, 0.1)))
            
            # Calculate speed based on jam factor
            free_flow_speed = random.uniform(80, 120)  # 80-120 km/h
            current_speed = free_flow_speed * (1 - jam_factor * 0.7)  # Speed decreases with jam
            
            flow = TrafficFlow(
                segment_id=f"mock_segment_{i}",
                speed_kmh=max(10, current_speed),  # Minimum 10 km/h
                free_flow_speed_kmh=free_flow_speed,
                jam_factor=jam_factor,
                confidence=random.uniform(0.7, 0.95),
                timestamp=datetime.now()
            )
            flows.append(flow)
        
        return flows
    
    def _generate_mock_incidents(self, coordinates: List[Tuple[float, float]]) -> List[TrafficIncident]:
        """Generate mock traffic incidents."""
        incidents = []
        
        # Probability of incidents based on route length
        route_length = len(coordinates)
        incident_probability = min(0.3, route_length / 100)  # Max 30% chance
        
        if random.random() < incident_probability:
            # Generate 1-3 incidents
            num_incidents = random.randint(1, min(3, route_length // 20))
            
            incident_types = ['accident', 'construction', 'congestion', 'weather']
            severities = ['low', 'medium', 'high']
            
            for i in range(num_incidents):
                # Pick random coordinate for incident location
                incident_coord = random.choice(coordinates)
                
                incident = TrafficIncident(
                    incident_id=f"mock_incident_{i}",
                    incident_type=random.choice(incident_types),
                    severity=random.choice(severities),
                    description=f"Mock {random.choice(incident_types)} incident",
                    location=incident_coord,
                    affected_road=f"Road {i+1}",
                    start_time=datetime.now() - timedelta(minutes=random.randint(10, 120)),
                    end_time=None,
                    confidence=random.uniform(0.8, 0.95)
                )
                incidents.append(incident)
        
        return incidents
    
    def _get_time_based_jam_factor(self, hour: int) -> float:
        """Get base jam factor based on time of day."""
        if 7 <= hour <= 9:  # Morning rush
            return random.uniform(0.4, 0.7)
        elif 16 <= hour <= 19:  # Evening rush
            return random.uniform(0.5, 0.8)
        elif 22 <= hour or hour <= 5:  # Night
            return random.uniform(0.0, 0.2)
        else:  # Daytime
            return random.uniform(0.1, 0.4)
    
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
        """Create empty traffic data when generation fails."""
        return TrafficData(
            route_id=route_id,
            flows=[],
            incidents=[],
            overall_jam_factor=0.0,
            average_speed_kmh=60.0,
            incident_count=0,
            last_updated=datetime.now(),
            provider="Mock (fallback)",
            cache_until=datetime.now() + timedelta(seconds=60)  # Short cache for fallback
        )
