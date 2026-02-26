# src/data/structure_expectations.py
"""
Expected physical characteristics per StructureType.

Used by the spatial matcher QA step to reject implausible building matches.
Ranges are SEA-calibrated — Vietnamese tube houses, Indonesian kampung,
Thai shophouses, Philippine informal settlements, Singapore HDB blocks.

Each entry defines the plausible range for area, height, and floor count.
A candidate building that falls outside these ranges is flagged as a
mismatch and triggers a retry with expanded search buffer.
"""

from dataclasses import dataclass
from typing import Dict, Optional

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
}


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
