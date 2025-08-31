#!/usr/bin/env python3
"""
Test script for the refactored Waze AI Navigation App
===================================================
Tests all major components and functionality.
"""

import sys
import os
# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_imports():
    """Test that all modules can be imported successfully."""
    print("🧪 Testing imports...")
    
    try:
        from components.ui_components import (
            render_search_bar,
            render_bottom_sheet,
            render_floating_buttons,
            render_route_chips,
            render_error_messages
        )
        print("✅ UI components imported successfully")
    except Exception as e:
        print(f"❌ UI components import failed: {e}")
        return False
    
    try:
        from app import (
            nominatim_search,
            photon_autocomplete,
            osrm_route,
            fetch_weather_auto,
            compute_base_times
        )
        print("✅ Core app functions imported successfully")
    except Exception as e:
        print(f"❌ Core app functions import failed: {e}")
        return False
    
    try:
        from bayes_model import predict_travel_multiplier, predict_travel_with_details
        print("✅ Traffic model imported successfully")
    except Exception as e:
        print(f"❌ Traffic model import failed: {e}")
        return False
    
    return True

def test_ui_components():
    """Test UI component rendering."""
    print("\n🧪 Testing UI components...")
    
    try:
        from components.ui_components import (
            render_search_bar,
            render_bottom_sheet,
            render_floating_buttons,
            render_route_chips,
            render_error_messages
        )
        
        # Test search bar
        search_html = render_search_bar()
        assert "floating-search-bar" in search_html
        print("✅ Search bar renders correctly")
        
        # Test bottom sheet
        bottom_html = render_bottom_sheet(eta_minutes=30.5, multiplier=1.2)
        assert "bottom-sheet" in bottom_html
        assert "30m" in bottom_html or "1h" in bottom_html
        print("✅ Bottom sheet renders correctly")
        
        # Test floating buttons
        buttons_html = render_floating_buttons()
        assert "fabs" in buttons_html
        assert "navigation" in buttons_html
        print("✅ Floating buttons render correctly")
        
        # Test route chips
        routes = [
            {"minutes": 25.0, "km": 15.2},
            {"minutes": 30.0, "km": 18.1},
            {"minutes": 35.0, "km": 20.5}
        ]
        chips_html = render_route_chips(routes)
        assert "route-chips" in chips_html
        assert "Route A" in chips_html
        print("✅ Route chips render correctly")
        
        # Test error messages
        error_html = render_error_messages("no_locations")
        assert "alert warning" in error_html
        assert "Select Locations" in error_html
        print("✅ Error messages render correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ UI component test failed: {e}")
        return False

def test_core_functions():
    """Test core application functions."""
    print("\n🧪 Testing core functions...")
    
    try:
        from app import (
            fmt_minutes,
            _haversine_km,
            photon_autocomplete,
            fetch_weather_auto
        )
        
        # Test time formatting
        assert fmt_minutes(65.5) == "1h 6m"
        assert fmt_minutes(30.0) == "30m"
        assert fmt_minutes(None) == "—"
        print("✅ Time formatting works correctly")
        
        # Test distance calculation
        distance = _haversine_km(31.4118, 35.0818, 31.4118, 35.0818)  # Same point
        assert abs(distance) < 0.001
        print("✅ Distance calculation works correctly")
        
        # Test autocomplete (with a simple query)
        suggestions = photon_autocomplete("Tel Aviv", limit=3)
        assert isinstance(suggestions, list)
        print("✅ Autocomplete works correctly")
        
        # Test weather fetch (with a known location)
        weather = fetch_weather_auto(31.4118, 35.0818)  # Jerusalem
        assert isinstance(weather, dict)
        assert "category" in weather
        print("✅ Weather fetch works correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Core function test failed: {e}")
        return False

def test_traffic_model():
    """Test traffic prediction model."""
    print("\n🧪 Testing traffic model...")
    
    try:
        from bayes_model import predict_travel_multiplier, predict_travel_with_details
        
        # Test simple prediction
        multiplier = predict_travel_multiplier(
            weather="clear",
            time_of_day="midday",
            day_type="weekday",
            road_problem="none",
            police_activity="low",
            driving_history="normal"
        )
        assert isinstance(multiplier, float)
        assert 0.5 <= multiplier <= 3.0
        print("✅ Traffic multiplier prediction works correctly")
        
        # Test detailed prediction
        details = predict_travel_with_details(
            weather="rain",
            time_of_day="evening_peak",
            day_type="weekday",
            road_problem="accident",
            police_activity="high",
            driving_history="aggressive"
        )
        assert isinstance(details, dict)
        assert "multiplier" in details
        assert "rows" in details
        assert "marginals" in details
        print("✅ Detailed traffic prediction works correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Traffic model test failed: {e}")
        return False

def test_file_structure():
    """Test that all required files exist."""
    print("\n🧪 Testing file structure...")
    
    required_files = [
        "app.py",
        "components/ui_components.py",
        "static/css/uiux.css",
        "static/js/interactions.js",
        "templates/base.html",
        "templates/components/search_bar.html",
        "templates/components/bottom_sheet.html",
        "templates/components/floating_buttons.html",
        "templates/components/route_chips.html",
        "templates/components/error_messages.html",
        "bayes_model.py",
        "config.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return False
    else:
        print("✅ All required files exist")
        return True

def main():
    """Run all tests."""
    print("🚀 Testing Refactored Waze AI Navigation App")
    print("=" * 50)
    
    tests = [
        test_file_structure,
        test_imports,
        test_ui_components,
        test_core_functions,
        test_traffic_model
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"❌ Test {test.__name__} failed")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The refactored app is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
