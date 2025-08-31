import math
import importlib

# Import app module functions
app = importlib.import_module("app")
bayes = importlib.import_module("bayes_model")


def test_haversine_symmetric():
    # NYC Times Sq to Central Park South (approx)
    lat1, lon1 = 40.7580, -73.9855
    lat2, lon2 = 40.7677, -73.9718
    d1 = app._haversine_km(lat1, lon1, lat2, lon2)
    d2 = app._haversine_km(lat2, lon2, lat1, lon1)
    assert abs(d1 - d2) < 1e-9
    assert 1.0 < d1 < 3.0  # about 1.6km


def test_fmt_minutes():
    assert app.fmt_minutes(0) == "0m"
    assert app.fmt_minutes(59) == "59m"
    assert app.fmt_minutes(60) == "1h 0m"
    assert app.fmt_minutes(125) == "2h 5m"


def test_multiplier_reasonable():
    m = bayes.predict_travel_multiplier(
        weather="rain",
        time_of_day="evening_peak",
        day_type="weekday",
        road_problem="construction",
        police_activity="medium",
        driving_history="normal",
    )
    assert 1.0 <= m <= 3.0


def test_multiplier_neutralish():
    m = bayes.predict_travel_multiplier(
        weather="clear",
        time_of_day="midday",
        day_type="weekend",
        road_problem="none",
        police_activity="low",
        driving_history="calm",
    )
    assert 0.7 <= m <= 1.2
