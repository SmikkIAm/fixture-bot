from datetime import datetime, timedelta, timezone

import pytest

from src.data.database import EventDatabase
from src.models.event import Event, EventSource
from src.services.database_service import DatabaseService


NOW = datetime.now(timezone.utc)


@pytest.fixture
def repo(tmp_path):
    service = DatabaseService(str(tmp_path / "events.db"))
    service.initialize_database()
    return EventDatabase(service)


def make_event(event_id="snooker-1", start=None, title="A vs B", **overrides):
    start = start or NOW + timedelta(days=1)
    defaults = dict(
        id=event_id,
        title=title,
        start=start,
        end=start + timedelta(hours=3),
        source=EventSource.INDIVIDUAL,
        tournament="World Championship",
        calendar_event_id="cal-1",
        player1_id=1,
        player2_id=2,
        player1_name="A",
        player2_name="B",
        event_id=100,
        round_name="Final",
    )
    defaults.update(overrides)
    return Event(**defaults)


class TestPersistence:
    def test_a_saved_event_is_read_back_intact(self, repo):
        original = make_event()
        repo.save(original)
        assert repo.find_by_id("snooker-1") == original

    def test_missing_events_return_none(self, repo):
        assert repo.find_by_id("nope") is None

    def test_exists_reflects_what_is_stored(self, repo):
        repo.save(make_event())
        assert repo.exists("snooker-1") is True
        assert repo.exists("nope") is False

    def test_saving_the_same_id_twice_replaces_rather_than_duplicates(self, repo):
        # This is what keeps repeated syncs idempotent.
        repo.save(make_event(title="A vs B"))
        repo.save(make_event(title="A vs B (Final)"))
        assert len(repo.get_all()) == 1
        assert repo.find_by_id("snooker-1").title == "A vs B (Final)"

    def test_a_calendar_id_can_be_attached_on_save(self, repo):
        repo.save(make_event(calendar_event_id=None), calendar_event_id="cal-99")
        assert repo.find_by_id("snooker-1").calendar_event_id == "cal-99"

    def test_timezone_aware_times_survive_the_roundtrip(self, repo):
        start = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
        repo.save(make_event(start=start))
        stored = repo.find_by_id("snooker-1")
        assert stored.start == start
        assert stored.start.tzinfo is not None


class TestUpdateAndDelete:
    def test_update_changes_the_stored_row(self, repo):
        repo.save(make_event())
        repo.update(make_event(title="C vs D", round_name="Semi-final"))
        stored = repo.find_by_id("snooker-1")
        assert stored.title == "C vs D"
        assert stored.round_name == "Semi-final"

    def test_delete_removes_the_event_and_reports_success(self, repo):
        repo.save(make_event())
        assert repo.delete("snooker-1") is True
        assert repo.find_by_id("snooker-1") is None

    def test_deleting_something_absent_reports_failure(self, repo):
        assert repo.delete("nope") is False


class TestQueries:
    def test_get_all_is_ordered_by_start_time(self, repo):
        repo.save(make_event("snooker-2", start=NOW + timedelta(days=2)))
        repo.save(make_event("snooker-1", start=NOW + timedelta(days=1)))
        assert [event.id for event in repo.get_all()] == ["snooker-1", "snooker-2"]

    def test_get_all_is_empty_for_a_fresh_database(self, repo):
        assert repo.get_all() == []

    def test_calendar_id_listing_covers_both_event_sources(self, repo):
        repo.save(make_event("snooker-1", source=EventSource.INDIVIDUAL))
        repo.save(make_event("h2h-1", source=EventSource.HEAD_TO_HEAD))
        rows = repo.get_all_with_calendar_ids()
        assert {row["id"] for row in rows} == {"snooker-1", "h2h-1"}
        assert all(row["calendar_event_id"] == "cal-1" for row in rows)

    def test_upcoming_excludes_matches_already_played(self, repo):
        repo.save(make_event("past", start=NOW - timedelta(days=2)))
        repo.save(make_event("future", start=NOW + timedelta(days=2)))
        assert [row["id"] for row in repo.get_upcoming_events()] == ["future"]

    def test_upcoming_respects_the_limit(self, repo):
        for day in range(1, 5):
            repo.save(make_event(f"snooker-{day}", start=NOW + timedelta(days=day)))
        assert len(repo.get_upcoming_events(limit=2)) == 2

    def test_upcoming_is_ordered_soonest_first(self, repo):
        repo.save(make_event("later", start=NOW + timedelta(days=5)))
        repo.save(make_event("sooner", start=NOW + timedelta(days=2)))
        assert [row["id"] for row in repo.get_upcoming_events()] == ["sooner", "later"]


class TestDatabaseService:
    def test_initialisation_is_idempotent(self, tmp_path):
        service = DatabaseService(str(tmp_path / "events.db"))
        service.initialize_database()
        service.initialize_database()
        assert "events" in service.get_database_info()["tables"]

    def test_the_parent_directory_is_created_when_missing(self, tmp_path):
        service = DatabaseService(str(tmp_path / "nested" / "dir" / "events.db"))
        service.initialize_database()
        assert (tmp_path / "nested" / "dir" / "events.db").exists()

    def test_database_info_reports_the_event_count(self, repo, tmp_path):
        repo.save(make_event())
        assert repo.db.get_database_info()["events_count"] == 1

    def test_a_failing_query_raises_a_readable_error(self, repo):
        # Regression guard: this path used to raise TypeError from an invalid Exception
        # kwarg, which masked the real SQL error entirely.
        with pytest.raises(Exception) as exc_info:
            repo.db.execute_query("SELECT * FROM table_that_does_not_exist", fetch=True)
        assert not isinstance(exc_info.value, TypeError)
        assert "no such table" in str(exc_info.value)
