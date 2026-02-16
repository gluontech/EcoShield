
"""
City-specific hazard configurations.

v3.0: All SEA target cities supported from day one.
NEX-GDDP-CMIP6 provides global climate projections.

v3.2 (Gap M): Added "pluvial_flood" to acute hazards for urban cities.
Pluvial flooding is the most frequent flood type in SEA; HCMC experiences
20-30+ events per year. Now assessed at multiple return periods.

v3.2 subsidence corrections:
  - Hanoi: Removed from chronic. Central Hanoi subsidence diminishing over
    2007-2018 (Nguyen et al. 2022, Engineering Geology). Localized hotspots
    in peri-urban Ha Dong/Hoai Duc (~50 mm/yr) but city is "relatively less
    affected compared to other SEA cities." Small consolidation coefficients.
  - Bangkok: Removed from chronic. Historic crisis (120 mm/yr peak, 1980s)
    largely mitigated through groundwater pricing, tap water expansion, and
    strict enforcement (Phien-wej et al. 2006). Inner Bangkok now ~0-1 cm/yr
    (Mekong-US Partnership 2020). Neighboring provinces outside assessment
    bounds still subsiding.
  - HCMC: Retained — up to 80 mm/yr, no effective mitigation (World Bank 2015).
  - Jakarta: Retained — up to 250 mm/yr, world's worst (Frontiers 2024).
  - Manila: Retained — max 109 mm/yr Bulacan, 20-42 mm/yr Metro Manila
    (Sulapas et al. 2024). No effective mitigation.
"""

CITY_HAZARDS = {
    # ═══════════════════════════════════════════════
    #  VIETNAM (MVP targets)
    # ═══════════════════════════════════════════════
    "hcmc": {
        "name": "Ho Chi Minh City",
        "country": "VN",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: Severe, up to 80 mm/yr in District 7 (World Bank 2015).
        # Mekong Delta groundwater extraction ongoing; no effective mitigation yet.
        "bounds": {"north": 11.2, "south": 10.4, "east": 107.0, "west": 106.3},
        "tidal_range_m": 3.5,
    },
    "hanoi": {
        "name": "Hanoi",
        "country": "VN",
        "acute": ["riverine_flood", "tropical_cyclone", "landslide",
                  "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["urban_heat"],
        # v3.2: Subsidence removed from chronic. Central Hanoi subsidence has been
        # diminishing (Nguyen et al. 2022, Eng. Geology). Localized hotspots in
        # peri-urban Ha Dong/Hoai Duc (~50 mm/yr) but "Hanoi is relatively less
        # affected by land subsidence compared to other SEA cities" due to small
        # consolidation coefficients and lower population density.
        "bounds": {"north": 21.3, "south": 20.8, "east": 106.0, "west": 105.5},
        "tidal_range_m": 0.0,
    },
    "danang": {
        "name": "Da Nang",
        "country": "VN",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "landslide", "pluvial_flood"],  # v3.2
        "chronic": ["urban_heat"],
        "bounds": {"north": 16.3, "south": 15.8, "east": 108.5, "west": 107.8},
        "tidal_range_m": 1.2,
    },

    # ═══════════════════════════════════════════════
    #  INDONESIA
    # ═══════════════════════════════════════════════
    "jakarta": {
        "name": "Jakarta",
        "country": "ID",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "landslide", "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: World's most severe — up to 250 mm/yr in North Jakarta
        # (Frontiers in Earth Science 2024). Capital relocation to Nusantara
        # partly driven by subsidence. No effective mitigation to date.
        "bounds": {"north": -6.0, "south": -6.5, "east": 107.1, "west": 106.5},
        "tidal_range_m": 1.0,
    },

    # ═══════════════════════════════════════════════
    #  PHILIPPINES
    # ═══════════════════════════════════════════════
    "manila": {
        "name": "Manila",
        "country": "PH",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "tropical_cyclone", "landslide", "pluvial_flood"],  # v3.2
        "chronic": ["subsidence", "urban_heat"],
        # Subsidence: Severe & ongoing — max 109 mm/yr in Bulacan Province,
        # 20-42 mm/yr across Metro Manila (Sulapas et al. 2024, Int. J. Applied
        # Earth Observation). Driven by excessive groundwater extraction; "orders
        # of magnitude more rapid than sea-level rise" (Rodolfo & Siringan 2006).
        "bounds": {"north": 14.8, "south": 14.3, "east": 121.2, "west": 120.8},
        "tidal_range_m": 1.5,
    },

    # ═══════════════════════════════════════════════
    #  THAILAND
    # ═══════════════════════════════════════════════
    "bangkok": {
        "name": "Bangkok",
        "country": "TH",
        "acute": ["riverine_flood", "coastal_flood", "storm_surge",
                  "pluvial_flood"],  # v3.2: + pluvial_flood
        "chronic": ["urban_heat"],
        # v3.2: Subsidence removed from chronic. Bangkok's historic crisis
        # (120 mm/yr peak in 1980s) was largely mitigated through groundwater
        # pricing, tap water expansion, and strict enforcement (Phien-wej et al.
        # 2006; Mekong-US Partnership 2020). Inner Bangkok now ~0-1 cm/yr.
        # Neighboring provinces (Samut Prakan, Ayutthaya) still subsiding but
        # outside EcoShield assessment bounds. Residual consolidation continues
        # but is not a dominant chronic risk for inner Bangkok.
        "bounds": {"north": 14.0, "south": 13.5, "east": 100.8, "west": 100.3},
        "tidal_range_m": 2.5,
    },

    # ═══════════════════════════════════════════════
    #  SINGAPORE
    # ═══════════════════════════════════════════════
    "singapore": {
        "name": "Singapore",
        "country": "SG",
        "acute": ["coastal_flood", "storm_surge",
                  "pluvial_flood"],  # v3.2: + pluvial_flood (common in SG)
        "chronic": ["urban_heat"],
        "bounds": {"north": 1.5, "south": 1.1, "east": 104.1, "west": 103.6},
        "tidal_range_m": 2.8,
    },
}
