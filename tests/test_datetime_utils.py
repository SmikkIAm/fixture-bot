from datetime import datetime, timedelta, timezone

import pytest

from src.utils.datetime_utils import (
    convert_to_local_timezone,
    parse_api_datetime,
    resolve_timezone,
)


class TestParseApiDatetime:
    @pytest.mark.parametrize(
        "raw",
        [
            "2026-03-30T12:00:00Z",
            "2026-03-30T12:00:00+00:00",
            "2026-03-30T12:00:00",
            "2026-03-30 12:00:00",
            "30.03.2026 12:00:00",
            "30.03.2026 12:00",
        ],
    )
    def test_all_supported_formats_yield_the_same_utc_instant(self, raw):
        assert parse_api_datetime(raw) == datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)

    def test_result_is_always_timezone_aware(self):
        assert parse_api_datetime("2026-03-30T12:00:00").tzinfo is not None

    def test_non_utc_offset_is_normalised_to_utc(self):
        parsed = parse_api_datetime("2026-03-30T14:00:00+02:00")
        assert parsed == datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)

    def test_surrounding_whitespace_is_tolerated(self):
        assert parse_api_datetime("  2026-03-30T12:00:00Z  ") == datetime(
            2026, 3, 30, 12, 0, tzinfo=timezone.utc
        )

    @pytest.mark.parametrize("raw", ["", "   ", None, 12345, "not a date"])
    def test_unparseable_input_raises(self, raw):
        with pytest.raises(ValueError):
            parse_api_datetime(raw)

    def test_date_only_is_rejected_rather_than_assumed_to_be_midnight(self):
        # A bare date would silently become 00:00, scheduling the match at the wrong time.
        with pytest.raises(ValueError):
            parse_api_datetime("2026-03-30")


class TestConvertToLocalTimezone:
    def test_converts_to_target_zone_preserving_the_instant(self):
        local = convert_to_local_timezone("2026-01-15T12:00:00Z", "Europe/Warsaw")
        assert local.hour == 13  # CET is UTC+1 in January
        assert local.astimezone(timezone.utc) == datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

    def test_handles_daylight_saving_offset(self):
        local = convert_to_local_timezone("2026-07-15T12:00:00Z", "Europe/Warsaw")
        assert local.hour == 14  # CEST is UTC+2 in July

    def test_unknown_timezone_raises_instead_of_guessing_an_offset(self):
        # Falling back to a fixed offset used to silently schedule matches an hour
        # early for half the year.
        with pytest.raises(ValueError, match="Unknown timezone"):
            convert_to_local_timezone("2026-01-15T12:00:00Z", "Not/AZone")

    def test_invalid_date_propagates(self):
        with pytest.raises(ValueError):
            convert_to_local_timezone("garbage", "Europe/Warsaw")


class TestResolveTimezone:
    def test_a_valid_iana_name_resolves(self):
        assert str(resolve_timezone("Europe/Warsaw")) == "Europe/Warsaw"

    @pytest.mark.parametrize("name", ["Not/AZone", "", None, 42, "CEST"])
    def test_invalid_names_raise_a_helpful_error(self, name):
        with pytest.raises(ValueError, match="Unknown timezone"):
            resolve_timezone(name)

    def test_the_error_mentions_the_windows_requirement(self):
        # Windows has no system tz database; the message must say so.
        with pytest.raises(ValueError, match="tzdata"):
            resolve_timezone("Not/AZone")


class TestDaylightSavingAcrossZones:
    """A fixed UTC offset cannot represent these zones correctly year round."""

    @pytest.mark.parametrize(
        "zone,winter_hour,summer_hour",
        [
            ("Europe/Warsaw", 13, 14),   # CET  -> CEST
            ("Europe/London", 12, 13),   # GMT  -> BST
            ("America/New_York", 7, 8),  # EST  -> EDT
            ("Europe/Kyiv", 14, 15),     # EET  -> EEST
            ("UTC", 12, 12),             # never shifts
            ("Asia/Tokyo", 21, 21),      # no DST
        ],
    )
    def test_offsets_shift_with_the_season(self, zone, winter_hour, summer_hour):
        winter = convert_to_local_timezone("2026-01-15T12:00:00Z", zone)
        summer = convert_to_local_timezone("2026-07-15T12:00:00Z", zone)
        assert winter.hour == winter_hour
        assert summer.hour == summer_hour

    def test_the_underlying_instant_is_never_altered(self):
        for zone in ["Europe/Warsaw", "America/New_York", "Asia/Tokyo"]:
            converted = convert_to_local_timezone("2026-07-15T12:00:00Z", zone)
            assert converted.astimezone(timezone.utc) == datetime(
                2026, 7, 15, 12, 0, tzinfo=timezone.utc
            )

    def test_the_zone_name_survives_conversion(self):
        # Google Calendar is sent str(tzinfo), so it must stay a real IANA name.
        assert str(convert_to_local_timezone("2026-07-15T12:00:00Z", "Europe/Warsaw").tzinfo) == (
            "Europe/Warsaw"
        )

    def test_matches_on_either_side_of_a_dst_switch_get_different_offsets(self):
        # Warsaw moves to CEST on 2026-03-29.
        before = convert_to_local_timezone("2026-03-28T12:00:00Z", "Europe/Warsaw")
        after = convert_to_local_timezone("2026-03-30T12:00:00Z", "Europe/Warsaw")
        assert before.utcoffset() == timedelta(hours=1)
        assert after.utcoffset() == timedelta(hours=2)
