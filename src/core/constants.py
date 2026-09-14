from datetime import timedelta

DEFAULT_TIMEZONE = "Europe/Warsaw"
UTC_TIMEZONE = "UTC"

DEFAULT_MATCH_DURATION = timedelta(hours=3)
EVENT_ID_PREFIX_INDIVIDUAL = "snooker"
EVENT_ID_PREFIX_H2H = "h2h"

API_TIMEOUT = 30  # seconds
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SNOOKER_API_BASE_URL = "https://api.snooker.org"

# snooker.org sits behind IIS dynamic IP restriction, which answers bursts with
# 403 (substatus 403.502) rather than 429, so 403 is treated as retryable here.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0
RETRY_STATUS_CODES = (403, 429, 500, 502, 503, 504)
MIN_REQUEST_INTERVAL = 4.0  # minimum seconds between API calls

DEFAULT_DB_PATH = "events.db"
DB_POOL_SIZE = 5

EVENT_SOURCE_INDIVIDUAL = "snooker"
EVENT_SOURCE_H2H = "snooker-h2h"

API_ENDPOINT_MATCHES = "/?t=14&tr=main"
API_ENDPOINT_PLAYER = "/?p={player_id}"
API_ENDPOINT_EVENT = "/?e={event_id}"
API_ENDPOINT_ROUNDS = "/?t=12&e={event_id}"

HEADER_WIDTH = 60
MAX_DISPLAYED_EVENTS = 5
MAX_DISPLAYED_NEW_EVENTS = 3
