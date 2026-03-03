import sys
import os
sys.path.append('/home/bim/code/EcoShield')
from src.data.spatial_matcher import SpatialMatcher, SpatialMatchContext
from src.core.models.enums import StructureCategory, StructureType

ctx = SpatialMatchContext(name="Crescent Mall", address="101 Tôn Dật Tiên", structure_category=StructureCategory.COMMERCIAL, structure_type=StructureType.SHOPPING_MALL)

# Just testing if imports work
print("Matcher imported")
