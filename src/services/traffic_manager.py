"""
Traffic Manager Service
=======================
Manages multiple traffic providers and integrates traffic data with ETA calculations.
"""

import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass

from src.providers import TomTomTrafficProvider, HereTrafficProvider, MockTrafficProvider
from src.providers.traffic_provider import TrafficProvider, TrafficData

logger = logging.getLogger(__name__)


@dataclass
class TrafficConfig:
    """Configuration for traffic integration"""
    enabled: bool = True
    provider_priority: List[str] = None  # ['tomtom', 'here', 'mock']
    cache_duration: int = 300  # 5 minutes
    fallback_to_mock: bool = True
    auto_refresh_interval: int = 60  # 1 minute
    max_retries: int = 3
    
    def __post_init__(self):
        if self.provider_priority is None:
            self.provider_priority = ['tomtom', 'here', 'mock']


class TrafficManager:
    """
    Manages traffic data providers and integrates traffic data with ETA calculations.
    
    Features:
    - Multiple provider support with fallback
    - Caching and auto-refresh
    - Integration with ETA model
    - Graceful error handling
    """
    
    def __init__(self, config: Optional[TrafficConfig] = None):
        """
        Initialize traffic manager.
        
        Args:
            config: Traffic configuration
        """
        self.config = config or TrafficConfig()
        self.providers: Dict[str, TrafficProvider] = {}
        self.active_provider: Optional[str] = None
        self.last_refresh: Optional[datetime] = None
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize available traffic providers."""
        # Initialize TomTom provider
        tomtom_key = os.getenv('TOMTOM_API_KEY')
        if tomtom_key:
            self.providers['tomtom'] = TomTomTrafficProvider(
                api_key=tomtom_key,
                cache_duration=self.config.cache_duration
            )
            logger.info("TomTom traffic provider initialized")
        
        # Initialize HERE provider
        here_key = os.getenv('HERE_API_KEY')
        if here_key:
            self.providers['here'] = HereTrafficProvider(
                api_key=here_key,
                cache_duration=self.config.cache_duration
            )
            logger.info("HERE traffic provider initialized")
        
        # Initialize Mock provider (always available)
        self.providers['mock'] = MockTrafficProvider(
            cache_duration=self.config.cache_duration
        )
        logger.info("Mock traffic provider initialized")
        
        # Set active provider based on priority
        self._set_active_provider()
    
    def _set_active_provider(self):
        """Set the active provider based on priority and availability."""
        for provider_name in self.config.provider_priority:
            if provider_name in self.providers and self.providers[provider_name].is_available():
                self.active_provider = provider_name
                logger.info(f"Active traffic provider: {provider_name}")
                return
        
        # Fallback to mock if no other provider is available
        if self.config.fallback_to_mock and 'mock' in self.providers:
            self.active_provider = 'mock'
            logger.warning("No real traffic providers available, using mock provider")
        else:
            self.active_provider = None
            logger.error("No traffic providers available")
    
    def get_traffic_data(
        self, 
        route_coordinates: List[Tuple[float, float]], 
        route_id: str
    ) -> Optional[TrafficData]:
        """
        Get traffic data for a route.
        
        Args:
            route_coordinates: List of (lat, lon) coordinates
            route_id: Unique route identifier
            
        Returns:
            TrafficData object or None if no provider available
        """
        if not self.config.enabled or not self.active_provider:
            return None
        
        try:
            provider = self.providers[self.active_provider]
            traffic_data = provider.get_traffic_data(route_coordinates, route_id)
            
            # Update last refresh time
            self.last_refresh = datetime.now()
            
            return traffic_data
            
        except Exception as e:
            logger.error(f"Error getting traffic data: {e}")
            
            # Try fallback providers
            if self._try_fallback_providers(route_coordinates, route_id):
                return self.get_traffic_data(route_coordinates, route_id)
            
            return None
    
    def _try_fallback_providers(self, route_coordinates: List[Tuple[float, float]], route_id: str) -> bool:
        """Try fallback providers if the active provider fails."""
        for provider_name in self.config.provider_priority:
            if provider_name != self.active_provider and provider_name in self.providers:
                try:
                    provider = self.providers[provider_name]
                    if provider.is_available():
                        self.active_provider = provider_name
                        logger.info(f"Switched to fallback provider: {provider_name}")
                        return True
                except Exception as e:
                    logger.error(f"Fallback provider {provider_name} failed: {e}")
        
        return False
    
    def should_refresh_traffic_data(self) -> bool:
        """Check if traffic data should be refreshed."""
        if not self.last_refresh:
            return True
        
        time_since_refresh = datetime.now() - self.last_refresh
        return time_since_refresh.total_seconds() >= self.config.auto_refresh_interval
    
    def get_traffic_multiplier(self, traffic_data: Optional[TrafficData]) -> float:
        """
        Calculate traffic multiplier for ETA adjustment with enhanced weighting.
        
        Args:
            traffic_data: Traffic data from provider
            
        Returns:
            Multiplier value (1.0 = no impact, >1.0 = slower, <1.0 = faster)
        """
        if not traffic_data:
            return 1.0
        
        # Enhanced base multiplier from jam factor (increased weight)
        jam_multiplier = 1.0 + (traffic_data.overall_jam_factor * 1.0)  # Increased from 0.5 to 1.0 (max 100% increase)
        
        # Enhanced incident multiplier (increased weight)
        incident_multiplier = 1.0
        if traffic_data.incident_count > 0:
            # Each incident adds 10-20% depending on severity (increased from 5-15%)
            incident_impact = min(0.2, traffic_data.incident_count * 0.1)
            incident_multiplier = 1.0 + incident_impact
        
        # Enhanced speed-based multiplier (increased weight)
        speed_multiplier = 1.0
        if traffic_data.average_speed_kmh < 60:  # Below normal speed
            speed_ratio = traffic_data.average_speed_kmh / 60.0
            speed_multiplier = 1.0 + (1.0 - speed_ratio) * 0.6  # Increased from 0.3 to 0.6 (max 60% increase)
        
        # Combine multipliers with enhanced weighting
        total_multiplier = jam_multiplier * incident_multiplier * speed_multiplier
        
        # Apply enhanced bounds (increased maximum impact)
        return max(0.6, min(2.2, total_multiplier))  # Increased from 0.7-1.8 to 0.6-2.2 (60% - 220% of base time)
    
    def get_traffic_conditions(self, traffic_data: Optional[TrafficData]) -> Dict[str, Any]:
        """
        Extract traffic conditions for ETA model integration.
        
        Args:
            traffic_data: Traffic data from provider
            
        Returns:
            Dictionary of traffic conditions
        """
        if not traffic_data:
            return {
                'live_traffic_enabled': False,
                'jam_factor': 0.0,
                'incident_count': 0,
                'average_speed_kmh': 60.0,
                'provider': 'none'
            }
        
        return {
            'live_traffic_enabled': True,
            'jam_factor': traffic_data.overall_jam_factor,
            'incident_count': traffic_data.incident_count,
            'average_speed_kmh': traffic_data.average_speed_kmh,
            'provider': traffic_data.provider,
            'last_updated': traffic_data.last_updated.isoformat(),
            'incidents': [
                {
                    'type': incident.incident_type,
                    'severity': incident.severity,
                    'description': incident.description
                }
                for incident in traffic_data.incidents
            ]
        }
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {
            'enabled': self.config.enabled,
            'active_provider': self.active_provider,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'providers': {}
        }
        
        for name, provider in self.providers.items():
            status['providers'][name] = {
                'available': provider.is_available(),
                'cache_stats': provider.get_cache_stats()
            }
        
        return status
    
    def clear_all_caches(self):
        """Clear caches for all providers."""
        for provider in self.providers.values():
            provider.clear_cache()
        logger.info("Cleared all traffic provider caches")
    
    def update_config(self, config: TrafficConfig):
        """Update traffic configuration."""
        self.config = config
        self._set_active_provider()
        logger.info("Updated traffic manager configuration")
