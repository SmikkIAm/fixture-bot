import time
import logging
import requests
from typing import List, Dict, Any, Optional

from ..core.constants import (
    API_TIMEOUT,
    MAX_RETRIES,
    MIN_REQUEST_INTERVAL,
    RETRY_BASE_DELAY,
    RETRY_BACKOFF_FACTOR,
    RETRY_STATUS_CODES,
    DEFAULT_USER_AGENT,
    SNOOKER_API_BASE_URL,
    API_ENDPOINT_MATCHES,
    API_ENDPOINT_PLAYER,
    API_ENDPOINT_EVENT,
    API_ENDPOINT_ROUNDS,
)
from ..models.player import Player

logger = logging.getLogger(__name__)


class APIUnavailableError(Exception):
    """
    The API could not be reached after retries, typically rate limiting.

    Distinct from a record that legitimately has no name: callers fall back to a
    placeholder for the latter, but must abort for this, because writing
    placeholder titles into the calendar is not recoverable on a later sync.
    """


class APIService:
    def __init__(
        self,
        timeout: int = API_TIMEOUT,
        custom_headers: dict = None,
        max_retries: int = MAX_RETRIES,
        min_request_interval: float = MIN_REQUEST_INTERVAL,
    ):
        """Custom headers required for snooker.org API access (X-Requested-By header)."""
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_request_interval = min_request_interval
        self.player_cache = {}
        self.tournament_cache = {}
        self.round_cache = {}
        self._last_request_at = None

        self.headers = {"User-Agent": DEFAULT_USER_AGENT}
        if custom_headers:
            self.headers.update(custom_headers)
        self.base_url = SNOOKER_API_BASE_URL

    def _throttle(self) -> None:
        """Space requests out; the API rejects bursts rather than queuing them."""
        if self.min_request_interval <= 0 or self._last_request_at is None:
            return

        wait = self.min_request_interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def _get_json(self, url: str) -> Any:
        """
        Fetch and parse JSON, retrying throttled and transient failures with
        exponential backoff. Raises if every attempt fails.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            self._throttle()

            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
            else:
                if response.status_code == 200:
                    self._last_request_at = time.monotonic()
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise Exception(f"Failed to parse JSON response from {url}: {exc}") from exc

                if response.status_code not in RETRY_STATUS_CODES:
                    self._last_request_at = time.monotonic()
                    raise Exception(f"API returned status {response.status_code} for {url}")

                last_error = f"HTTP {response.status_code}"

            self._last_request_at = time.monotonic()

            if attempt < self.max_retries:
                delay = RETRY_BASE_DELAY * (RETRY_BACKOFF_FACTOR ** attempt)
                logger.warning(
                    "Request to %s failed (%s); retrying in %.1fs [attempt %d/%d]",
                    url, last_error, delay, attempt + 1, self.max_retries,
                )
                time.sleep(delay)

        raise APIUnavailableError(
            f"snooker.org did not respond successfully after {self.max_retries + 1} attempts "
            f"(last error: {last_error}). This is usually rate limiting - wait a few minutes "
            f"and run the command again."
        )

    def fetch_upcoming_matches(self) -> List[Dict[str, Any]]:
        """Uses matches endpoint for comprehensive data (player IDs, schedule, context)."""
        data = self._get_json(f"{self.base_url}{API_ENDPOINT_MATCHES}")

        if isinstance(data, list):
            print(f"Fetched {len(data)} matches from API")
            return data
        return []

    def fetch_player(self, player_id: int) -> Player:
        cache_key = f"player_{player_id}"
        if cache_key in self.player_cache:
            return Player.from_dict(self.player_cache[cache_key])

        url = f"{self.base_url}{API_ENDPOINT_PLAYER.format(player_id=player_id)}"

        try:
            data = self._get_json(url)
        except APIUnavailableError:
            # Abort rather than invent a name: a placeholder title written to the
            # calendar now would match on the next sync and never be corrected.
            raise
        except Exception as exc:
            logger.warning("Player %s lookup failed (%s); using a placeholder name", player_id, exc)
            return Player.create_fallback(player_id)

        if isinstance(data, list) and data:
            player_data = data[0]
            first_name = (player_data.get("FirstName") or "").strip()
            last_name = (player_data.get("LastName") or "").strip()

            if first_name or last_name:
                player = Player(id=player_id, first_name=first_name, last_name=last_name)
                self.player_cache[cache_key] = player.to_dict()
                return player

        logger.warning("Player %s returned no name; using a placeholder", player_id)
        return Player.create_fallback(player_id)

    def fetch_tournament_name(self, event_id: int) -> str:
        """Legacy API returns tournament data as single-element arrays."""
        cache_key = f"tournament_{event_id}"
        if cache_key in self.tournament_cache:
            return self.tournament_cache[cache_key]

        url = f"{self.base_url}{API_ENDPOINT_EVENT.format(event_id=event_id)}"

        try:
            data = self._get_json(url)
        except APIUnavailableError:
            raise
        except Exception as exc:
            logger.warning("Event %s lookup failed (%s); using a placeholder name", event_id, exc)
            return f"Event {event_id}"

        if isinstance(data, list) and data:
            name = str(data[0].get("Name", "")).strip()
            if name:
                self.tournament_cache[cache_key] = name
                return name

        logger.warning("Event %s returned no name; using a placeholder", event_id)
        return f"Event {event_id}"

    def _fetch_rounds(self, event_id: int) -> List[Dict[str, Any]]:
        """One request returns every round of an event, so it is cached per event."""
        if event_id in self.round_cache:
            return self.round_cache[event_id]

        url = f"{self.base_url}{API_ENDPOINT_ROUNDS.format(event_id=event_id)}"

        try:
            rounds_data = self._get_json(url)
        except APIUnavailableError:
            raise
        except Exception as exc:
            logger.warning("Round lookup failed for event %s (%s)", event_id, exc)
            return []

        rounds = rounds_data if isinstance(rounds_data, list) else []
        if rounds:
            self.round_cache[event_id] = rounds
        return rounds

    def fetch_round_name(self, event_id: int, round_id: int) -> str:
        for round_info in self._fetch_rounds(event_id):
            if isinstance(round_info, dict) and round_info.get("Round") == round_id:
                round_name = (round_info.get("RoundName") or "").strip()
                if round_name:
                    return round_name

        return "Unknown Round"

    def fetch_snooker_data(self, individual_players: Dict[str, int], h2h_players: Dict[str, int] = None) -> tuple:
        """
        Single-pass processing optimizes API usage by avoiding multiple fetches.
        H2H matches take priority to prevent duplicate event creation.
        """
        data = self.fetch_upcoming_matches()
        if not data:
            return {}, [], []

        tracked_player_ids = set(individual_players.values()) if individual_players else set()

        h2h_valid_pairs = set()
        if h2h_players and len(h2h_players) >= 2:
            h2h_valid_pairs = self._generate_player_pairs_set(h2h_players)

        individual_events_by_player = {name: [] for name in individual_players.keys()} if individual_players else {}
        h2h_events = []
        all_events = []
        processed_matches = set()

        for match in data:
            if not self._is_upcoming_match(match):
                continue

            match_id = match.get("ID")
            if match_id in processed_matches:
                continue

            if self._process_h2h_match(match, h2h_valid_pairs, h2h_events, all_events):
                processed_matches.add(match_id)
                continue

            if self._process_individual_match(match, tracked_player_ids, individual_players, individual_events_by_player, all_events):
                processed_matches.add(match_id)

        total_individual = sum(len(events) for events in individual_events_by_player.values())
        print("\nAPI Processing Summary:")
        print(f"- Total matches in API: {len(data)}")
        print(f"- Individual player events: {total_individual}")
        print(f"- Head-to-head events: {len(h2h_events)}")
        print(f"- Total events processed: {len(all_events)}")

        return individual_events_by_player, h2h_events, all_events

    def _generate_player_pairs_set(self, players_dict: Dict[str, int]) -> set:
        import itertools

        player_ids = list(players_dict.values())
        pairs = list(itertools.combinations(sorted(player_ids), 2))
        return set(pairs)

    def _is_upcoming_match(self, match: Dict[str, Any]) -> bool:
        scheduled_date = match.get("ScheduledDate")
        return scheduled_date and match.get("Status") == 0

    def _process_h2h_match(self, match: Dict[str, Any], h2h_valid_pairs: set, h2h_events: list, all_events: list) -> bool:
        player1_id = match.get("Player1ID")
        player2_id = match.get("Player2ID")

        if not player1_id or not player2_id:
            return False

        pair = tuple(sorted([player1_id, player2_id]))
        if pair in h2h_valid_pairs:
            h2h_events.append(match)
            all_events.append(match)
            return True

        return False

    def _process_individual_match(self, match: Dict[str, Any], tracked_player_ids: set,
                                individual_players: Dict[str, int], individual_events_by_player: Dict[str, list],
                                all_events: list) -> bool:
        player1_id = match.get("Player1ID")
        player2_id = match.get("Player2ID")

        processed = False

        if player1_id in tracked_player_ids:
            for name, pid in individual_players.items():
                if pid == player1_id:
                    individual_events_by_player[name].append(match)
                    all_events.append(match)
                    processed = True
                    break

        if player2_id in tracked_player_ids:
            for name, pid in individual_players.items():
                if pid == player2_id:
                    individual_events_by_player[name].append(match)
                    if not processed:
                        all_events.append(match)
                    processed = True
                    break

        return processed
