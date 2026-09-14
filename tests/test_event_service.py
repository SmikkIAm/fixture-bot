from datetime import datetime, timedelta, timezone

import pytest

from src.models.event import Event, EventSource
from src.services.event_service import EventService


START = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def service():
    # Match-key construction is pure logic, so no collaborators are needed.
    return EventService(None, None, None, None)


def make_event(title, tournament="World Championship", start=START):
    return Event(
        id="snooker-1",
        title=title,
        start=start,
        end=start + timedelta(hours=3),
        source=EventSource.INDIVIDUAL,
        tournament=tournament,
    )


class TestMatchKey:
    def test_round_information_is_stripped(self, service):
        # The round name changes as a tournament progresses; the key must survive that.
        with_round = service._create_match_key(make_event("A vs B (Final)"))
        without_round = service._create_match_key(make_event("A vs B"))
        assert with_round == without_round

    def test_h2h_prefix_is_stripped(self, service):
        assert service._create_match_key(make_event("H2H: A vs B")) == service._create_match_key(
            make_event("A vs B")
        )

    def test_key_is_players_tournament_and_date(self, service):
        assert service._create_match_key(make_event("A vs B")) == (
            "A vs B",
            "World Championship",
            "2026-03-30",
        )

    def test_a_missing_tournament_becomes_an_empty_string(self, service):
        assert service._create_match_key(make_event("A vs B", tournament=None))[1] == ""

    def test_different_matches_produce_different_keys(self, service):
        assert service._create_match_key(make_event("A vs B")) != service._create_match_key(
            make_event("C vs D")
        )

    def test_a_match_moved_to_another_day_produces_a_different_key(self, service):
        moved = make_event("A vs B", start=START + timedelta(days=1))
        assert service._create_match_key(make_event("A vs B")) != service._create_match_key(moved)


class TestMatchKeyParity:
    """Cancellation detection compares API events against database rows, so both key
    builders must agree for equivalent data - otherwise live events get deleted."""

    def test_event_and_row_forms_agree(self, service):
        event = make_event("A vs B (Final)")
        row = {
            "title": event.title,
            "tournament": event.tournament,
            "start": event.start.isoformat(),
        }
        assert service._create_match_key(event) == service._create_match_key_from_dict(row)

    def test_agreement_holds_for_h2h_events(self, service):
        event = make_event("H2H: A vs B")
        row = {
            "title": event.title,
            "tournament": event.tournament,
            "start": event.start.isoformat(),
        }
        assert service._create_match_key(event) == service._create_match_key_from_dict(row)

    def test_agreement_holds_when_the_tournament_is_missing(self, service):
        event = make_event("A vs B", tournament=None)
        row = {"title": event.title, "tournament": None, "start": event.start.isoformat()}
        assert service._create_match_key(event) == service._create_match_key_from_dict(row)


class FakeAPI:
    """Minimal stand-in so event construction can be tested without the network."""

    def fetch_player(self, player_id):
        from src.models.player import Player

        return Player(player_id, f"Player{player_id}", "Surname")

    def fetch_round_name(self, event_id, round_id):
        return "Final"

    def fetch_tournament_name(self, event_id):
        return "World Championship"


MATCH = {
    "ID": 1,
    "ScheduledDate": "2026-07-15T12:00:00Z",
    "Player1ID": 1,
    "Player2ID": 2,
    "EventID": 10,
    "Round": 1,
}


class TestConfiguredTimezone:
    def test_events_are_built_in_the_configured_zone(self):
        service = EventService(FakeAPI(), None, None, None, timezone="America/New_York")
        event = service._create_event_from_match(MATCH, EventSource.INDIVIDUAL)
        assert event is not None
        assert event.start.hour == 8  # 12:00 UTC in July is 08:00 EDT
        assert str(event.start.tzinfo) == "America/New_York"

    def test_a_different_user_zone_yields_a_different_local_time(self):
        warsaw = EventService(FakeAPI(), None, None, None, timezone="Europe/Warsaw")
        tokyo = EventService(FakeAPI(), None, None, None, timezone="Asia/Tokyo")
        assert warsaw._create_event_from_match(MATCH, EventSource.INDIVIDUAL).start.hour == 14
        assert tokyo._create_event_from_match(MATCH, EventSource.INDIVIDUAL).start.hour == 21

    def test_summer_time_is_applied_to_the_configured_zone(self):
        service = EventService(FakeAPI(), None, None, None, timezone="Europe/Warsaw")
        winter = dict(MATCH, ScheduledDate="2026-01-15T12:00:00Z")
        assert service._create_event_from_match(winter, EventSource.INDIVIDUAL).start.hour == 13
        assert service._create_event_from_match(MATCH, EventSource.INDIVIDUAL).start.hour == 14

    def test_the_default_zone_is_used_when_none_is_given(self):
        service = EventService(FakeAPI(), None, None, None)
        assert str(service._create_event_from_match(MATCH, EventSource.INDIVIDUAL).start.tzinfo) == (
            "Europe/Warsaw"
        )

    def test_the_calendar_payload_carries_an_iana_zone_name(self):
        # Google rejects offset strings like "UTC+01:00"; it needs a real zone id.
        service = EventService(FakeAPI(), None, None, None, timezone="Europe/Warsaw")
        payload = service._create_event_from_match(MATCH, EventSource.INDIVIDUAL).to_calendar_event()
        assert payload["start"]["timeZone"] == "Europe/Warsaw"
        assert payload["end"]["timeZone"] == "Europe/Warsaw"

    def test_match_duration_is_applied_in_local_time(self):
        service = EventService(FakeAPI(), None, None, None, timezone="Europe/Warsaw")
        event = service._create_event_from_match(MATCH, EventSource.INDIVIDUAL)
        assert event.end - event.start == timedelta(hours=3)
