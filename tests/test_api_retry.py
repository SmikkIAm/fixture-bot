import pytest
import requests

from src.services import api_service as api_module
from src.services.api_service import APIService, APIUnavailableError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def sleeps(monkeypatch):
    """Capture backoff delays instead of actually waiting."""
    recorded = []
    monkeypatch.setattr(api_module.time, "sleep", lambda s: recorded.append(s))
    return recorded


@pytest.fixture
def service():
    # Throttling is exercised separately; keep it out of the retry tests.
    return APIService(custom_headers={"X-Requested-By": "tester"}, min_request_interval=0)


def fake_get(responses, calls):
    def _get(url, **kwargs):
        calls.append(url)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return _get


class TestRetryBehaviour:
    def test_a_successful_request_is_not_retried(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(200, [{"a": 1}])], calls))
        assert service._get_json("http://x") == [{"a": 1}]
        assert len(calls) == 1
        assert sleeps == []

    def test_a_throttled_request_is_retried_and_can_succeed(self, service, monkeypatch, sleeps):
        # snooker.org answers bursts with 403, which is why 403 must be retryable.
        calls = []
        monkeypatch.setattr(
            api_module.requests,
            "get",
            fake_get([FakeResponse(403), FakeResponse(403), FakeResponse(200, ["ok"])], calls),
        )
        assert service._get_json("http://x") == ["ok"]
        assert len(calls) == 3

    @pytest.mark.parametrize("status", [403, 429, 500, 502, 503, 504])
    def test_every_transient_status_is_retried(self, service, monkeypatch, sleeps, status):
        calls = []
        monkeypatch.setattr(
            api_module.requests, "get", fake_get([FakeResponse(status), FakeResponse(200, ["ok"])], calls)
        )
        assert service._get_json("http://x") == ["ok"]
        assert len(calls) == 2

    def test_a_permanent_failure_is_not_retried(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(404)], calls))
        with pytest.raises(Exception, match="404"):
            service._get_json("http://x")
        assert len(calls) == 1

    def test_network_errors_are_retried(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(
            api_module.requests,
            "get",
            fake_get([requests.exceptions.ConnectionError("down"), FakeResponse(200, ["ok"])], calls),
        )
        assert service._get_json("http://x") == ["ok"]
        assert len(calls) == 2

    def test_retries_are_bounded_and_then_raise(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(403)] * 4, calls))
        with pytest.raises(APIUnavailableError, match="rate limiting"):
            service._get_json("http://x")
        assert len(calls) == 4  # the initial attempt plus max_retries

    def test_backoff_delay_grows_exponentially(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(403)] * 4, calls))
        with pytest.raises(Exception):
            service._get_json("http://x")
        assert sleeps == [5.0, 10.0, 20.0]

    def test_unparseable_json_is_reported_clearly(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(
            api_module.requests, "get", fake_get([FakeResponse(200, bad_json=True)], calls)
        )
        with pytest.raises(Exception, match="Failed to parse JSON"):
            service._get_json("http://x")


class TestThrottling:
    def test_the_first_request_is_not_delayed(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(api_module.time, "sleep", lambda s: recorded.append(s))
        service = APIService(min_request_interval=5)
        service._throttle()
        assert recorded == []

    def test_consecutive_requests_are_spaced_out(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(api_module.time, "sleep", lambda s: recorded.append(s))
        monkeypatch.setattr(api_module.time, "monotonic", lambda: 100.0)
        service = APIService(min_request_interval=5)
        service._last_request_at = 98.0  # 2s ago, so 3s of the interval remains
        service._throttle()
        assert recorded == [3.0]

    def test_no_wait_once_the_interval_has_already_passed(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(api_module.time, "sleep", lambda s: recorded.append(s))
        monkeypatch.setattr(api_module.time, "monotonic", lambda: 100.0)
        service = APIService(min_request_interval=5)
        service._last_request_at = 90.0
        service._throttle()
        assert recorded == []

    def test_throttling_can_be_disabled(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(api_module.time, "sleep", lambda s: recorded.append(s))
        service = APIService(min_request_interval=0)
        service._last_request_at = 0.0
        service._throttle()
        assert recorded == []


class TestThrottlingAbortsRatherThanFabricating:
    """A throttled lookup must not write a placeholder title into the calendar:
    the placeholder would match on the next sync and never be corrected."""

    def test_a_throttled_player_lookup_aborts(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(403)] * 4, calls))
        with pytest.raises(APIUnavailableError):
            service.fetch_player(17)
        assert service.player_cache == {}

    def test_a_throttled_tournament_lookup_aborts(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(403)] * 4, calls))
        with pytest.raises(APIUnavailableError):
            service.fetch_tournament_name(2771)
        assert service.tournament_cache == {}

    def test_a_throttled_round_lookup_aborts(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(403)] * 4, calls))
        with pytest.raises(APIUnavailableError):
            service.fetch_round_name(10, 1)
        assert service.round_cache == {}


class TestGenuinelyMissingDataStillFallsBack:
    """A record that really has no name is a stable fact, not a transient failure."""

    def test_a_missing_player_record_falls_back(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(404)], calls))
        assert service.fetch_player(17).display_name == "Player 17"
        assert len(calls) == 1  # a 404 is not retried

    def test_an_empty_player_record_falls_back_without_caching(self, service, monkeypatch, sleeps):
        calls = []
        responses = [
            FakeResponse(200, [{"FirstName": "", "LastName": ""}]),
            FakeResponse(200, [{"FirstName": "Neil", "LastName": "Robertson"}]),
        ]
        monkeypatch.setattr(api_module.requests, "get", fake_get(responses, calls))
        assert service.fetch_player(17).display_name == "Player 17"
        assert service.player_cache == {}
        assert service.fetch_player(17).display_name == "Neil Robertson"

    def test_a_missing_tournament_record_falls_back(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(404)], calls))
        assert service.fetch_tournament_name(2771) == "Event 2771"


class TestCaching:
    def test_a_successful_player_lookup_is_cached(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(
            api_module.requests,
            "get",
            fake_get([FakeResponse(200, [{"FirstName": "Neil", "LastName": "Robertson"}])], calls),
        )
        assert service.fetch_player(17).display_name == "Neil Robertson"
        assert service.fetch_player(17).display_name == "Neil Robertson"
        assert len(calls) == 1

    def test_a_successful_tournament_lookup_is_cached(self, service, monkeypatch, sleeps):
        calls = []
        monkeypatch.setattr(
            api_module.requests, "get", fake_get([FakeResponse(200, [{"Name": "UK Championship"}])], calls)
        )
        assert service.fetch_tournament_name(2771) == "UK Championship"
        assert service.fetch_tournament_name(2771) == "UK Championship"
        assert len(calls) == 1

    def test_all_rounds_of_an_event_come_from_one_request(self, service, monkeypatch, sleeps):
        # One response describes every round, so asking for a second round of the
        # same event must not cost another request against the rate limit.
        calls = []
        payload = [{"Round": 1, "RoundName": "Round 1"}, {"Round": 2, "RoundName": "Final"}]
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(200, payload)], calls))
        assert service.fetch_round_name(10, 1) == "Round 1"
        assert service.fetch_round_name(10, 2) == "Final"
        assert len(calls) == 1

    def test_an_unknown_round_reports_a_placeholder(self, service, monkeypatch, sleeps):
        calls = []
        payload = [{"Round": 1, "RoundName": "Round 1"}]
        monkeypatch.setattr(api_module.requests, "get", fake_get([FakeResponse(200, payload)], calls))
        assert service.fetch_round_name(10, 99) == "Unknown Round"
