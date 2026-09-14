import json

import pytest

from src.core.config import APIConfig, Config, DatabaseConfig, GoogleCalendarConfig


ENV_VARS = [
    "GOOGLE_CAL_ID",
    "SERVICE_ACCOUNT_FILE",
    "DATABASE_PATH",
    "API_TIMEOUT",
    "CACHE_TTL",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "INDIVIDUAL_PLAYERS",
    "H2H_PLAYERS",
    "API_CUSTOM_HEADERS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Keep the developer's own environment from leaking into config tests."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def make_config(tmp_path, **overrides):
    key_file = tmp_path / "service-account.json"
    key_file.write_text("{}")
    defaults = dict(
        individual_players={"ronnie": 1},
        h2h_players={},
        google_calendar=GoogleCalendarConfig(
            calendar_id="cal@group.calendar.google.com",
            service_account_file=str(key_file),
        ),
        database=DatabaseConfig(path=str(tmp_path / "events.db")),
        api=APIConfig(custom_headers={"X-Requested-By": "tester"}),
        custom_headers={"X-Requested-By": "tester"},
    )
    defaults.update(overrides)
    return Config(**defaults)


class TestValidate:
    def test_a_complete_config_passes(self, tmp_path):
        make_config(tmp_path).validate()

    def test_missing_calendar_id_is_rejected(self, tmp_path):
        config = make_config(tmp_path)
        config.google_calendar.calendar_id = ""
        with pytest.raises(ValueError, match="Calendar ID"):
            config.validate()

    def test_missing_service_account_file_is_rejected(self, tmp_path):
        config = make_config(tmp_path)
        config.google_calendar.service_account_file = str(tmp_path / "nope.json")
        with pytest.raises(ValueError, match="not found"):
            config.validate()

    def test_config_without_any_players_is_rejected(self, tmp_path):
        config = make_config(tmp_path, individual_players={}, h2h_players={})
        with pytest.raises(ValueError, match="At least one"):
            config.validate()

    def test_missing_api_identification_header_is_rejected(self, tmp_path):
        # snooker.org rejects requests without X-Requested-By, so catch it before the call.
        config = make_config(tmp_path, custom_headers={}, api=APIConfig(custom_headers={}))
        with pytest.raises(ValueError, match="X-Requested-By"):
            config.validate()


class TestFilteredH2HPlayers:
    def test_players_tracked_individually_are_excluded_from_pairing(self):
        config = Config(
            individual_players={"ronnie": 1},
            h2h_players={"ronnie": 1, "judd": 2},
            google_calendar=GoogleCalendarConfig("cal", "key.json"),
            database=DatabaseConfig(),
            api=APIConfig(),
        )
        # Ronnie's matches are already covered; pairing him again would duplicate events.
        assert config.get_filtered_h2h_players() == {"judd": 2}

    def test_non_overlapping_players_are_kept(self):
        config = Config(
            individual_players={"ronnie": 1},
            h2h_players={"judd": 2, "mark": 3},
            google_calendar=GoogleCalendarConfig("cal", "key.json"),
            database=DatabaseConfig(),
            api=APIConfig(),
        )
        assert config.get_filtered_h2h_players() == {"judd": 2, "mark": 3}


class TestLoad:
    def test_missing_file_falls_back_to_defaults(self, tmp_path):
        config = Config.load(str(tmp_path / "absent.json"))
        assert config.individual_players == {}
        assert config.api.timeout == 30

    def test_values_are_read_from_the_file(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {
                    "individual_players": {"ronnie": 1},
                    "google_calendar": {
                        "calendar_id": "from-file",
                        "service_account_file": "key.json",
                    },
                    "api": {"timeout": 5, "custom_headers": {"X-Requested-By": "from-file"}},
                }
            )
        )
        config = Config.load(str(path))
        assert config.individual_players == {"ronnie": 1}
        assert config.google_calendar.calendar_id == "from-file"
        assert config.custom_headers["X-Requested-By"] == "from-file"

    def test_malformed_file_does_not_crash_the_loader(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("{ not json")
        assert Config.load(str(path)).api.timeout == 30

    def test_environment_overrides_the_file(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"google_calendar": {"calendar_id": "from-file",
                                                        "service_account_file": "key.json"}}))
        monkeypatch.setenv("GOOGLE_CAL_ID", "from-env")
        monkeypatch.setenv("API_TIMEOUT", "99")
        config = Config.load(str(path))
        assert config.google_calendar.calendar_id == "from-env"
        assert config.api.timeout == 99

    def test_players_can_be_supplied_as_json_in_the_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDIVIDUAL_PLAYERS", '{"ronnie": 1}')
        assert Config.load(str(tmp_path / "absent.json")).individual_players == {"ronnie": 1}

    def test_invalid_json_in_the_environment_is_ignored_rather_than_fatal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDIVIDUAL_PLAYERS", "not json")
        assert Config.load(str(tmp_path / "absent.json")).individual_players == {}

    def test_environment_headers_merge_with_file_headers(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"api": {"custom_headers": {"User-Agent": "from-file"}}}))
        monkeypatch.setenv("API_CUSTOM_HEADERS", '{"X-Requested-By": "from-env"}')
        headers = Config.load(str(path)).custom_headers
        assert headers == {"User-Agent": "from-file", "X-Requested-By": "from-env"}


class TestTimezone:
    def test_defaults_when_unspecified(self, tmp_path):
        assert Config.load(str(tmp_path / "absent.json")).timezone == "Europe/Warsaw"

    def test_is_read_from_the_file(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"timezone": "America/New_York"}))
        assert Config.load(str(path)).timezone == "America/New_York"

    def test_environment_overrides_the_file(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"timezone": "America/New_York"}))
        monkeypatch.setenv("TIMEZONE", "Asia/Tokyo")
        assert Config.load(str(path)).timezone == "Asia/Tokyo"

    def test_validate_accepts_a_real_zone(self, tmp_path):
        make_config(tmp_path, timezone="America/New_York").validate()

    def test_validate_rejects_an_unknown_zone(self, tmp_path):
        # Caught up front, because a bad zone otherwise makes every event silently
        # fail to build and the sync reports "no changes".
        with pytest.raises(ValueError, match="Unknown timezone"):
            make_config(tmp_path, timezone="Not/AZone").validate()
