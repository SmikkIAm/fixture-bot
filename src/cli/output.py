from typing import List, Dict, Any, Optional

from ..core.config import Config
from ..models.event import Event


class OutputFormatter:
    def print_header(self, text: str) -> None:
        print(f"\n{'='*60}")
        print(f"{text.center(60)}")
        print(f"{'='*60}\n")
    
    def print_section(self, text: str) -> None:
        print(f"\n{text}")
        print(f"{'-'*len(text)}")
    
    def print_success(self, message: str) -> None:
        print(f"✓ {message}")
    
    def print_error(self, title: str, message: str) -> None:
        print(f"\n✗ {title}: {message}\n")
    
    def print_warning(self, message: str) -> None:
        print(f"⚠ {message}")
    
    def print_info(self, message: str) -> None:
        print(f"ℹ {message}")
     
    def print_player_tracking_info(self, individual_count: int, h2h_count: int) -> None:
        self.print_section("PLAYER TRACKING")
        print(f"Individual players: {individual_count}")
        
        if h2h_count > 0:
            print(f"H2H players: {h2h_count} (excluding individual players)")
        else:
            print("H2H tracking: disabled - all H2H players are tracked individually")
    
    def print_sync_summary(self, added: int, updated: int, cancelled: int) -> None:
        self.print_section("SYNC RESULTS")
        print(f"Added: {added}, Updated: {updated}, Cancelled: {cancelled}")
        
        # Add some visual feedback
        if added + updated + cancelled == 0:
            self.print_info("No changes were made - all events are up to date.")
        else:
            self.print_success(f"Synchronization completed successfully!")
    
    def print_detailed_check_summary(self, would_add: List, would_update: List, would_cancel: List) -> None:
        self.print_section("CHECK RESULTS")
        
        total_changes = len(would_add) + len(would_update) + len(would_cancel)
        
        if would_add:
            print(f"\nWould ADD {len(would_add)} event(s):")
            for event in would_add:
                source_type = "H2H" if event.source.name == "HEAD_TO_HEAD" else "Individual"
                print(f"  • {event.title}")
                print(f"    {event.start.strftime('%m-%d %H:%M')} | {event.tournament} | {source_type}")
        
        if would_update:
            print(f"\nWould UPDATE {len(would_update)} event(s):")
            for event in would_update:
                source_type = "H2H" if event.source.name == "HEAD_TO_HEAD" else "Individual"
                print(f"  • {event.title}")
                print(f"    {event.start.strftime('%m-%d %H:%M')} | {event.tournament} | {source_type}")
        
        if would_cancel:
            print(f"\nWould CANCEL {len(would_cancel)} event(s):")
            for event in would_cancel:
                source_type = "H2H" if event.source.name == "HEAD_TO_HEAD" else "Individual"
                print(f"  • {event.title}")
                print(f"    {event.start.strftime('%m-%d %H:%M')} | {event.tournament} | {source_type}")
        
        # Summary
        if total_changes == 0:
            self.print_info("No changes needed - all events are up to date.")

    def print_upcoming_matches(self, upcoming_events: List[Dict[str, Any]]) -> None:
        if not upcoming_events:
            print("  No upcoming matches")
            return
        
        print(f"  Next {len(upcoming_events)} upcoming matches:")
        print()
        
        for i, event in enumerate(upcoming_events, 1):
            # Parse the start time for display
            from datetime import datetime
            try:
                if 'T' in event['start']:
                    start_time = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                else:
                    start_time = datetime.fromisoformat(event['start'])
                time_str = start_time.strftime("%m-%d %H:%M")
            except:
                time_str = event['start']
            
            source_display = "Individual" if event['source'] == "snooker" else "H2H"
            print(f"  {i:2}. {event['title']}")
            print(f"      {time_str} | {event['tournament']} | {source_display}")
            print()