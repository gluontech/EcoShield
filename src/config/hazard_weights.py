
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Path to the YAML file
WEIGHTS_FILE = Path(__file__).parent / "hazard_weights.yaml"

def load_hazard_weights() -> Dict[str, Any]:
    """Load hazard weights from YAML file."""
    if not WEIGHTS_FILE.exists():
        logger.warning(f"Hazard weights file not found at {WEIGHTS_FILE}. Using defaults.")
        return {}
        
    try:
        with open(WEIGHTS_FILE, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load hazard weights: {e}")
        return {}

HAZARD_WEIGHTS = load_hazard_weights()

def load_city_weights(city: str) -> Dict[str, Dict[str, float]]:
    """
    Get acute and chronic weights for a specific city.
    Falls back to 'default' if city not found.
    """
    city_key = city.lower()
    
    # Try direct match
    if city_key in HAZARD_WEIGHTS:
        return HAZARD_WEIGHTS[city_key]
        
    # Try default
    if "default" in HAZARD_WEIGHTS:
        return HAZARD_WEIGHTS["default"]
        
    # Fallback hardcoded defaults (MVP)
    return {
        "acute": {},
        "chronic": {}
    }
