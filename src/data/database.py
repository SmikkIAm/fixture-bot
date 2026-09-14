from typing import List, Optional, Dict, Any
import sqlite3
from datetime import datetime

from ..models.event import Event, EventSource
from ..services.database_service import DatabaseService

class EventDatabase:
    def __init__(self, database_service: DatabaseService):
        self.db = database_service
    
    def save(self, event: Event, calendar_event_id: Optional[str] = None) -> None:
        if calendar_event_id:
            event.calendar_event_id = calendar_event_id
        
        query = '''
            INSERT OR REPLACE INTO events (
                id, title, start, end, source, calendar_event_id, tournament,
                player1_id, player2_id, player1_name, player2_name, 
                event_id, round_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        params = (
            event.id,
            event.title,
            event.start.isoformat(),
            event.end.isoformat(),
            event.source.value,
            event.calendar_event_id,
            event.tournament,
            event.player1_id,
            event.player2_id,
            event.player1_name,
            event.player2_name,
            event.event_id,
            event.round_name,
        )
        
        self.db.execute_query(query, params)
    
    def find_by_id(self, event_id: str) -> Optional[Event]:
        query = "SELECT * FROM events WHERE id = ?"
        results = self.db.execute_query(query, (event_id,), fetch=True)
        
        if not results:
            return None
        
        return self._row_to_event(results[0])
    
    def update(self, event: Event) -> None:
        query = '''
            UPDATE events SET
                title = ?, start = ?, end = ?, source = ?, calendar_event_id = ?,
                tournament = ?, player1_id = ?, player2_id = ?, player1_name = ?,
                player2_name = ?, event_id = ?, round_name = ?
            WHERE id = ?
        '''
        
        params = (
            event.title,
            event.start.isoformat(),
            event.end.isoformat(),
            event.source.value,
            event.calendar_event_id,
            event.tournament,
            event.player1_id,
            event.player2_id,
            event.player1_name,
            event.player2_name,
            event.event_id,
            event.round_name,
            event.id,
        )
        
        self.db.execute_query(query, params)
    
    def delete(self, event_id: str) -> bool:
        if not self.exists(event_id):
            return False
        
        query = "DELETE FROM events WHERE id = ?"
        self.db.execute_query(query, (event_id,))
        return True
    
    def exists(self, event_id: str) -> bool:
        query = "SELECT 1 FROM events WHERE id = ? LIMIT 1"
        results = self.db.execute_query(query, (event_id,), fetch=True)
        return len(results) > 0
    
    def get_all(self) -> List[Event]:
        query = '''
            SELECT id, title, start, end, tournament, source, 
                   calendar_event_id, created_at, updated_at,
                   player1_id, player2_id, player1_name, player2_name, 
                   event_id, round_name
            FROM events 
            ORDER BY start
        '''
        
        try:
            results = self.db.execute_query(query, fetch=True)
            return [self._row_to_event(row) for row in results]
            
        except Exception as e:
            raise Exception(f"Error getting all events: {e}")

    def get_all_with_calendar_ids(self) -> List[Dict[str, Any]]:
        query = '''
            SELECT id, title, calendar_event_id, start, tournament, source
            FROM events 
            WHERE source IN (?, ?)
            ORDER BY start
        '''
        params = (EventSource.INDIVIDUAL.value, EventSource.HEAD_TO_HEAD.value)
        results = self.db.execute_query(query, params, fetch=True)
        
        return [dict(row) for row in results]
    
    
    def get_upcoming_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                id, title, start, end, tournament, source, 
                calendar_event_id, created_at, updated_at,
                player1_name, player2_name, round_name
            FROM events 
            WHERE datetime(start) >= datetime('now')
            ORDER BY start ASC
            LIMIT ?
        """
        
        try:
            result = self.db.execute_query(query, (limit,), fetch=True)
            events = []
            
            for row in result:
                events.append({
                    'id': row[0],
                    'title': row[1],
                    'start': row[2],
                    'end': row[3],
                    'tournament': row[4],
                    'source': row[5],
                    'calendar_event_id': row[6],
                    'created_at': row[7],
                    'updated_at': row[8],
                    'player1_name': row[9],
                    'player2_name': row[10],
                    'round_name': row[11]
                })
            
            return events
            
        except Exception as e:
            raise Exception(f"Error getting upcoming events: {e}")
    
    def _row_to_event(self, row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            title=row["title"],
            start=datetime.fromisoformat(row["start"]),
            end=datetime.fromisoformat(row["end"]),
            source=EventSource(row["source"]),
            tournament=row["tournament"],
            calendar_event_id=row["calendar_event_id"],
            player1_id=row["player1_id"],
            player2_id=row["player2_id"],
            player1_name=row["player1_name"],
            player2_name=row["player2_name"],
            event_id=row["event_id"],
            round_name=row["round_name"],
        )