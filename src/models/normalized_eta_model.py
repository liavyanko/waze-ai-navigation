"""
Normalized ETA Adjustment Model
==============================
This model addresses the over-inflation issue on long trips by implementing:
- Duration-aware scaling (short trips get stronger effects, long trips get dampened)
- Hard caps by severity band
- Diminishing returns for multiple conditions
- Additive + multiplicative blend
- Context weighting
- Continuity and stability
"""

import math
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ETAConfig:
    """Configuration for ETA normalization parameters"""
    
    # Duration breakpoints (in minutes)
    SHORT_TRIP_THRESHOLD: float = 30.0      # ≤30 min: full multiplier effects
    MEDIUM_TRIP_THRESHOLD: float = 120.0    # ≤2h: moderate dampening
    LONG_TRIP_THRESHOLD: float = 300.0      # ≥5h: heavy dampening
    
    # Severity-based caps (maximum total inflation)
    LIGHT_SEVERITY_CAP: float = 0.35        # +35% max for light conditions
    MODERATE_SEVERITY_CAP: float = 0.50     # +50% max for moderate conditions  
    HEAVY_SEVERITY_CAP: float = 0.60        # +60% max for heavy conditions
    
    # Dampening slopes (how quickly effects diminish with duration)
    SHORT_TO_MEDIUM_SLOPE: float = 0.8     # 80% of effect retained at medium threshold
    MEDIUM_TO_LONG_SLOPE: float = 0.5      # 50% of effect retained at long threshold
    
    # Additive penalties (per hour of travel)
    WEATHER_ADDITIVE_PER_HOUR: float = 2.0  # 2 min per hour for weather
    TRAFFIC_ADDITIVE_PER_HOUR: float = 3.0  # 3 min per hour for traffic
    ROAD_ADDITIVE_PER_HOUR: float = 1.5     # 1.5 min per hour for road issues
    
    # Multiplicative factor bounds
    MAX_MULTIPLICATIVE_FACTOR: float = 1.4  # Maximum 1.4x multiplier
    MIN_MULTIPLICATIVE_FACTOR: float = 0.8  # Minimum 0.8x multiplier
    
    # Diminishing returns parameters
    DIMINISHING_RETURNS_FACTOR: float = 0.7  # 70% of previous effect for each additional factor
    
    # Context weighting factors
    NIGHT_WEATHER_WEIGHT: float = 1.3       # Weather impacts 30% more at night
    URBAN_ROAD_WEIGHT: float = 1.2          # Road issues impact 20% more in urban areas
    PEAK_TIME_WEIGHT: float = 1.15          # Peak time amplifies other factors by 15%


class NormalizedETAModel:
    """
    Duration-aware, normalized ETA adjustment model that prevents runaway inflation
    on long trips while maintaining sensitivity for short trips.
    """
    
    def __init__(self, config: Optional[ETAConfig] = None):
        self.config = config or ETAConfig()
        
        # Base condition severity mappings
        self.condition_severity = {
            "weather": {
                "clear": 0,      # No impact
                "cloudy": 1,     # Light
                "rain": 2,       # Moderate
                "storm": 3,      # Heavy
                "snow": 3        # Heavy
            },
            "time_of_day": {
                "night": 0,      # No impact (actually beneficial)
                "morning_peak": 2,  # Moderate
                "midday": 0,     # No impact
                "evening_peak": 2   # Moderate
            },
            "day_type": {
                "weekday": 1,    # Light
                "weekend": 0,    # No impact
                "holiday": 1     # Light
            },
            "road_problem": {
                "none": 0,       # No impact
                "accident": 3,   # Heavy
                "construction": 2,  # Moderate
                "closure": 3     # Heavy
            },
            "police_activity": {
                "low": 0,        # No impact
                "medium": 1,     # Light
                "high": 2        # Moderate
            },
            "driving_history": {
                "calm": 0,       # No impact (actually beneficial)
                "normal": 0,     # No impact
                "aggressive": 1  # Light
            }
        }
        
        # Base impact values (before duration scaling)
        self.base_impacts = {
            "weather": {
                "clear": 0.0, "cloudy": 0.05, "rain": 0.15, "storm": 0.25, "snow": 0.30
            },
            "time_of_day": {
                "night": -0.05, "morning_peak": 0.20, "midday": 0.0, "evening_peak": 0.22
            },
            "day_type": {
                "weekday": 0.08, "weekend": -0.03, "holiday": 0.12
            },
            "road_problem": {
                "none": 0.0, "accident": 0.35, "construction": 0.20, "closure": 0.45
            },
            "police_activity": {
                "low": 0.0, "medium": 0.05, "high": 0.10
            },
            "driving_history": {
                "calm": -0.05, "normal": 0.0, "aggressive": -0.08  # Aggressive driving reduces time
            }
        }
    
    def calculate_normalized_eta(
        self, 
        base_minutes: float,
        conditions: Dict[str, str],
        traffic_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculate normalized ETA adjustment that prevents runaway inflation on long trips.
        
        Args:
            base_minutes: Baseline travel time in minutes
            conditions: Dictionary of condition values (weather, time_of_day, etc.)
            
        Returns:
            Dictionary with adjusted_minutes, multiplier, breakdown, and analysis
        """
        
        # Step 1: Calculate raw condition impacts
        raw_impacts = self._calculate_raw_impacts(conditions)
        
        # Step 1.5: Integrate live traffic data if available
        traffic_available = traffic_data and traffic_data.get('live_traffic_enabled', False)
        if traffic_available:
            traffic_impact = self._calculate_traffic_impact(traffic_data)
            raw_impacts['live_traffic'] = traffic_impact
            
            # Normalize manual variables when live traffic is available
            # Reduce the impact of manual settings since we have real-time data
            for key in raw_impacts:
                if key != 'live_traffic':
                    raw_impacts[key] *= 0.3  # Reduce manual variable impact by 70%
        
        # Step 2: Apply duration-aware scaling
        scaled_impacts = self._apply_duration_scaling(base_minutes, raw_impacts)
        
        # Step 3: Apply diminishing returns for multiple conditions
        combined_impact = self._apply_diminishing_returns(scaled_impacts)
        
        # Step 4: Calculate additive penalties (per-hour delays)
        additive_penalty = self._calculate_additive_penalty(base_minutes, conditions)
        
        # Step 5: Apply severity-based caps
        final_multiplier = self._apply_severity_caps(
            base_minutes, combined_impact, additive_penalty
        )
        
        # Step 6: Calculate final adjusted time
        adjusted_minutes = base_minutes * final_multiplier
        
        # Step 7: Generate detailed breakdown
        breakdown = self._generate_breakdown(
            base_minutes, conditions, raw_impacts, scaled_impacts, 
            combined_impact, additive_penalty, final_multiplier, adjusted_minutes
        )
        
        return {
            "base_minutes": base_minutes,
            "adjusted_minutes": adjusted_minutes,
            "multiplier": final_multiplier,
            "total_inflation_percent": (final_multiplier - 1.0) * 100,
            "additive_penalty_minutes": additive_penalty,
            "breakdown": breakdown,
            "model_type": "normalized_duration_aware",
            "traffic_integration": traffic_data is not None
        }
    
    def _calculate_traffic_impact(self, traffic_data: Dict[str, Any]) -> float:
        """
        Calculate traffic impact from live traffic data with enhanced weighting.
        
        Args:
            traffic_data: Traffic data from provider
            
        Returns:
            Traffic impact value (0.0 = no impact, >0.0 = delay)
        """
        # Enhanced base impact from jam factor (increased weight)
        jam_factor = traffic_data.get('jam_factor', 0.0)
        base_impact = jam_factor * 0.8  # Increased from 0.4 to 0.8 (max 80% impact)
        
        # Enhanced incident impact (increased weight)
        incident_count = traffic_data.get('incident_count', 0)
        incident_impact = min(0.4, incident_count * 0.1)  # Increased from 0.05 to 0.1 (max 40%)
        
        # Enhanced speed impact (increased weight)
        average_speed = traffic_data.get('average_speed_kmh', 60.0)
        speed_impact = 0.0
        if average_speed < 60:
            speed_ratio = average_speed / 60.0
            speed_impact = (1.0 - speed_ratio) * 0.6  # Increased from 0.3 to 0.6 (max 60%)
        
        # Combine impacts with enhanced weighting
        total_impact = base_impact + incident_impact + speed_impact
        
        # Apply enhanced bounds (increased maximum impact)
        return max(0.0, min(1.2, total_impact))  # Increased from 0.6 to 1.2 (max 120% total traffic impact)
    
    def _calculate_raw_impacts(self, conditions: Dict[str, str]) -> Dict[str, float]:
        """Calculate raw impact values for each condition"""
        impacts = {}
        
        for condition_type, value in conditions.items():
            if condition_type in self.base_impacts and value in self.base_impacts[condition_type]:
                base_impact = self.base_impacts[condition_type][value]
                
                # Apply context weighting
                weighted_impact = self._apply_context_weighting(
                    condition_type, value, base_impact, conditions
                )
                
                impacts[condition_type] = weighted_impact
        
        return impacts
    
    def _apply_context_weighting(
        self, 
        condition_type: str, 
        value: str, 
        base_impact: float, 
        all_conditions: Dict[str, str]
    ) -> float:
        """Apply context-aware weighting to condition impacts"""
        
        weighted_impact = base_impact
        
        # Night weather weighting
        if (condition_type == "weather" and 
            all_conditions.get("time_of_day") == "night" and 
            base_impact > 0):
            weighted_impact *= self.config.NIGHT_WEATHER_WEIGHT
        
        # Urban road weighting (assume construction/accidents impact more in urban areas)
        if (condition_type == "road_problem" and 
            value in ["construction", "accident"] and
            all_conditions.get("time_of_day") in ["morning_peak", "evening_peak"]):
            weighted_impact *= self.config.URBAN_ROAD_WEIGHT
        
        # Peak time amplification
        if (all_conditions.get("time_of_day") in ["morning_peak", "evening_peak"] and
            condition_type != "time_of_day" and base_impact > 0):
            weighted_impact *= self.config.PEAK_TIME_WEIGHT
        
        return weighted_impact
    
    def _apply_duration_scaling(
        self, 
        base_minutes: float, 
        raw_impacts: Dict[str, float]
    ) -> Dict[str, float]:
        """Apply duration-aware scaling to condition impacts"""
        
        scaled_impacts = {}
        
        for condition_type, impact in raw_impacts.items():
            if base_minutes <= self.config.SHORT_TRIP_THRESHOLD:
                # Short trips: full impact
                scaling_factor = 1.0
            elif base_minutes <= self.config.MEDIUM_TRIP_THRESHOLD:
                # Medium trips: moderate dampening
                progress = (base_minutes - self.config.SHORT_TRIP_THRESHOLD) / (
                    self.config.MEDIUM_TRIP_THRESHOLD - self.config.SHORT_TRIP_THRESHOLD
                )
                scaling_factor = (self.config.SHORT_TO_MEDIUM_SLOPE + 
                                (1.0 - self.config.SHORT_TO_MEDIUM_SLOPE) * progress)
            else:
                # Long trips: heavy dampening
                progress = min(1.0, (base_minutes - self.config.MEDIUM_TRIP_THRESHOLD) / 
                             (self.config.LONG_TRIP_THRESHOLD - self.config.MEDIUM_TRIP_THRESHOLD))
                scaling_factor = (self.config.MEDIUM_TO_LONG_SLOPE + 
                                (self.config.SHORT_TO_MEDIUM_SLOPE - self.config.MEDIUM_TO_LONG_SLOPE) * 
                                (1.0 - progress))
            
            scaled_impacts[condition_type] = impact * scaling_factor
        
        return scaled_impacts
    
    def _apply_diminishing_returns(self, scaled_impacts: Dict[str, float]) -> float:
        """Apply diminishing returns when combining multiple conditions"""
        
        if not scaled_impacts:
            return 0.0
        
        # Sort impacts by magnitude (largest first)
        sorted_impacts = sorted(scaled_impacts.values(), key=abs, reverse=True)
        
        # First impact gets full weight, subsequent ones get diminishing returns
        total_impact = sorted_impacts[0]
        
        for i, impact in enumerate(sorted_impacts[1:], 1):
            diminishing_factor = self.config.DIMINISHING_RETURNS_FACTOR ** i
            total_impact += impact * diminishing_factor
        
        return total_impact
    
    def _calculate_additive_penalty(self, base_minutes: float, conditions: Dict[str, str]) -> float:
        """Calculate additive time penalties (per-hour delays)"""
        
        total_additive = 0.0
        
        # Weather additive penalty
        weather = conditions.get("weather", "clear")
        if weather in ["rain", "storm", "snow"]:
            hours = base_minutes / 60.0
            total_additive += self.config.WEATHER_ADDITIVE_PER_HOUR * hours
        
        # Traffic additive penalty
        time_of_day = conditions.get("time_of_day", "midday")
        if time_of_day in ["morning_peak", "evening_peak"]:
            hours = base_minutes / 60.0
            total_additive += self.config.TRAFFIC_ADDITIVE_PER_HOUR * hours
        
        # Road problem additive penalty
        road_problem = conditions.get("road_problem", "none")
        if road_problem in ["construction", "accident"]:
            hours = base_minutes / 60.0
            total_additive += self.config.ROAD_ADDITIVE_PER_HOUR * hours
        
        return total_additive
    
    def _apply_severity_caps(
        self, 
        base_minutes: float, 
        combined_impact: float, 
        additive_penalty: float
    ) -> float:
        """Apply severity-based caps to prevent runaway inflation"""
        
        # Calculate total inflation percentage
        total_inflation = combined_impact + (additive_penalty / base_minutes)
        
        # Determine severity band based on total impact
        if abs(total_inflation) <= 0.20:
            severity_cap = self.config.LIGHT_SEVERITY_CAP
        elif abs(total_inflation) <= 0.40:
            severity_cap = self.config.MODERATE_SEVERITY_CAP
        else:
            severity_cap = self.config.HEAVY_SEVERITY_CAP
        
        # Apply cap
        capped_inflation = max(-severity_cap, min(severity_cap, total_inflation))
        
        # Convert to multiplier
        multiplier = 1.0 + capped_inflation
        
        # Apply final bounds
        multiplier = max(self.config.MIN_MULTIPLICATIVE_FACTOR, 
                        min(self.config.MAX_MULTIPLICATIVE_FACTOR, multiplier))
        
        return multiplier
    
    def _generate_breakdown(
        self, 
        base_minutes: float,
        conditions: Dict[str, str],
        raw_impacts: Dict[str, float],
        scaled_impacts: Dict[str, float],
        combined_impact: float,
        additive_penalty: float,
        final_multiplier: float,
        adjusted_minutes: float
    ) -> Dict[str, Any]:
        """Generate detailed breakdown of the ETA calculation"""
        
        # Calculate individual contributions
        contributions = []
        for condition_type, value in conditions.items():
            if condition_type in raw_impacts:
                raw_impact = raw_impacts[condition_type]
                scaled_impact = scaled_impacts.get(condition_type, 0.0)
                
                contributions.append({
                    "factor": condition_type,
                    "value": value,
                    "raw_impact": round(raw_impact, 4),
                    "scaled_impact": round(scaled_impact, 4),
                    "contribution_percent": round(scaled_impact * 100, 2)
                })
        
        # Duration analysis
        duration_analysis = {
            "trip_category": self._categorize_trip_duration(base_minutes),
            "scaling_factor": self._calculate_overall_scaling_factor(base_minutes),
            "dampening_applied": base_minutes > self.config.SHORT_TRIP_THRESHOLD
        }
        
        # Cap analysis
        cap_analysis = {
            "severity_band": self._determine_severity_band(combined_impact, additive_penalty, base_minutes),
            "cap_applied": self._was_cap_applied(combined_impact, additive_penalty, base_minutes),
            "total_inflation_before_cap": round((combined_impact + additive_penalty / base_minutes) * 100, 2)
        }
        
        return {
            "contributions": contributions,
            "duration_analysis": duration_analysis,
            "cap_analysis": cap_analysis,
            "additive_penalty_analysis": {
                "total_additive_minutes": round(additive_penalty, 2),
                "additive_per_hour": round(additive_penalty / (base_minutes / 60.0), 2) if base_minutes > 0 else 0
            },
            "final_calculation": {
                "base_time": base_minutes,
                "impact_multiplier": round(1.0 + combined_impact, 4),
                "additive_penalty": additive_penalty,
                "final_multiplier": final_multiplier,
                "adjusted_time": adjusted_minutes
            }
        }
    
    def _categorize_trip_duration(self, base_minutes: float) -> str:
        """Categorize trip duration for analysis"""
        if base_minutes <= self.config.SHORT_TRIP_THRESHOLD:
            return "short"
        elif base_minutes <= self.config.MEDIUM_TRIP_THRESHOLD:
            return "medium"
        else:
            return "long"
    
    def _calculate_overall_scaling_factor(self, base_minutes: float) -> float:
        """Calculate overall scaling factor applied to conditions"""
        if base_minutes <= self.config.SHORT_TRIP_THRESHOLD:
            return 1.0
        elif base_minutes <= self.config.MEDIUM_TRIP_THRESHOLD:
            return self.config.SHORT_TO_MEDIUM_SLOPE
        else:
            return self.config.MEDIUM_TO_LONG_SLOPE
    
    def _determine_severity_band(self, combined_impact: float, additive_penalty: float, base_minutes: float) -> str:
        """Determine severity band based on total impact"""
        total_inflation = abs(combined_impact + (additive_penalty / base_minutes))
        
        if total_inflation <= 0.20:
            return "light"
        elif total_inflation <= 0.40:
            return "moderate"
        else:
            return "heavy"
    
    def _was_cap_applied(self, combined_impact: float, additive_penalty: float, base_minutes: float) -> bool:
        """Check if severity cap was applied"""
        total_inflation = abs(combined_impact + (additive_penalty / base_minutes))
        
        if total_inflation <= 0.15:
            return total_inflation > self.config.LIGHT_SEVERITY_CAP
        elif total_inflation <= 0.30:
            return total_inflation > self.config.MODERATE_SEVERITY_CAP
        else:
            return total_inflation > self.config.HEAVY_SEVERITY_CAP


# API compatibility functions (drop-in replacement for existing models)
def predict_travel_multiplier(
    weather: str,
    time_of_day: str,
    day_type: str,
    road_problem: str,
    police_activity: str,
    driving_history: str,
    base_minutes: float = 60.0  # Default to 1 hour for backward compatibility
) -> float:
    """Normalized version of predict_travel_multiplier with duration awareness"""
    model = NormalizedETAModel()
    conditions = {
        "weather": weather,
        "time_of_day": time_of_day,
        "day_type": day_type,
        "road_problem": road_problem,
        "police_activity": police_activity,
        "driving_history": driving_history,
    }
    
    result = model.calculate_normalized_eta(base_minutes, conditions)
    return result["multiplier"]


def predict_travel_with_details(
    weather: str,
    time_of_day: str,
    day_type: str,
    road_problem: str,
    police_activity: str,
    driving_history: str,
    base_minutes: float = 60.0,  # Default to 1 hour for backward compatibility
    traffic_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Normalized version of predict_travel_with_details with duration awareness"""
    model = NormalizedETAModel()
    conditions = {
        "weather": weather,
        "time_of_day": time_of_day,
        "day_type": day_type,
        "road_problem": road_problem,
        "police_activity": police_activity,
        "driving_history": driving_history,
    }
    
    result = model.calculate_normalized_eta(base_minutes, conditions, traffic_data)
    
    # Convert to expected format for backward compatibility
    rows = []
    for contrib in result["breakdown"]["contributions"]:
        rows.append({
            "factor": contrib["factor"],
            "value": contrib["value"],
            "weight": contrib["raw_impact"],
            "contribution": contrib["scaled_impact"]
        })
    
    # Generate marginals based on final multiplier
    multiplier = result["multiplier"]
    if multiplier < 1.2:
        traffic = "light"
        cond = "good"
        route_bias = "shortest"
    elif multiplier < 1.6:
        traffic = "moderate"
        cond = "mixed"
        route_bias = "balanced"
    else:
        traffic = "heavy"
        cond = "bad"
        route_bias = "fastest"
    
    marginals = {
        "traffic": {"top": traffic, "dist": {"light": 0.3, "moderate": 0.4, "heavy": 0.3}},
        "conditions_severity": {"top": cond, "dist": {"good": 0.4, "mixed": 0.4, "bad": 0.2}},
        "route_choice": {"top": "main_roads", "dist": {"main_roads": 0.7, "shortcuts": 0.3}},
        "route_bias": {"top": route_bias, "dist": {"shortest": 0.3, "balanced": 0.4, "fastest": 0.3}},
    }
    
    return {
        "multiplier": multiplier,
        "rows": rows,
        "marginals": marginals,
        "model_type": "normalized_duration_aware",
        "normalized_details": result
    }


if __name__ == "__main__":
    # Test the normalized model
    print("🧠 Testing Normalized ETA Model")
    print("=" * 50)
    
    model = NormalizedETAModel()
    
    # Test cases with different durations
    test_cases = [
        # (name, base_minutes, conditions)
        ("Short trip - Clear day", 20, {
            "weather": "clear", "time_of_day": "midday", "day_type": "weekend",
            "road_problem": "none", "police_activity": "low", "driving_history": "calm"
        }),
        ("Short trip - Rainy rush hour", 25, {
            "weather": "rain", "time_of_day": "morning_peak", "day_type": "weekday",
            "road_problem": "none", "police_activity": "low", "driving_history": "normal"
        }),
        ("Medium trip - Storm with accident", 90, {
            "weather": "storm", "time_of_day": "evening_peak", "day_type": "weekday",
            "road_problem": "accident", "police_activity": "high", "driving_history": "aggressive"
        }),
        ("Long trip - Heavy conditions", 300, {
            "weather": "snow", "time_of_day": "night", "day_type": "holiday",
            "road_problem": "construction", "police_activity": "medium", "driving_history": "calm"
        }),
        ("Very long trip - Worst case", 480, {
            "weather": "storm", "time_of_day": "morning_peak", "day_type": "weekday",
            "road_problem": "accident", "police_activity": "high", "driving_history": "aggressive"
        })
    ]
    
    print("Testing predictions with duration awareness:")
    print()
    
    for name, base_minutes, conditions in test_cases:
        result = model.calculate_normalized_eta(base_minutes, conditions)
        
        print(f"📊 {name}")
        print(f"   Base time: {base_minutes} minutes")
        print(f"   Final multiplier: {result['multiplier']:.3f}")
        print(f"   Adjusted time: {result['adjusted_minutes']:.1f} minutes")
        print(f"   Total inflation: {result['total_inflation_percent']:.1f}%")
        print(f"   Trip category: {result['breakdown']['duration_analysis']['trip_category']}")
        print(f"   Severity band: {result['breakdown']['cap_analysis']['severity_band']}")
        print()
    
    print("✅ Normalized ETA model test completed!")
    print("   Short trips get stronger effects, long trips get dampened")
    print("   Hard caps prevent runaway inflation")
    print("   Diminishing returns for multiple conditions")
