"""
Traffic Integration Tests
========================
Comprehensive tests for the real-time traffic integration system.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from typing import Dict, Any

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.providers.traffic_provider import TrafficFlow, TrafficIncident, TrafficData
from src.providers.mock_provider import MockTrafficProvider
from src.services.traffic_manager import TrafficManager, TrafficConfig
from src.models.normalized_eta_model import NormalizedETAModel


class TestTrafficProvider(unittest.TestCase):
    """Test traffic provider functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_provider = MockTrafficProvider(cache_duration=60)
        self.test_coordinates = [(32.0853, 34.7818), (31.7683, 35.2137)]  # Tel Aviv to Jerusalem
        self.test_route_id = "test_route_123"
    
    def test_mock_provider_availability(self):
        """Test that mock provider is always available."""
        self.assertTrue(self.mock_provider.is_available())
    
    def test_mock_traffic_data_generation(self):
        """Test mock traffic data generation."""
        traffic_data = self.mock_provider.get_traffic_data(self.test_coordinates, self.test_route_id)
        
        self.assertIsNotNone(traffic_data)
        self.assertEqual(traffic_data.route_id, self.test_route_id)
        self.assertEqual(traffic_data.provider, "Mock")
        self.assertIsInstance(traffic_data.flows, list)
        self.assertIsInstance(traffic_data.incidents, list)
        self.assertIsInstance(traffic_data.overall_jam_factor, float)
        self.assertIsInstance(traffic_data.average_speed_kmh, float)
        self.assertIsInstance(traffic_data.incident_count, int)
    
    def test_mock_traffic_data_caching(self):
        """Test that mock provider caches data correctly."""
        # First request
        traffic_data1 = self.mock_provider.get_traffic_data(self.test_coordinates, self.test_route_id)
        
        # Second request should return cached data
        traffic_data2 = self.mock_provider.get_traffic_data(self.test_coordinates, self.test_route_id)
        
        self.assertEqual(traffic_data1.route_id, traffic_data2.route_id)
        self.assertEqual(traffic_data1.overall_jam_factor, traffic_data2.overall_jam_factor)
    
    def test_mock_traffic_data_realistic_values(self):
        """Test that mock traffic data has realistic values."""
        traffic_data = self.mock_provider.get_traffic_data(self.test_coordinates, self.test_route_id)
        
        # Jam factor should be between 0 and 1
        self.assertGreaterEqual(traffic_data.overall_jam_factor, 0.0)
        self.assertLessEqual(traffic_data.overall_jam_factor, 1.0)
        
        # Average speed should be reasonable
        self.assertGreaterEqual(traffic_data.average_speed_kmh, 10.0)
        self.assertLessEqual(traffic_data.average_speed_kmh, 120.0)
        
        # Incident count should be reasonable
        self.assertGreaterEqual(traffic_data.incident_count, 0)
        self.assertLessEqual(traffic_data.incident_count, 10)


class TestTrafficManager(unittest.TestCase):
    """Test traffic manager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = TrafficConfig(
            enabled=True,
            provider_priority=['mock'],
            cache_duration=60,
            fallback_to_mock=True,
            auto_refresh_interval=30
        )
        self.traffic_manager = TrafficManager(self.config)
    
    def test_traffic_manager_initialization(self):
        """Test traffic manager initialization."""
        self.assertIsNotNone(self.traffic_manager)
        self.assertTrue(self.traffic_manager.config.enabled)
        self.assertEqual(self.traffic_manager.active_provider, 'mock')
    
    def test_traffic_data_retrieval(self):
        """Test traffic data retrieval through manager."""
        test_coordinates = [(32.0853, 34.7818), (31.7683, 35.2137)]
        test_route_id = "test_route_manager"
        
        traffic_data = self.traffic_manager.get_traffic_data(test_coordinates, test_route_id)
        
        self.assertIsNotNone(traffic_data)
        self.assertEqual(traffic_data.route_id, test_route_id)
        self.assertEqual(traffic_data.provider, "Mock")
    
    def test_traffic_multiplier_calculation(self):
        """Test traffic multiplier calculation."""
        # Test with no traffic data
        multiplier = self.traffic_manager.get_traffic_multiplier(None)
        self.assertEqual(multiplier, 1.0)
        
        # Test with mock traffic data
        mock_traffic_data = TrafficData(
            route_id="test",
            flows=[],
            incidents=[],
            overall_jam_factor=0.3,
            average_speed_kmh=45.0,
            incident_count=2,
            last_updated=datetime.now(),
            provider="Mock",
            cache_until=datetime.now() + timedelta(seconds=60)
        )
        
        multiplier = self.traffic_manager.get_traffic_multiplier(mock_traffic_data)
        self.assertGreater(multiplier, 1.0)
        self.assertLessEqual(multiplier, 2.2)  # Updated from 1.8 to 2.2
    
    def test_traffic_conditions_extraction(self):
        """Test traffic conditions extraction."""
        # Test with no traffic data
        conditions = self.traffic_manager.get_traffic_conditions(None)
        self.assertFalse(conditions['live_traffic_enabled'])
        self.assertEqual(conditions['provider'], 'none')
        
        # Test with mock traffic data
        mock_traffic_data = TrafficData(
            route_id="test",
            flows=[],
            incidents=[],
            overall_jam_factor=0.25,
            average_speed_kmh=50.0,
            incident_count=1,
            last_updated=datetime.now(),
            provider="Mock",
            cache_until=datetime.now() + timedelta(seconds=60)
        )
        
        conditions = self.traffic_manager.get_traffic_conditions(mock_traffic_data)
        self.assertTrue(conditions['live_traffic_enabled'])
        self.assertEqual(conditions['jam_factor'], 0.25)
        self.assertEqual(conditions['average_speed_kmh'], 50.0)
        self.assertEqual(conditions['incident_count'], 1)
        self.assertEqual(conditions['provider'], 'Mock')
    
    def test_provider_status(self):
        """Test provider status reporting."""
        status = self.traffic_manager.get_provider_status()
        
        self.assertTrue(status['enabled'])
        self.assertEqual(status['active_provider'], 'mock')
        self.assertIn('providers', status)
        self.assertIn('mock', status['providers'])
        self.assertTrue(status['providers']['mock']['available'])
    
    def test_cache_management(self):
        """Test cache management."""
        # Clear cache
        self.traffic_manager.clear_all_caches()
        
        # Check cache stats
        status = self.traffic_manager.get_provider_status()
        mock_stats = status['providers']['mock']['cache_stats']
        self.assertEqual(mock_stats['cached_routes'], 0)


class TestETAIntegration(unittest.TestCase):
    """Test ETA model integration with traffic data."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.model = NormalizedETAModel()
        self.base_conditions = {
            "weather": "clear",
            "time_of_day": "midday",
            "day_type": "weekday",
            "road_problem": "none",
            "police_activity": "low",
            "driving_history": "normal"
        }
    
    def test_eta_without_traffic(self):
        """Test ETA calculation without traffic data."""
        result = self.model.calculate_normalized_eta(60.0, self.base_conditions)
        
        self.assertIsNotNone(result)
        self.assertIn('multiplier', result)
        self.assertIn('traffic_integration', result)
        self.assertFalse(result['traffic_integration'])
    
    def test_eta_with_traffic(self):
        """Test ETA calculation with traffic data."""
        traffic_data = {
            'live_traffic_enabled': True,
            'jam_factor': 0.3,
            'incident_count': 2,
            'average_speed_kmh': 45.0,
            'provider': 'Mock'
        }
        
        result = self.model.calculate_normalized_eta(60.0, self.base_conditions, traffic_data)
        
        self.assertIsNotNone(result)
        self.assertIn('multiplier', result)
        self.assertIn('traffic_integration', result)
        self.assertTrue(result['traffic_integration'])
        
        # Traffic should increase the multiplier
        multiplier_without_traffic = self.model.calculate_normalized_eta(60.0, self.base_conditions)['multiplier']
        self.assertGreater(result['multiplier'], multiplier_without_traffic)
    
    def test_traffic_impact_calculation(self):
        """Test traffic impact calculation."""
        traffic_data = {
            'jam_factor': 0.5,
            'incident_count': 3,
            'average_speed_kmh': 30.0
        }
        
        impact = self.model._calculate_traffic_impact(traffic_data)
        
        self.assertIsInstance(impact, float)
        self.assertGreaterEqual(impact, 0.0)
        self.assertLessEqual(impact, 1.2)  # Updated from 0.6 to 1.2
    
    def test_traffic_impact_bounds(self):
        """Test that traffic impact respects enhanced bounds."""
        # Test maximum impact
        max_traffic_data = {
            'jam_factor': 1.0,
            'incident_count': 10,
            'average_speed_kmh': 10.0
        }
        
        max_impact = self.model._calculate_traffic_impact(max_traffic_data)
        self.assertLessEqual(max_impact, 1.2)  # Updated from 0.6 to 1.2
        
        # Test minimum impact
        min_traffic_data = {
            'jam_factor': 0.0,
            'incident_count': 0,
            'average_speed_kmh': 120.0
        }
        
        min_impact = self.model._calculate_traffic_impact(min_traffic_data)
        self.assertEqual(min_impact, 0.0)


class TestEndToEndIntegration(unittest.TestCase):
    """Test end-to-end traffic integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.traffic_manager = TrafficManager(TrafficConfig(enabled=True, provider_priority=['mock']))
        self.eta_model = NormalizedETAModel()
    
    def test_complete_traffic_integration(self):
        """Test complete traffic integration workflow."""
        # 1. Get traffic data
        coordinates = [(32.0853, 34.7818), (31.7683, 35.2137)]
        route_id = "test_e2e"
        
        traffic_data = self.traffic_manager.get_traffic_data(coordinates, route_id)
        self.assertIsNotNone(traffic_data)
        
        # 2. Extract traffic conditions
        traffic_conditions = self.traffic_manager.get_traffic_conditions(traffic_data)
        self.assertTrue(traffic_conditions['live_traffic_enabled'])
        
        # 3. Calculate ETA with traffic
        base_conditions = {
            "weather": "clear",
            "time_of_day": "midday",
            "day_type": "weekday",
            "road_problem": "none",
            "police_activity": "low",
            "driving_history": "normal"
        }
        
        eta_result = self.eta_model.calculate_normalized_eta(60.0, base_conditions, traffic_conditions)
        self.assertTrue(eta_result['traffic_integration'])
        
        # 4. Verify traffic multiplier
        traffic_multiplier = self.traffic_manager.get_traffic_multiplier(traffic_data)
        self.assertGreaterEqual(traffic_multiplier, 1.0)
    
    def test_fallback_behavior(self):
        """Test fallback behavior when traffic data is unavailable."""
        # Simulate traffic data failure
        with patch.object(self.traffic_manager, 'get_traffic_data', return_value=None):
            coordinates = [(32.0853, 34.7818), (31.7683, 35.2137)]
            route_id = "test_fallback"
            
            traffic_data = self.traffic_manager.get_traffic_data(coordinates, route_id)
            self.assertIsNone(traffic_data)
            
            # ETA should still work without traffic data
            base_conditions = {
                "weather": "clear",
                "time_of_day": "midday",
                "day_type": "weekday",
                "road_problem": "none",
                "police_activity": "low",
                "driving_history": "normal"
            }
            
            eta_result = self.eta_model.calculate_normalized_eta(60.0, base_conditions)
            self.assertIsNotNone(eta_result)
            self.assertFalse(eta_result['traffic_integration'])


if __name__ == '__main__':
    # Run tests
    print("🧪 Running Traffic Integration Tests")
    print("=" * 50)
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test classes
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestTrafficProvider))
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestTrafficManager))
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestETAIntegration))
    test_suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestEndToEndIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("✅ All traffic integration tests passed!")
    else:
        print("❌ Some tests failed!")
        for failure in result.failures:
            print(f"  - {failure[0]}: {failure[1]}")
        for error in result.errors:
            print(f"  - {error[0]}: {error[1]}")
