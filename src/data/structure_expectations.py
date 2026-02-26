# src/data/structure_expectations.py
"""
Expected physical characteristics per StructureType.

Used by the spatial matcher QA step to reject implausible building matches.
Ranges are SEA-calibrated — Vietnamese tube houses, Indonesian kampung,
Thai shophouses, Philippine informal settlements, Singapore HDB blocks.

Each entry defines the plausible range for area, height, and floor count.
A candidate building that falls outside these ranges is flagged as a
mismatch and triggers a retry with expanded search buffer.

Adaptive Reuse (CONVERTED_* types):
    In dense SEA historic quarters, residential structures are commonly
    converted to commercial use without changing the physical envelope:
    - Hanoi Old Quarter (Hoàn Kiếm): tube houses → boutique hotels, cafés
    - HCMC District 1/3: villas → restaurants, galleries
    - Hội An ancient town: shophouses → hotels, tailor shops
    - Bangkok Chinatown (Yaowarat): shophouses → hostels
    - Manila Intramuros: heritage houses → hotels
    - Jakarta Kota Tua: warehouses → cafés, co-working

    For these types, spatial QA uses the PHYSICAL form (tube house envelope)
    while vulnerability/value assessment uses the FUNCTION (commercial).
    Regional override zones further loosen plausibility thresholds in known
    conversion-heavy areas.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.core.models.enums import (
    StructureCategory,
    StructureType,
    BuildingOccupancy,
)


@dataclass(frozen=True)
class StructureExpectation:
    """Expected physical range for a structure type."""
    category: StructureCategory
    min_area_m2: float
    max_area_m2: float
    min_height_m: float
    max_height_m: float
    min_floors: int
    max_floors: int
    expected_occupancy: BuildingOccupancy

    def area_plausible(self, area_m2: float) -> bool:
        return self.min_area_m2 <= area_m2 <= self.max_area_m2

    def height_plausible(self, height_m: float) -> bool:
        return self.min_height_m <= height_m <= self.max_height_m

    def floors_plausible(self, floors: int) -> bool:
        return self.min_floors <= floors <= self.max_floors

    def plausibility_score(
        self,
        area_m2: Optional[float] = None,
        height_m: Optional[float] = None,
        floors: Optional[int] = None,
    ) -> float:
        """Return 0.0–1.0 indicating how well the candidate fits expectations.

        Each available dimension contributes equally.  A value within the
        expected range scores 1.0; outside scores a decay based on distance
        from the nearest bound.
        """
        scores = []

        if area_m2 is not None and area_m2 > 0:
            if self.area_plausible(area_m2):
                scores.append(1.0)
            else:
                dist = min(
                    abs(area_m2 - self.min_area_m2),
                    abs(area_m2 - self.max_area_m2),
                )
                span = self.max_area_m2 - self.min_area_m2
                scores.append(max(0.0, 1.0 - dist / max(span, 1.0)))

        if height_m is not None and height_m > 0:
            if self.height_plausible(height_m):
                scores.append(1.0)
            else:
                dist = min(
                    abs(height_m - self.min_height_m),
                    abs(height_m - self.max_height_m),
                )
                span = self.max_height_m - self.min_height_m
                scores.append(max(0.0, 1.0 - dist / max(span, 1.0)))

        if floors is not None and floors > 0:
            if self.floors_plausible(floors):
                scores.append(1.0)
            else:
                dist = min(
                    abs(floors - self.min_floors),
                    abs(floors - self.max_floors),
                )
                span = self.max_floors - self.min_floors
                scores.append(max(0.0, 1.0 - dist / max(span, 1)))

        if not scores:
            return 0.5  # no data — neutral

        return sum(scores) / len(scores)


# ── Residential ──────────────────────────────────────────────

STRUCTURE_EXPECTATIONS: Dict[StructureType, StructureExpectation] = {
    StructureType.TUBE_HOUSE: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=15, max_area_m2=80,
        min_height_m=9, max_height_m=18,
        min_floors=3, max_floors=6,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_SINGLE,
    ),
    StructureType.SINGLE_DWELLING: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=30, max_area_m2=300,
        min_height_m=3, max_height_m=12,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_SINGLE,
    ),
    StructureType.MULTISTORY_DWELLING: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=80, max_area_m2=500,
        min_height_m=9, max_height_m=21,
        min_floors=3, max_floors=7,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_MULTI,
    ),
    StructureType.APARTMENT_BUILDING: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=500, max_area_m2=15000,
        min_height_m=15, max_height_m=100,
        min_floors=5, max_floors=35,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_MULTI,
    ),
    StructureType.INFORMAL_SETTLEMENT: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=5, max_area_m2=50,
        min_height_m=2, max_height_m=6,
        min_floors=1, max_floors=2,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_INFORMAL,
    ),

    # ── Commercial ───────────────────────────────────────────

    StructureType.HOTEL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=200, max_area_m2=50000,
        min_height_m=10, max_height_m=200,
        min_floors=3, max_floors=60,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.SHOPPING_MALL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=1000, max_area_m2=100000,
        min_height_m=6, max_height_m=30,
        min_floors=1, max_floors=6,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.BANK: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=100, max_area_m2=5000,
        min_height_m=6, max_height_m=30,
        min_floors=2, max_floors=10,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.GYM: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=100, max_area_m2=3000,
        min_height_m=4, max_height_m=15,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.OFFICE_BUILDING: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=200, max_area_m2=20000,
        min_height_m=10, max_height_m=150,
        min_floors=3, max_floors=40,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.RETAIL_SHOP: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=20, max_area_m2=500,
        min_height_m=3, max_height_m=12,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.RESTAURANT: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=30, max_area_m2=1000,
        min_height_m=3, max_height_m=12,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),

    # ── Industrial ───────────────────────────────────────────

    StructureType.FACTORY: StructureExpectation(
        category=StructureCategory.INDUSTRIAL,
        min_area_m2=500, max_area_m2=50000,
        min_height_m=6, max_height_m=20,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.INDUSTRIAL,
    ),
    StructureType.WAREHOUSE: StructureExpectation(
        category=StructureCategory.INDUSTRIAL,
        min_area_m2=200, max_area_m2=30000,
        min_height_m=5, max_height_m=15,
        min_floors=1, max_floors=2,
        expected_occupancy=BuildingOccupancy.INDUSTRIAL,
    ),

    # ── Adaptive Reuse (CONVERTED_*) ────────────────────────
    # Physical form = residential/industrial envelope.
    # Function = commercial (occupancy is COMMERCIAL for vulnerability/value).

    StructureType.CONVERTED_TUBE_HOUSE_HOTEL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=15, max_area_m2=80,      # tube house physical envelope
        min_height_m=9, max_height_m=21,      # often add rooftop floor
        min_floors=3, max_floors=7,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_TUBE_HOUSE_SHOP: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=15, max_area_m2=80,
        min_height_m=9, max_height_m=18,
        min_floors=3, max_floors=6,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_TUBE_HOUSE_RESTAURANT: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=15, max_area_m2=80,
        min_height_m=9, max_height_m=18,
        min_floors=3, max_floors=6,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_VILLA_HOTEL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=100, max_area_m2=500,     # colonial/French villa envelope
        min_height_m=6, max_height_m=15,
        min_floors=2, max_floors=4,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_VILLA_RESTAURANT: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=100, max_area_m2=500,
        min_height_m=6, max_height_m=15,
        min_floors=2, max_floors=4,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_SHOPHOUSE_HOTEL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=30, max_area_m2=150,      # Thai/Chinese shophouse
        min_height_m=6, max_height_m=15,
        min_floors=2, max_floors=4,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureType.CONVERTED_WAREHOUSE_COMMERCIAL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=200, max_area_m2=30000,   # warehouse envelope
        min_height_m=5, max_height_m=15,
        min_floors=1, max_floors=2,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
}


# ── Adaptive Reuse Override Zones ───────────────────────────
# In these bounding boxes, the spatial matcher QA step loosens
# plausibility thresholds for commercial types that would normally
# fail against small residential footprints.
#
# Format: (name, min_lat, max_lat, min_lon, max_lon, loosened_types)
# The matcher multiplies the plausibility_score by a leniency factor
# (1.5x) when the query point falls inside one of these zones AND the
# declared structure_type is a pure commercial type (not CONVERTED_*).

@dataclass(frozen=True)
class AdaptiveReuseZone:
    """Geographic zone where commercial-in-residential conversion is common."""
    name: str
    city: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    leniency_factor: float  # multiply plausibility_score by this in the zone

    def contains(self, lat: float, lon: float) -> bool:
        return (self.min_lat <= lat <= self.max_lat
                and self.min_lon <= lon <= self.max_lon)


ADAPTIVE_REUSE_ZONES: List[AdaptiveReuseZone] = [
    # Vietnam
    AdaptiveReuseZone(
        name="Hanoi Old Quarter (Hoàn Kiếm)",
        city="hanoi",
        min_lat=21.028, max_lat=21.040,
        min_lon=105.847, max_lon=105.858,
        leniency_factor=1.5,
    ),
    AdaptiveReuseZone(
        name="Hội An Ancient Town",
        city="danang",  # nearest supported city
        min_lat=15.875, max_lat=15.885,
        min_lon=108.325, max_lon=108.340,
        leniency_factor=1.5,
    ),
    AdaptiveReuseZone(
        name="HCMC District 1 backpacker area (Bùi Viện / Phạm Ngũ Lão)",
        city="hcmc",
        min_lat=10.766, max_lat=10.772,
        min_lon=106.690, max_lon=106.698,
        leniency_factor=1.5,
    ),
    AdaptiveReuseZone(
        name="HCMC District 3 villa quarter",
        city="hcmc",
        min_lat=10.776, max_lat=10.790,
        min_lon=106.676, max_lon=106.692,
        leniency_factor=1.4,
    ),
    # Thailand
    AdaptiveReuseZone(
        name="Bangkok Chinatown (Yaowarat)",
        city="bangkok",
        min_lat=13.735, max_lat=13.745,
        min_lon=100.505, max_lon=100.515,
        leniency_factor=1.5,
    ),
    AdaptiveReuseZone(
        name="Bangkok Khao San Road area",
        city="bangkok",
        min_lat=13.757, max_lat=13.766,
        min_lon=100.494, max_lon=100.502,
        leniency_factor=1.4,
    ),
    # Philippines
    AdaptiveReuseZone(
        name="Manila Intramuros",
        city="manila",
        min_lat=14.587, max_lat=14.596,
        min_lon=120.970, max_lon=120.980,
        leniency_factor=1.4,
    ),
    # Indonesia
    AdaptiveReuseZone(
        name="Jakarta Kota Tua (Old Town)",
        city="jakarta",
        min_lat=-6.138, max_lat=-6.128,
        min_lon=106.808, max_lon=106.818,
        leniency_factor=1.4,
    ),
]


def get_zone_leniency(lat: float, lon: float) -> float:
    """Return the leniency multiplier for a given point.

    Returns 1.0 (no leniency) if the point is not in any override zone.
    If inside multiple zones, returns the highest leniency factor.
    """
    max_leniency = 1.0
    for zone in ADAPTIVE_REUSE_ZONES:
        if zone.contains(lat, lon):
            max_leniency = max(max_leniency, zone.leniency_factor)
    return max_leniency


# ── Category-level fallback ranges ──────────────────────────
# Used when structure_category is provided but structure_type is not.

CATEGORY_EXPECTATIONS: Dict[StructureCategory, StructureExpectation] = {
    StructureCategory.RESIDENTIAL: StructureExpectation(
        category=StructureCategory.RESIDENTIAL,
        min_area_m2=5, max_area_m2=15000,
        min_height_m=2, max_height_m=100,
        min_floors=1, max_floors=35,
        expected_occupancy=BuildingOccupancy.RESIDENTIAL_SINGLE,
    ),
    StructureCategory.COMMERCIAL: StructureExpectation(
        category=StructureCategory.COMMERCIAL,
        min_area_m2=20, max_area_m2=100000,
        min_height_m=3, max_height_m=200,
        min_floors=1, max_floors=60,
        expected_occupancy=BuildingOccupancy.COMMERCIAL,
    ),
    StructureCategory.INDUSTRIAL: StructureExpectation(
        category=StructureCategory.INDUSTRIAL,
        min_area_m2=200, max_area_m2=50000,
        min_height_m=5, max_height_m=20,
        min_floors=1, max_floors=3,
        expected_occupancy=BuildingOccupancy.INDUSTRIAL,
    ),
}


def get_expectation(
    structure_type: Optional[StructureType] = None,
    structure_category: Optional[StructureCategory] = None,
) -> Optional[StructureExpectation]:
    """Resolve the best available expectation for QA validation.

    Prefers structure_type (specific) over structure_category (broad).
    Returns None if neither is provided.
    """
    if structure_type and structure_type in STRUCTURE_EXPECTATIONS:
        return STRUCTURE_EXPECTATIONS[structure_type]
    if structure_category and structure_category in CATEGORY_EXPECTATIONS:
        return CATEGORY_EXPECTATIONS[structure_category]
    return None


# Types whose physical_form differs from their function.
# The spatial matcher uses these to decide which expectation table to query:
# - Spatial QA → uses CONVERTED_* expectation (physical envelope)
# - Vulnerability/value → uses COMMERCIAL occupancy
CONVERTED_TYPES: Dict[StructureType, StructureType] = {
    StructureType.CONVERTED_TUBE_HOUSE_HOTEL: StructureType.TUBE_HOUSE,
    StructureType.CONVERTED_TUBE_HOUSE_SHOP: StructureType.TUBE_HOUSE,
    StructureType.CONVERTED_TUBE_HOUSE_RESTAURANT: StructureType.TUBE_HOUSE,
    StructureType.CONVERTED_VILLA_HOTEL: StructureType.SINGLE_DWELLING,
    StructureType.CONVERTED_VILLA_RESTAURANT: StructureType.SINGLE_DWELLING,
    StructureType.CONVERTED_SHOPHOUSE_HOTEL: StructureType.MULTISTORY_DWELLING,
    StructureType.CONVERTED_WAREHOUSE_COMMERCIAL: StructureType.WAREHOUSE,
}


def is_converted_type(structure_type: Optional[StructureType]) -> bool:
    """Check whether a structure_type represents adaptive reuse."""
    return structure_type is not None and structure_type in CONVERTED_TYPES


def get_physical_form(structure_type: StructureType) -> StructureType:
    """Return the underlying physical form for a converted type.

    For non-converted types, returns the type itself.
    """
    return CONVERTED_TYPES.get(structure_type, structure_type)
