from typing import Dict, Any, Optional
from datetime import datetime

from ..models.event import Event

class CalendarService:
    
    def __init__(self, calendar_id: str, service_account_file: str):
        """
        Initialize the calendar service.
        
        Service initialization is deferred until first use to avoid unnecessary
        Google API overhead during configuration validation or help commands.
        """
        self.calendar_id = calendar_id
        self.service_account_file = service_account_file
        self._service = None
        
        if not calendar_id:
            raise ValueError("Calendar ID is required")
        
        if not service_account_file:
            raise ValueError("Service account file is required")
    
    @property
    def service(self):
        """
        Lazy initialization of Google Calendar service.
        
        Defers API authentication until first calendar operation, improving
        startup time and avoiding credential errors for non-calendar commands.
        """
        if self._service is None:
            try:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
                
                credentials = service_account.Credentials.from_service_account_file(
                    self.service_account_file,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                
                # Disable discovery cache to avoid oauth2client warning
                self._service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)
                
            except ImportError as e:
                raise ImportError(
                    "Google API client libraries not installed. "
                    "Install with: pip install google-api-python-client google-auth"
                )
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Service account file not found: {self.service_account_file}"
                )
            except Exception as e:
                raise Exception(f"Failed to initialize calendar service: {str(e)}")
        
        return self._service
    
    def add_event(self, event: Event) -> str:
        try:
            calendar_event = event.to_calendar_event()
            
            result = self.service.events().insert(
                calendarId=self.calendar_id,
                body=calendar_event
            ).execute()
            
            calendar_event_id = result.get('id')
            if not calendar_event_id:
                raise Exception("No event ID returned from calendar")
            
            return calendar_event_id
            
        except Exception as e:
            raise Exception(f"Failed to create calendar event: {str(e)}")
    
    def update_event(self, calendar_event_id: str, event: Event) -> bool:
        try:
            calendar_event = event.to_calendar_event()
            
            self.service.events().update(
                calendarId=self.calendar_id,
                eventId=calendar_event_id,
                body=calendar_event
            ).execute()
            
            return True
            
        except Exception as e:
            return False
    
    def delete_event(self, calendar_event_id: str) -> bool:
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=calendar_event_id
            ).execute()
            
            return True
            
        except Exception as e:
            return False
    
    def get_event(self, calendar_event_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=calendar_event_id
            ).execute()
            
            return result
            
        except Exception as e:
            return None
    
    def event_exists(self, calendar_event_id: str) -> bool:
        return self.get_event(calendar_event_id) is not None
    
    def test_connection(self) -> bool:
        try:
            # Try to get calendar metadata
            calendar = self.service.calendars().get(calendarId=self.calendar_id).execute()
            return True
            
        except Exception as e:
            return False