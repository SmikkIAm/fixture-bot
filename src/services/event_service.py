from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime, timedelta

from ..models.event import Event, EventSource
from ..models.player import Player
from ..services.api_service import APIService, APIUnavailableError
from ..services.calendar_service import CalendarService
from ..services.database_service import DatabaseService
from ..data.database import EventDatabase
from ..utils.datetime_utils import convert_to_local_timezone
from ..core.constants import DEFAULT_MATCH_DURATION, DEFAULT_TIMEZONE

class EventService:
    def __init__(
        self,
        api_service: APIService,
        calendar_service: CalendarService,
        database_service: DatabaseService,
        event_repository: EventDatabase,
        timezone: str = DEFAULT_TIMEZONE,
    ):
        self.api = api_service
        self.calendar = calendar_service
        self.db = database_service
        self.events = event_repository
        self.timezone = timezone
    
    def sync_events(
        self,
        individual_players: Dict[str, int],
        h2h_players: Dict[str, int]
    ) -> Tuple[int, int, int]:
        try:
            individual_events_by_player, h2h_events, all_events = self._fetch_and_process_events(
                individual_players, h2h_players
            )
            
            total_added = 0
            total_updated = 0
            
            for player_name, events in individual_events_by_player.items():
                added, updated = self._process_events(events)
                total_added += added
                total_updated += updated
            
            if h2h_events:
                added, updated = self._process_events(h2h_events)
                total_added += added
                total_updated += updated
            
            total_cancelled = self._cleanup_cancelled_events(all_events)
            
            return total_added, total_updated, total_cancelled
            
        except Exception as e:
            if isinstance(e, Exception):
                raise
            raise Exception(f"Event synchronization failed: {str(e)}")
    
    def get_detailed_check_events(
        self,
        individual_players: Dict[str, int],
        h2h_players: Dict[str, int]
    ) -> Tuple[List[Event], List[Event], List[Event]]:
        try:
            individual_events_by_player, h2h_events, all_events = self._fetch_and_process_events(
                individual_players, h2h_players
            )
            
            would_add_events = []
            would_update_events = []
            
            # Check individual player events
            for player_name, events in individual_events_by_player.items():
                new_events, updated_events = self._get_detailed_check_events(events)
                would_add_events.extend(new_events)
                would_update_events.extend(updated_events)
            
            # Check H2H events
            if h2h_events:
                new_events, updated_events = self._get_detailed_check_events(h2h_events)
                would_add_events.extend(new_events)
                would_update_events.extend(updated_events)
            
            # Check for cancelled events
            would_cancel_events = self._get_cancelled_events(all_events)
            
            return would_add_events, would_update_events, would_cancel_events
            
        except Exception as e:
            if isinstance(e, Exception):
                raise
            raise Exception(f"Detailed event check failed: {str(e)}")


    def _fetch_and_process_events(
        self,
        individual_players: Dict[str, int],
        h2h_players: Dict[str, int]
    ) -> Tuple[Dict[str, List[Event]], List[Event], List[Event]]:
        individual_events_raw, h2h_events_raw, all_events_raw = self.api.fetch_snooker_data(
            individual_players, h2h_players
        )
        
        individual_events_by_player = {}
        for player_name, matches in individual_events_raw.items():
            individual_events_by_player[player_name] = [
                self._create_event_from_match(match_data, EventSource.INDIVIDUAL)
                for match_data in matches
            ]
            individual_events_by_player[player_name] = [
                event for event in individual_events_by_player[player_name] if event is not None
            ]
        
        h2h_events = [
            self._create_event_from_match(match_data, EventSource.HEAD_TO_HEAD)
            for match_data in h2h_events_raw
        ]
        h2h_events = [event for event in h2h_events if event is not None]
        
        all_events = []
        for match_data in all_events_raw:
            source = EventSource.INDIVIDUAL
            for h2h_match in h2h_events_raw:
                if match_data.get('ID') == h2h_match.get('ID'):
                    source = EventSource.HEAD_TO_HEAD
                    break
            
            event = self._create_event_from_match(match_data, source)
            if event is not None:
                all_events.append(event)
        
        return individual_events_by_player, h2h_events, all_events
    
    def _process_events(self, events: List[Event]) -> Tuple[int, int]:
        """Calendar updates before database to maintain consistency."""
        added = 0
        updated = 0
        
        for event in events:
            result = self._process_single_event(event)
            if result == "added":
                added += 1
            elif result == "updated":
                updated += 1
        
        return added, updated
    
    def _process_single_event(self, event: Event) -> Optional[str]:
        """Process a single event. Returns 'added', 'updated', or None."""
        existing_event = self.events.find_by_id(event.id)
        
        if not existing_event:
            return self._add_new_event(event)
        
        if self._needs_calendar_recreation(existing_event):
            return self._add_new_event(event)
        
        if event.has_changed(existing_event):
            return self._try_update_event(existing_event, event)
        
        return None
    
    def _needs_calendar_recreation(self, existing_event: Event) -> bool:
        """Check if event exists in DB but calendar entry is missing."""
        if not existing_event.calendar_event_id:
            return False
        return not self.calendar.event_exists(existing_event.calendar_event_id)
    
    def _add_new_event(self, event: Event) -> Optional[str]:
        """Add new event to calendar and database."""
        try:
            calendar_event_id = self.calendar.add_event(event)
            event.calendar_event_id = calendar_event_id
            self.events.save(event)
            return "added"
        except Exception:
            return None
    
    def _try_update_event(self, existing_event: Event, new_event: Event) -> Optional[str]:
        """Attempt to update an existing event."""
        try:
            if self._update_existing_event(existing_event, new_event):
                return "updated"
        except Exception:
            pass
        return None
    
    def _get_detailed_check_events(self, events: List[Event]) -> Tuple[List[Event], List[Event]]:
        new_events = []
        updated_events = []
        
        for event in events:
            existing_event = self.events.find_by_id(event.id)
            
            if not existing_event:
                new_events.append(event)
            elif event.has_changed(existing_event):
                updated_events.append(event)
        
        return new_events, updated_events

    def _get_cancelled_events(self, all_events: List[Event]) -> List[Event]:
        db_events = self.events.get_all()
        api_event_ids = {event.id for event in all_events}
        api_events_by_key = self._build_events_key_map(all_events)
        
        cancelled_events = []
        for db_event in db_events:
            if self._is_event_object_still_active(db_event, api_event_ids, api_events_by_key):
                continue
            cancelled_events.append(db_event)
        
        return cancelled_events
    
    def _is_event_object_still_active(
        self, 
        db_event: Event, 
        current_event_ids: Set[str], 
        current_events_by_key: Dict
    ) -> bool:
        """Check if a database Event object still exists in current API data."""
        if db_event.id in current_event_ids:
            return True
        
        db_key = self._create_match_key(db_event)
        return db_key in current_events_by_key
    
    def _update_existing_event(self, existing_event: Event, new_event: Event) -> bool:
        """Update calendar first; if that fails, delete and recreate to avoid stale data."""

        if existing_event.calendar_event_id:
            if self.calendar.update_event(existing_event.calendar_event_id, new_event):
                new_event.calendar_event_id = existing_event.calendar_event_id
                self.events.update(new_event)
                return True

            self.calendar.delete_event(existing_event.calendar_event_id)
            calendar_event_id = self.calendar.add_event(new_event)
            new_event.calendar_event_id = calendar_event_id
            self.events.update(new_event)
            return True

        calendar_event_id = self.calendar.add_event(new_event)
        new_event.calendar_event_id = calendar_event_id
        self.events.update(new_event)
        return True
    
    def _cleanup_cancelled_events(self, current_events: List[Event]) -> int:
        db_events = self.events.get_all_with_calendar_ids()
        current_event_ids = {event.id for event in current_events}
        current_events_by_key = self._build_events_key_map(current_events)
        
        cancelled_count = 0
        for db_event in db_events:
            if self._is_event_still_active(db_event, current_event_ids, current_events_by_key):
                continue
            
            self._remove_cancelled_event(db_event)
            cancelled_count += 1
        
        return cancelled_count
    
    def _build_events_key_map(self, events: List[Event]) -> Dict[Tuple[str, str, str], Event]:
        """Build a lookup map of events by their match key."""
        return {self._create_match_key(event): event for event in events}
    
    def _is_event_still_active(
        self, 
        db_event: Dict, 
        current_event_ids: Set[str], 
        current_events_by_key: Dict
    ) -> bool:
        """Check if a database event still exists in current API data."""
        if db_event["id"] in current_event_ids:
            return True
        
        db_key = self._create_match_key_from_dict(db_event)
        return db_key in current_events_by_key
    
    def _remove_cancelled_event(self, db_event: Dict) -> None:
        """Remove a cancelled event from calendar and database."""
        if db_event["calendar_event_id"]:
            self.calendar.delete_event(db_event["calendar_event_id"])
        self.events.delete(db_event["id"])
    
    def _create_event_from_match(self, match_data: Dict, source: EventSource) -> Optional[Event]:
        try:
            # Parse datetime
            scheduled_date = match_data.get("ScheduledDate")
            start_time = convert_to_local_timezone(scheduled_date, self.timezone)
            end_time = start_time + DEFAULT_MATCH_DURATION
            
            # Get player information
            player1_id = match_data.get("Player1ID")
            player2_id = match_data.get("Player2ID")
            
            player1 = self.api.fetch_player(player1_id) if player1_id else None
            player2 = self.api.fetch_player(player2_id) if player2_id else None
            
            # Create title
            player1_name = player1.display_name if player1 else f"Player {player1_id}"
            player2_name = player2.display_name if player2 else f"Player {player2_id}"
            title = f"{player1_name} vs {player2_name}"
            
            # Get round information
            round_name = None
            if match_data.get("EventID") and match_data.get("Round"):
                round_name = self.api.fetch_round_name(
                    match_data["EventID"], 
                    match_data["Round"]
                )
                if round_name and round_name != "Unknown Round":
                    title += f" ({round_name})"
            
            # Get tournament name
            tournament_name = None
            if match_data.get("EventID"):
                tournament_name = self.api.fetch_tournament_name(match_data["EventID"])
            
            # Create event based on source type
            match_id = match_data.get("ID")
            if source == EventSource.HEAD_TO_HEAD:
                event = Event.create_h2h_event(
                    match_id=match_id,
                    title=title,
                    start=start_time,
                    end=end_time,
                    tournament=tournament_name,
                )
            else:
                event = Event.create_individual_event(
                    match_id=match_id,
                    title=title,
                    start=start_time,
                    end=end_time,
                    tournament=tournament_name,
                )
            
            # Add additional metadata
            event.player1_id = player1_id
            event.player2_id = player2_id
            event.player1_name = player1_name
            event.player2_name = player2_name
            event.event_id = match_data.get("EventID")
            event.round_name = round_name
            
            return event

        except APIUnavailableError:
            # Must not be swallowed: a skipped event is absent from the sync's event
            # list, which the cleanup pass would read as "cancelled" and delete from
            # the calendar.
            raise
        except Exception as e:
            return None
    
    def _create_match_key(self, event: Event) -> Tuple[str, str, str]:
        """Create a key for smart matching of events."""
        # Remove round info and H2H prefix for matching
        clean_title = event.title.replace("H2H: ", "")
        if "(" in clean_title:
            clean_title = clean_title.split("(")[0].strip()
        
        return (
            clean_title,
            event.tournament or "",
            event.start.date().isoformat(),
        )
    
    def _create_match_key_from_dict(self, event_dict: Dict) -> Tuple[str, str, str]:
        """Create a key for smart matching from dictionary data."""
        # Remove round info and H2H prefix for matching
        clean_title = event_dict["title"].replace("H2H: ", "")
        if "(" in clean_title:
            clean_title = clean_title.split("(")[0].strip()
        
        start_date = event_dict["start"][:10]  # Get date part only
        
        return (
            clean_title,
            event_dict["tournament"] or "",
            start_date,
        )