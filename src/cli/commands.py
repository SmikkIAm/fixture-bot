import sys
import os
import logging
from typing import Dict, Tuple

from ..core.config import Config
from ..services.api_service import APIService
from ..services.calendar_service import CalendarService
from ..services.database_service import DatabaseService
from ..services.event_service import EventService
from ..data.database import EventDatabase
from .output import OutputFormatter


class CLICommands:
    def __init__(self, config: Config, config_file: str = "config.json"):
        self.config = config
        self.config_file = config_file
        self.output = OutputFormatter()
        self._event_service = None
    
    def _validate_config(self) -> bool:
        individual_count = len(self.config.individual_players) if self.config.individual_players else 0
        h2h_count = len(self.config.h2h_players) if self.config.h2h_players else 0
        
        if individual_count == 0 and h2h_count < 2:
            return False
        
        if not self.config.google_calendar.service_account_file or self.config.google_calendar.service_account_file == "your-service-account-file.json":
            return False
        
        if not self.config.google_calendar.calendar_id or self.config.google_calendar.calendar_id == "your-calendar-id@group.calendar.google.com":
            return False
        
        headers = self.config.custom_headers or self.config.api.custom_headers or {}
        if "X-Requested-By" not in headers or not headers["X-Requested-By"]:
            return False
        return True
    
    @property
    def event_service(self) -> EventService:

        if self._event_service is None:
            try:
                api_service = APIService(
                    self.config.api.timeout,
                    self.config.custom_headers,
                    max_retries=self.config.api.max_retries,
                    min_request_interval=self.config.api.min_request_interval,
                )
                calendar_service = CalendarService(
                    self.config.google_calendar.calendar_id,
                    self.config.google_calendar.service_account_file
                )
                database_service = DatabaseService(self.config.database.path)
                database_service.initialize_database()
                event_db = EventDatabase(database_service)
                
                self._event_service = EventService(
                    api_service=api_service,
                    calendar_service=calendar_service,
                    database_service=database_service,
                    event_repository=event_db,
                    timezone=self.config.timezone,
                )
                
            except Exception as e:
                raise Exception(f"Service initialization failed: {str(e)}")
        
        return self._event_service
    
    def sync(self) -> int:
        try:
            if not self._validate_config():
                self.output.print_error(
                    "Configuration Error",
                    "Your config file contains template values. Please edit your config file with actual values before running sync."
                )
                return 1
            
            self.output.print_header("SPORT CALENDAR SYNC")
            
            self.config.validate()
            h2h_players = self.config.get_filtered_h2h_players()
            
            self.output.print_player_tracking_info(
                len(self.config.individual_players),
                len(h2h_players)
            )
            
            added, updated, cancelled = self.event_service.sync_events(
                self.config.individual_players,
                h2h_players
            )
            
            self.output.print_sync_summary(added, updated, cancelled)
            
            return 0
            
        except Exception as e:
            self.output.print_error("Sync Error", str(e))
            return 1
    
    def check_api(self) -> int:
        try:
            self.config.validate()

            self.output.print_header("SPORT CALENDAR CHECK API")
            
            h2h_players = self.config.get_filtered_h2h_players()
            
            self.output.print_player_tracking_info(
                len(self.config.individual_players),
                len(h2h_players)
            )
            
            would_add, would_update, would_cancel = self.event_service.get_detailed_check_events(
                self.config.individual_players,
                h2h_players
            )

            self.output.print_detailed_check_summary(would_add, would_update, would_cancel)
            
            return 0
            
        except Exception as e:
            self.output.print_error("Check Error", str(e))
            return 1
    
    def check_db(self) -> int:
        try:
            self.output.print_header("SPORT CALENDAR CHECK DATABASE")

            database_service = DatabaseService(self.config.database.path)
            database_service.initialize_database()
            event_db = EventDatabase(database_service)

            self.output.print_section("Next Upcoming Matches")
            try:
                upcoming_events = event_db.get_upcoming_events(limit=5)
                if upcoming_events:
                    self.output.print_upcoming_matches(upcoming_events)
                else:
                    print("  No upcoming matches found in database.")
                    print("  Run 'sync' command to fetch and add events.\n")
            except Exception as e:
                print("  Unable to retrieve upcoming matches.")
                print("  No database connection.\n")
            
            return 0
            
        except Exception as e:
            self.output.print_error("Status Error", str(e))
            return 1
    
    def test_connections(self) -> int:
        try:
            self.output.print_header("CONNECTION TESTS")

            self.output.print_section("Testing API Connection")
            try:
                api_service = APIService(
                    self.config.api.timeout,
                    self.config.custom_headers,
                    max_retries=self.config.api.max_retries,
                    min_request_interval=self.config.api.min_request_interval,
                )
                matches = api_service.fetch_upcoming_matches()
                if matches is not None:
                    self.output.print_success(f"API connection successful - {len(matches)} matches found")
                else:
                    self.output.print_warning("API connection succeeded but returned no data")
            except Exception as e:
                self.output.print_error("API Connection Failed", str(e))
                return 1
            
            # Test calendar connection
            self.output.print_section("Testing Calendar Connection")
            try:
                calendar_service = CalendarService(
                    self.config.google_calendar.calendar_id,
                    self.config.google_calendar.service_account_file
                )
                if calendar_service.test_connection():
                    self.output.print_success("Calendar connection successful")
                else:
                    self.output.print_error("Calendar Connection Failed", "Unable to connect to Google Calendar")
                    return 1
            except Exception as e:
                self.output.print_error("Calendar Connection Failed", str(e))
                return 1

            self.output.print_section("Testing Database Connection")
            try:
                db_service = DatabaseService(self.config.database.path)
                db_info = db_service.get_database_info()
                if "error" in db_info:
                    self.output.print_error("Database Connection Failed", db_info["error"])
                    return 1
                else:
                    self.output.print_success(f"Database connection successful - {db_info.get('events_count', 0)} events")
            except Exception as e:
                self.output.print_error("Database Connection Failed", str(e))
                return 1
            
            self.output.print_success("All connections successful!")
            return 0
            
        except Exception as e:
            self.output.print_error("Connection Test Error", str(e))
            return 1
    

    def clear_database(self) -> int:
        try:
            self.output.print_header("CLEARING DATABASE")
            
            database_service = DatabaseService(self.config.database.path)
            database_service.initialize_database()
            event_db = EventDatabase(database_service)
            
            all_events = event_db.get_all()
            event_count = len(all_events)
            
            if event_count == 0:
                self.output.print_info("Database is already empty")
                return 0
            
            print(f"\nWARNING: This will delete {event_count} events from the database.")
            print("   Calendar events will NOT be deleted from Google Calendar.")
            response = input("\nAre you sure you want to continue? (yes/no): ")
            
            if response.lower() not in ['yes', 'y']:
                print("\nOperation cancelled")
                return 0
            
            for event in all_events:
                event_db.delete(event.id)
            
            self.output.print_success(f"Database cleared - removed {event_count} events")
            
            return 0
            
        except Exception as e:
            self.output.print_error("Database Clear Error", str(e))
            return 1
    
    def show_help(self) -> int:
        help_text = """
SportCalendarTGBot - Snooker Calendar Sync Tool
USAGE:
    python main.py --user [USERNAME] [COMMAND]
    python main.py [COMMAND]

OPTIONS:
    --user USERNAME     Use config from users/[USERNAME]/config.json

COMMANDS:
    test            Test API and calendar connections
    check-api       Check API and preview changes without making them
    sync            Perform full synchronization (default)
    check-db        Check database and show upcoming matches
    clear-db        Clear all events from database
    help            Show this help message

CONFIGURATION:
    1. Copy users/default/ folder to users/[USERNAME]/
    2. Edit users/[USERNAME]/config.json with your actual values
    3. Add your Google Calendar service account JSON file
    4. Run: python main.py --user [USERNAME] sync

For more information, see the README.md file.
"""
        print(help_text)
        return 0


def main() -> int:
    try:
        # Determine which config file to use
        config_file = "config.json"  # Default
        args = sys.argv[1:]  # Copy args for manipulation
        
        # Check for --user argument
        user_index = -1
        for i, arg in enumerate(args):
            if arg == "--user" and i + 1 < len(args):
                username = args[i + 1]
                config_file = f"users/{username}/config.json"
                user_index = i
                break
        
        # Remove --user and its value from args
        if user_index >= 0:
            args = args[:user_index] + args[user_index + 2:]
        
        elif os.path.exists("users/default/config.json"):
            # Use default config as template
            config_file = "users/default/config.json"
        
        # Load configuration
        config = Config.load(config_file)

        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format=config.log_format,
        )

        # Create CLI handler
        cli = CLICommands(config, config_file)
        
        # Parse command line arguments
        if len(args) > 0:
            command = args[0].lower()
            
            if command == "sync":
                return cli.sync()
            elif command == "sync-events":
                return cli.sync()
            elif command in ["check-api", "check_api"]:
                return cli.check_api()
            elif command in ["check-db", "check_db"]:
                return cli.check_db()
            elif command == "test":
                return cli.test_connections()
            elif command in ["clear-db", "clear_db", "clear-database", "clear_database"]:
                return cli.clear_database()
            elif command in ["help", "-h", "--help"]:
                return cli.show_help()
            else:
                print(f"Unknown command: {command}")
                print("Use 'help' to see available commands.")
                return 1
        else:
            # Default command is sync
            return cli.sync()
            
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
