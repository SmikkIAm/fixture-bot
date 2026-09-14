from datetime import datetime, timedelta, timezone

import pytest

from src.models.event import Event, EventSource
from src.models.player import Player


START = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=3)


def make_event(**overrides) -> Event:
    defaults = dict(
        id="snooker-1",
        title="A vs B",
        start=START,
        end=END,
        source=EventSource.INDIVIDUAL,
        tournament="World Championship",
        player1_id=1,
        player2_id=2,
        player1_name="A",
        player2_name="B",
        round_name="Final",
    )
    defaults.update(overrides)
    return Event(**defaults)


class TestEventConstruction:
    def test_individual_factory_sets_id_scheme_and_source(self):
        event = Event.create_individual_event(99, "A vs B", START, END)
        assert event.id == "snooker-99"
        assert event.source is EventSource.INDIVIDUAL

    def test_h2h_factory_sets_id_scheme_and_source(self):
        event = Event.create_h2h_event(99, "A vs B", START, END)
        assert event.id == "h2h-99"
        assert event.source is EventSource.HEAD_TO_HEAD

    def test_the_two_factories_never_collide_for_the_same_match(self):
        # Re-run idempotency depends on these staying distinct.
        assert Event.create_individual_event(7, "t", START, END).id != Event.create_h2h_event(
            7, "t", START, END
        ).id

    @pytest.mark.parametrize(
        "overrides",
        [
            {"id": ""},
            {"title": ""},
            {"start": END, "end": START},
            {"start": START, "end": START},
        ],
    )
    def test_invalid_events_are_rejected(self, overrides):
        with pytest.raises(ValueError):
            make_event(**overrides)


class TestEventHasChanged:
    def test_identical_events_are_unchanged(self):
        assert make_event().has_changed(make_event()) is False

    @pytest.mark.parametrize(
        "field,value",
        [
            ("title", "C vs D"),
            ("start", START + timedelta(hours=1)),
            ("end", END + timedelta(hours=1)),
            ("tournament", "Other Open"),
            ("player1_id", 42),
            ("player1_name", "Z"),
            ("round_name", "Semi-final"),
        ],
    )
    def test_meaningful_differences_are_detected(self, field, value):
        assert make_event().has_changed(make_event(**{field: value})) is True

    def test_calendar_event_id_is_not_treated_as_a_change(self):
        # It is local bookkeeping, not match data - a difference must not trigger a calendar update.
        original = make_event(calendar_event_id="abc")
        incoming = make_event(calendar_event_id=None)
        assert original.has_changed(incoming) is False


class TestEventSerialisation:
    def test_dict_roundtrip_preserves_every_field(self):
        original = make_event(calendar_event_id="cal-1", event_id=55)
        assert Event.from_dict(original.to_dict()) == original

    def test_to_dict_renders_datetimes_as_iso_strings(self):
        data = make_event().to_dict()
        assert data["start"] == START.isoformat()
        assert data["source"] == "snooker"

    def test_calendar_payload_appends_the_tournament_to_the_summary(self):
        payload = make_event(tournament="World Championship").to_calendar_event()
        assert "A vs B" in payload["summary"]
        assert "World Championship" in payload["summary"]

    def test_calendar_payload_omits_a_missing_tournament(self):
        assert make_event(tournament=None).to_calendar_event()["summary"] == "A vs B"


class TestPlayer:
    def test_display_name_combines_both_names(self):
        assert Player(1, "Ronnie", "O'Sullivan").display_name == "Ronnie O'Sullivan"

    @pytest.mark.parametrize(
        "first,last,expected",
        [("Ronnie", "", "Ronnie"), ("", "O'Sullivan", "O'Sullivan")],
    )
    def test_display_name_handles_a_single_known_name(self, first, last, expected):
        assert Player(1, first, last).display_name == expected

    def test_fallback_player_is_usable_when_the_lookup_fails(self):
        player = Player.create_fallback(404)
        assert player.id == 404
        assert player.display_name == "Player 404"

    def test_from_api_data_strips_whitespace(self):
        player = Player.from_api_data({"ID": 5, "FirstName": " Judd ", "LastName": " Trump "})
        assert player.full_name == "Judd Trump"

    def test_from_api_data_rejects_a_payload_with_no_id(self):
        with pytest.raises(ValueError):
            Player.from_api_data({"FirstName": "Judd", "LastName": "Trump"})

    @pytest.mark.parametrize("args", [(0, "A", "B"), (-1, "A", "B"), (1, "", "")])
    def test_invalid_players_are_rejected(self, args):
        with pytest.raises(ValueError):
            Player(*args)

    def test_identity_is_based_on_id_alone(self):
        # The API spells names inconsistently; the ID is the stable identifier.
        assert Player(1, "Ronnie", "O'Sullivan") == Player(1, "R.", "OSullivan")
        assert len({Player(1, "Ronnie", "O'Sullivan"), Player(1, "R.", "OSullivan")}) == 1
