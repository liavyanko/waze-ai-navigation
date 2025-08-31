# config.py
"""
Global configuration constants for Waze-Bayes project.
"""

# APIs
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

# HTTP
USER_AGENT = "waze-ai-mvp/1.0 (liavyanko@gmail.com)"  

# Defaults
AVERAGE_SPEED_KMH = 80.0  # fallback speed for Haversine
REQUEST_TIMEOUT = 10
CACHE_TTL = 300  # cache duration in seconds

# Calibration factor for Haversine normalization
AVERAGE_NORMALIZATION_FACTOR = 1.25  # update this after calibration runs

# Multiplier weights for estimated_travel_time states
MULTIPLIER_WEIGHTS = {"short": 1.0, "medium": 1.35, "long": 1.85}

# Geocoding extras
PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

USE_PGMPY = True

# ישראליות (לוגיות/תצוגה)
DEFAULT_UNITS = "metric"  # km


