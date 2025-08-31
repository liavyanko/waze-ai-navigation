"""
Base Traffic Provider
====================
Abstract base class for traffic data providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class TrafficFlow:
    """Traffic flow data for a road segment"""
    segment_id: str
    speed_kmh: float
    free_flow_speed_kmh: float
    jam_factor: float  # 0.0 = free flow, 1.0 = complete jam
    confidence: float  # 0.0-1.0 confidence in the data
    timestamp: datetime


@dataclass
class TrafficIncident:
    """Traffic incident data"""
    incident_id: str
    incident_type: str  # 'accident', 'construction', 'closure', 'weather', etc.
    severity: str  # 'low', 'medium', 'high'
    description: str
    location: Tuple[float, float]  # lat, lon
    affected_road: str
    start_time: datetime
    end_time: Optional[datetime]
    confidence: float


@dataclass
class TrafficData:
    """Complete traffic data for a route"""
    route_id: str
    flows: List[TrafficFlow]
    incidents: List[TrafficIncident]
    overall_jam_factor: float  # 0.0-1.0 average jam factor
    average_speed_kmh: float
    incident_count: int
    last_updated: datetime
    provider: str
    cache_until: datetime


class TrafficProvider(ABC):
    """
    Abstract base class for traffic data providers.
    
    All traffic providers must implement these methods to provide
    real-time traffic data for route optimization.
    """
    
    def __init__(self, api_key: Optional[str] = None, cache_duration: int = 300):
        """
        Initialize the traffic provider.
        
        Args:
            api_key: API key for the provider (if required)
            cache_duration: Cache duration in seconds (default: 5 minutes)
        """
        self.api_key = api_key
        self.cache_duration = cache_duration
        self._cache: Dict[str, TrafficData] = {}
        self._last_request_time: Dict[str, datetime] = {}
        
    @abstractmethod
    def get_traffic_data(
        self, 
        route_coordinates: List[Tuple[float, float]], 
        route_id: str
    ) -> TrafficData:
        """
        Get traffic data for a specific route.
        
        Args:
            route_coordinates: List of (lat, lon) coordinates along the route
            route_id: Unique identifier for the route
            
        Returns:
            TrafficData object containing flows and incidents
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.
        
        Returns:
            True if the provider can be used
        """
        pass
    
    def _is_cache_valid(self, route_id: str) -> bool:
        """Check if cached data is still valid."""
        if route_id not in self._cache:
            return False
        
        cached_data = self._cache[route_id]
        return datetime.now() < cached_data.cache_until
    
    def _update_cache(self, route_id: str, traffic_data: TrafficData):
        """Update the cache with new traffic data."""
        cache_until = datetime.now() + timedelta(seconds=self.cache_duration)
        traffic_data.cache_until = cache_until
        self._cache[route_id] = traffic_data
        self._last_request_time[route_id] = datetime.now()
    
    def _get_cached_data(self, route_id: str) -> Optional[TrafficData]:
        """Get cached traffic data if valid."""
        if self._is_cache_valid(route_id):
            return self._cache[route_id]
        return None
    
    def clear_cache(self):
        """Clear all cached traffic data."""
        self._cache.clear()
        self._last_request_time.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cached_routes': len(self._cache),
            'cache_duration': self.cache_duration,
            'last_requests': self._last_request_time.copy()
        }
