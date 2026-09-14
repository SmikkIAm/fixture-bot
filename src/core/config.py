import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .constants import DEFAULT_TIMEZONE, MAX_RETRIES, MIN_REQUEST_INTERVAL

@dataclass
class APIConfig:
    timeout: int = 30
    cache_ttl: int = 3600  # 1 hour
    custom_headers: Optional[Dict[str, str]] = None
    max_retries: int = MAX_RETRIES
    min_request_interval: float = MIN_REQUEST_INTERVAL


@dataclass
class GoogleCalendarConfig:
    calendar_id: str
    service_account_file: str


@dataclass
class DatabaseConfig:
    path: str = "events.db"


@dataclass
class Config:
    individual_players: Dict[str, int]
    h2h_players: Dict[str, int]
    google_calendar: GoogleCalendarConfig
    database: DatabaseConfig
    api: APIConfig
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(levelname)s - %(message)s"
    custom_headers: Optional[Dict[str, str]] = None
    timezone: str = DEFAULT_TIMEZONE
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        if config_path is None:
            config_path = "config.json"
        
        config_data = {
            "individual_players": {},
            "h2h_players": {},
            "google_calendar": {
                "calendar_id": "",
                "service_account_file": "your-service-account-file.json"
            },
            "database": {
                "path": "events.db"
            },
            "api": {
                "timeout": 30,
                "cache_ttl": 3600
            },
            "log_level": "INFO",
            "log_format": "%(asctime)s - %(levelname)s - %(message)s",
            "timezone": DEFAULT_TIMEZONE
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    config_data.update(file_config)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config from {config_path}: {e}")
        
        if os.getenv("GOOGLE_CAL_ID"):
            config_data["google_calendar"]["calendar_id"] = os.getenv("GOOGLE_CAL_ID")
        
        if os.getenv("SERVICE_ACCOUNT_FILE"):
            config_data["google_calendar"]["service_account_file"] = os.getenv("SERVICE_ACCOUNT_FILE")
            
        if os.getenv("DATABASE_PATH"):
            config_data["database"]["path"] = os.getenv("DATABASE_PATH")
            
        if os.getenv("API_TIMEOUT"):
            config_data["api"]["timeout"] = int(os.getenv("API_TIMEOUT"))
            
        if os.getenv("CACHE_TTL"):
            config_data["api"]["cache_ttl"] = int(os.getenv("CACHE_TTL"))

        if os.getenv("API_MAX_RETRIES"):
            config_data["api"]["max_retries"] = int(os.getenv("API_MAX_RETRIES"))

        if os.getenv("API_MIN_REQUEST_INTERVAL"):
            config_data["api"]["min_request_interval"] = float(
                os.getenv("API_MIN_REQUEST_INTERVAL")
            )
            
        if os.getenv("LOG_LEVEL"):
            config_data["log_level"] = os.getenv("LOG_LEVEL")
            
        if os.getenv("LOG_FORMAT"):
            config_data["log_format"] = os.getenv("LOG_FORMAT")

        if os.getenv("TIMEZONE"):
            config_data["timezone"] = os.getenv("TIMEZONE")
        
        individual_players_env = os.getenv("INDIVIDUAL_PLAYERS")
        if individual_players_env:
            try:
                config_data["individual_players"] = json.loads(individual_players_env)
            except json.JSONDecodeError:
                print("Warning: Invalid JSON in INDIVIDUAL_PLAYERS environment variable")
                
        h2h_players_env = os.getenv("H2H_PLAYERS")
        if h2h_players_env:
            try:
                config_data["h2h_players"] = json.loads(h2h_players_env)
            except json.JSONDecodeError:
                print("Warning: Invalid JSON in H2H_PLAYERS environment variable")
        
        custom_headers = dict(config_data["api"].get("custom_headers", {}) or {})
        if os.getenv("API_CUSTOM_HEADERS"):
            try:
                env_headers = json.loads(os.getenv("API_CUSTOM_HEADERS"))
                if isinstance(env_headers, dict):
                    custom_headers.update(env_headers)
                else:
                    print("Warning: API_CUSTOM_HEADERS must be a JSON object")
            except json.JSONDecodeError:
                print("Warning: Invalid JSON in API_CUSTOM_HEADERS environment variable")

        config_data["api"]["custom_headers"] = custom_headers
        
        return cls(
            individual_players=config_data["individual_players"],
            h2h_players=config_data["h2h_players"],
            google_calendar=GoogleCalendarConfig(**config_data["google_calendar"]),
            database=DatabaseConfig(**config_data["database"]),
            api=APIConfig(**config_data["api"]),
            log_level=config_data["log_level"],
            log_format=config_data["log_format"],
            custom_headers=custom_headers,
            timezone=config_data["timezone"]
        )
    
    
    def validate(self) -> None:
        if not self.google_calendar.calendar_id:
            raise ValueError("Google Calendar ID is required")
            
        if not self.google_calendar.service_account_file:
            raise ValueError("Service account file is required")
            
        if not os.path.exists(self.google_calendar.service_account_file):
            raise ValueError(f"Service account file not found: {self.google_calendar.service_account_file}")
            
        if not self.individual_players and not self.h2h_players:
            raise ValueError("At least one individual player or H2H player must be configured")

        headers = self.custom_headers or self.api.custom_headers or {}
        if not headers.get("X-Requested-By"):
            raise ValueError(
                "X-Requested-By header is required for snooker.org API access. "
                "Set it in api.custom_headers or API_CUSTOM_HEADERS."
            )

        # Fail here rather than letting every event silently get the wrong start time.
        from ..utils.datetime_utils import resolve_timezone
        resolve_timezone(self.timezone)
    
    def get_filtered_h2h_players(self) -> Dict[str, int]:
        return {
            name: player_id for name, player_id in self.h2h_players.items()
            if name not in self.individual_players
        }