# tests/api_tests/test_utils.py
"""Unit tests for src/api/utils.py utility functions."""

import pytest
from src.api.utils import parse_time_horizon, score_to_category


# ---------------------------------------------------------------------------
# parse_time_horizon
# ---------------------------------------------------------------------------

class TestParseTimeHorizon:
    """Tests for parse_time_horizon()."""

    # -- range strings -------------------------------------------------------

    def test_range_returns_midpoint(self):
        assert parse_time_horizon("2041-2060") == 2050

    def test_range_odd_midpoint_truncates(self):
        # (2020 + 2039) / 2 = 2029.5 → truncated to 2029
        assert parse_time_horizon("2020-2039") == 2029

    def test_range_same_start_end(self):
        assert parse_time_horizon("2050-2050") == 2050

    def test_range_near_term(self):
        assert parse_time_horizon("2021-2040") == 2030

    def test_range_far_future(self):
        assert parse_time_horizon("2080-2100") == 2090

    # -- plain year strings --------------------------------------------------

    def test_plain_year_string(self):
        assert parse_time_horizon("2050") == 2050

    def test_plain_year_string_2030(self):
        assert parse_time_horizon("2030") == 2030

    # -- fallback behaviours -------------------------------------------------

    def test_empty_string_returns_fallback(self):
        assert parse_time_horizon("", fallback=2050) == 2050

    def test_non_numeric_returns_fallback(self):
        assert parse_time_horizon("future", fallback=2050) == 2050

    def test_partial_range_non_numeric_returns_fallback(self):
        # 'now-2060' cannot be parsed as int
        assert parse_time_horizon("now-2060", fallback=2050) == 2050

    def test_custom_fallback_value_used(self):
        assert parse_time_horizon("bad-input", fallback=2035) == 2035

    def test_default_fallback_is_2050(self):
        # Confirm the signature default without passing fallback explicitly
        assert parse_time_horizon("garbage") == 2050

    def test_range_with_whitespace_returns_fallback(self):
        # '2041 - 2060' splits into ['2041 ', ' 2060'], int() strips ok
        # Python int() handles surrounding whitespace, so this should parse
        assert parse_time_horizon("2041 - 2060") == 2050


# ---------------------------------------------------------------------------
# score_to_category
# ---------------------------------------------------------------------------

class TestScoreToCategory:
    """Tests for score_to_category()."""

    # -- boundary checks (boundary is exclusive on the upper side) -----------

    def test_zero_is_low(self):
        assert score_to_category(0.0) == "Low"

    def test_just_below_0_2_is_low(self):
        assert score_to_category(0.199) == "Low"

    def test_exactly_0_2_is_moderate(self):
        assert score_to_category(0.2) == "Moderate"

    def test_midpoint_moderate(self):
        assert score_to_category(0.3) == "Moderate"

    def test_just_below_0_4_is_moderate(self):
        assert score_to_category(0.399) == "Moderate"

    def test_exactly_0_4_is_high(self):
        assert score_to_category(0.4) == "High"

    def test_midpoint_high(self):
        assert score_to_category(0.5) == "High"

    def test_just_below_0_6_is_high(self):
        assert score_to_category(0.599) == "High"

    def test_exactly_0_6_is_very_high(self):
        assert score_to_category(0.6) == "Very High"

    def test_midpoint_very_high(self):
        assert score_to_category(0.7) == "Very High"

    def test_just_below_0_8_is_very_high(self):
        assert score_to_category(0.799) == "Very High"

    def test_exactly_0_8_is_extreme(self):
        assert score_to_category(0.8) == "Extreme"

    def test_one_is_extreme(self):
        assert score_to_category(1.0) == "Extreme"

    def test_above_one_is_extreme(self):
        # Scores > 1.0 should still return "Extreme"
        assert score_to_category(1.5) == "Extreme"

    # -- qualitative spot checks ---------------------------------------------

    def test_zero_risk_is_low(self):
        assert score_to_category(0.0) == "Low"

    def test_half_risk_is_high(self):
        assert score_to_category(0.5) == "High"

    def test_full_risk_is_extreme(self):
        assert score_to_category(1.0) == "Extreme"
