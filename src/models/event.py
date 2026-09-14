from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import json

class EventSource(Enum):
    INDIVIDUAL = "snooker"
    HEAD_TO_HEAD = "snooker-h2h"


@dataclass
class Event:
    id: str
    title: str
    
    start: datetime
    end: datetime

    source: EventSource

    tournament: Optional[str] = None
    calendar_event_id: Optional[str] = None
    
    player1_id: Optional[int] = None
    player2_id: Optional[int] = None
    player1_name: Optional[str] = None
    player2_name: Optional[str] = None
    
    event_id: Optional[int] = None
    round_name: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            raise ValueError("Event ID cannot be empty")
        
        if not self.title:
            raise ValueError("Event title cannot be empty")
        
        if self.start >= self.end:
            raise ValueError("Event start time must be before end time")
    
    @classmethod
    def create_individual_event(
        cls,
        match_id: int,
        title: str,
        start: datetime,
        end: datetime,
        tournament: Optional[str] = None,
        **kwargs
    ) -> "Event":
        return cls(
            id=f"snooker-{match_id}",
            title=title,
            start=start,
            end=end,
            source=EventSource.INDIVIDUAL,
            tournament=tournament,
            **kwargs
        )
    
    @classmethod
    def create_h2h_event(
        cls,
        match_id: int,
        title: str,
        start: datetime,
        end: datetime,
        tournament: Optional[str] = None,
        **kwargs
    ) -> "Event":
        return cls(
            id=f"h2h-{match_id}",
            title=title,
            start=start,
            end=end,
            source=EventSource.HEAD_TO_HEAD,
            tournament=tournament,
            **kwargs
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat() if isinstance(self.start, datetime) else self.start,
            "end": self.end.isoformat() if isinstance(self.end, datetime) else self.end,
            "source": self.source.value,
            "tournament": self.tournament,
            "calendar_event_id": self.calendar_event_id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "player1_name": self.player1_name,
            "player2_name": self.player2_name,
            "event_id": self.event_id,
            "round_name": self.round_name,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        start = data["start"]
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        
        end = data["end"]
        if isinstance(end, str):
            end = datetime.fromisoformat(end)

        source = data["source"]
        if isinstance(source, str):
            source = EventSource(source)
        
        return cls(
            id=data["id"],
            title=data["title"],
            start=start,
            end=end,
            source=source,
            tournament=data.get("tournament"),
            calendar_event_id=data.get("calendar_event_id"),
            player1_id=data.get("player1_id"),
            player2_id=data.get("player2_id"),
            player1_name=data.get("player1_name"),
            player2_name=data.get("player2_name"),
            event_id=data.get("event_id"),
            round_name=data.get("round_name"),
        )
    
    def to_calendar_event(self) -> Dict[str, Any]:
        calendar_title = self.title
        if self.tournament:
            calendar_title += f" — {self.tournament}"
        
        return {
            "summary": calendar_title,
            "start": {
                "dateTime": self.start.isoformat(),
                "timeZone": str(self.start.tzinfo) if self.start.tzinfo else "UTC",
            },
            "end": {
                "dateTime": self.end.isoformat(),
                "timeZone": str(self.end.tzinfo) if self.end.tzinfo else "UTC",
            },
            "description": f"Snooker match: {self.title}",
        }
    
    def has_changed(self, other: "Event") -> bool:
        fields_to_check = [
            "title",
            "start",
            "end",
            "tournament",
            "player1_id",
            "player2_id",
            "player1_name",
            "player2_name",
            "round_name",
        ]
        
        for field in fields_to_check:
            if getattr(self, field) != getattr(other, field):
                return True
        return False
    
    def __str__(self) -> str:
        return f"Event(id='{self.id}', title='{self.title}', start={self.start})"
    
    def __repr__(self) -> str:
        return (
            f"Event(id='{self.id}', title='{self.title}', "
            f"start={self.start}, end={self.end}, source={self.source}, "
            f"tournament='{self.tournament}')"
        )