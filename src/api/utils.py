# src/api/utils.py
"""Shared utility functions for EcoShield API routes."""


def parse_time_horizon(time_horizon: str, fallback: int = 2050) -> int:
    """
    Parse a time horizon string to a representative year.

    Accepts either a range ('2041-2060' → midpoint 2050) or a plain year
    string ('2050' → 2050).  Falls back to *fallback* on parse failure.
    """
    try:
        if "-" in time_horizon:
            parts = time_horizon.split("-")
            return int((int(parts[0]) + int(parts[1])) / 2)
        return int(time_horizon)
    except (ValueError, IndexError):
        return fallback


def score_to_category(score: float) -> str:
    """Convert a normalised 0-1 risk score to a human-readable category."""
    if score < 0.2:
        return "Low"
    elif score < 0.4:
        return "Moderate"
    elif score < 0.6:
        return "High"
    elif score < 0.8:
        return "Very High"
    return "Extreme"
