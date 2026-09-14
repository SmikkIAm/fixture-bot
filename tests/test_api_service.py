import pytest

from src.services.api_service import APIService


@pytest.fixture
def service():
    # The constructor performs no I/O, so these helpers can be exercised without the network.
    return APIService(timeout=1, custom_headers={"X-Requested-By": "tester"})


class TestHeaders:
    def test_custom_headers_are_merged_over_the_default_user_agent(self, service):
        assert service.headers["X-Requested-By"] == "tester"
        assert "User-Agent" in service.headers

    def test_a_custom_user_agent_wins(self):
        service = APIService(custom_headers={"User-Agent": "mine"})
        assert service.headers["User-Agent"] == "mine"


class TestPlayerPairs:
    def test_every_unique_pair_is_generated(self, service):
        assert service._generate_player_pairs_set({"a": 1, "b": 2, "c": 3}) == {(1, 2), (1, 3), (2, 3)}

    def test_pairs_are_order_independent(self, service):
        # Pairs are sorted so a match is found regardless of who is listed as player 1.
        assert service._generate_player_pairs_set({"b": 2, "a": 1}) == {(1, 2)}

    def test_a_single_player_produces_no_pairs(self, service):
        assert service._generate_player_pairs_set({"a": 1}) == set()


class TestUpcomingMatchFilter:
    def test_a_scheduled_unplayed_match_is_included(self, service):
        assert service._is_upcoming_match({"ScheduledDate": "2026-03-30T12:00:00Z", "Status": 0})

    def test_a_match_already_in_progress_or_finished_is_excluded(self, service):
        assert not service._is_upcoming_match({"ScheduledDate": "2026-03-30T12:00:00Z", "Status": 1})

    @pytest.mark.parametrize("match", [{"Status": 0}, {"ScheduledDate": None, "Status": 0}, {}])
    def test_a_match_without_a_schedule_is_excluded(self, service, match):
        assert not service._is_upcoming_match(match)


class TestH2HMatching:
    def test_a_match_between_two_tracked_players_is_captured(self, service):
        h2h, everything = [], []
        match = {"ID": 1, "Player1ID": 1, "Player2ID": 2}
        assert service._process_h2h_match(match, {(1, 2)}, h2h, everything) is True
        assert h2h == [match] and everything == [match]

    def test_reversed_player_order_still_matches(self, service):
        h2h, everything = [], []
        assert service._process_h2h_match({"Player1ID": 2, "Player2ID": 1}, {(1, 2)}, h2h, everything)

    def test_an_untracked_pairing_is_skipped(self, service):
        h2h, everything = [], []
        assert service._process_h2h_match({"Player1ID": 1, "Player2ID": 9}, {(1, 2)}, h2h, everything) is False
        assert h2h == [] and everything == []

    def test_a_match_with_an_unknown_opponent_is_skipped(self, service):
        h2h, everything = [], []
        assert service._process_h2h_match({"Player1ID": 1, "Player2ID": None}, {(1, 2)}, h2h, everything) is False


class TestIndividualMatching:
    def test_a_tracked_player_is_recorded_once(self, service):
        by_player, everything = {"ronnie": []}, []
        match = {"ID": 1, "Player1ID": 1, "Player2ID": 9}
        assert service._process_individual_match(match, {1}, {"ronnie": 1}, by_player, everything) is True
        assert by_player["ronnie"] == [match] and everything == [match]

    def test_a_tracked_player_is_found_in_either_slot(self, service):
        by_player, everything = {"ronnie": []}, []
        match = {"ID": 1, "Player1ID": 9, "Player2ID": 1}
        assert service._process_individual_match(match, {1}, {"ronnie": 1}, by_player, everything) is True
        assert by_player["ronnie"] == [match]

    def test_two_tracked_players_produce_a_single_shared_event(self, service):
        # Both players want the match on their list, but only one calendar event should exist.
        by_player, everything = {"ronnie": [], "judd": []}, []
        match = {"ID": 1, "Player1ID": 1, "Player2ID": 2}
        service._process_individual_match(match, {1, 2}, {"ronnie": 1, "judd": 2}, by_player, everything)
        assert by_player["ronnie"] == [match] and by_player["judd"] == [match]
        assert everything == [match]

    def test_an_untracked_match_is_ignored(self, service):
        by_player, everything = {"ronnie": []}, []
        assert service._process_individual_match(
            {"Player1ID": 8, "Player2ID": 9}, {1}, {"ronnie": 1}, by_player, everything
        ) is False
        assert everything == []
