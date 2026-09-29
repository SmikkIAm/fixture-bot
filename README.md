# Fixture Bot

A command-line tool that keeps a Google Calendar in sync with upcoming snooker matches from the
[snooker.org](https://api.snooker.org) API. You tell it which players to follow; it creates calendar
events for their upcoming matches, updates them when schedules shift, and removes them when matches
are cancelled.

## Features

- **Individual player tracking** — every upcoming match for the players you follow.
- **Head-to-head tracking** — events only for matches where two tracked players face each other.
- **Idempotent sync** — re-running never duplicates events. Existing entries are updated in place.
- **Cancellation handling** — matches that disappear from the API are deleted from the calendar.
- **Dry-run mode** — `check-api` previews every add / update / cancel without writing anything.
- **Multi-user** — independent config, calendar and database per user.
- **Local state in SQLite** — persists the match → calendar-event mapping between runs.
- **Timezone aware** — events are created in your configured zone, with daylight saving
  applied according to the date of each individual match.

## How it works

```
snooker.org API  ──►  APIService     filter to upcoming matches (Status 0, has a scheduled date),
                                     split into head-to-head vs individual, cache player /
                                     tournament / round lookups for the run
                          │
                          ▼
                      EventService   build Event objects, diff them against SQLite, then
                                     add / update / cancel as needed
                       ╱        ╲
                      ▼          ▼
            CalendarService   EventDatabase
           (Google Calendar)      (SQLite)
```

Each match gets a deterministic ID (`snooker-<match_id>` or `h2h-<match_id>`), which is what makes
re-runs idempotent. Because the upstream API sometimes reissues IDs, cancellation detection falls
back to a secondary match key of *(players, tournament, date)* before deciding an event is really
gone. Head-to-head matches are processed first so a match between two tracked players produces one
event rather than two.

## Requirements

- Python 3.11+ (developed and tested on 3.12)
- A Google Cloud **service account** with the Calendar API enabled
- A snooker.org API identifier for the `X-Requested-By` header ([their API](https://api.snooker.org)
  requires it and will reject requests without one)

## Setup

**1. Install dependencies**

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

**2. Create your user folder**

```bash
cp -r users/default users/<username>
```

**3. Add your Google credentials**

Create a service account in the Google Cloud Console, enable the Calendar API, download its JSON
key into `users/<username>/`, then **share your calendar with the service account's email address**
and give it "Make changes to events" permission. Without that sharing step the sync will
authenticate successfully but see an empty calendar.

**4. Edit `users/<username>/config.json`**

```json
{
  "individual_players": { "ronnie_osullivan": 1 },
  "h2h_players": { "player_one": 2, "player_two": 3 },
  "google_calendar": {
    "calendar_id": "your-calendar-id@group.calendar.google.com",
    "service_account_file": "users/<username>/your-key.json"
  },
  "database": { "path": "users/<username>/events.db" },
  "timezone": "Europe/Warsaw",
  "api": {
    "timeout": 30,
    "min_request_interval": 4,
    "max_retries": 3,
    "custom_headers": { "X-Requested-By": "YourSnookerOrgIdentifier" }
  }
}
```

Player IDs are snooker.org player IDs. Any player listed under `individual_players` is
automatically excluded from head-to-head pairing, since their matches are already tracked.

**5. Verify**

```bash
python main.py --user <username> test
```

## Usage

```bash
python main.py --user <username> <command>
```

| Command | Description |
| --- | --- |
| `test` | Check API, calendar and database connectivity |
| `check-api` | Preview pending adds / updates / cancellations without applying them |
| `sync` | Apply the full synchronization (default if no command is given) |
| `check-db` | Show the next upcoming matches stored locally |
| `clear-db` | Delete all local events (prompts for confirmation; leaves the calendar untouched) |
| `help` | Show usage information |

Omitting `--user` falls back to `users/default/config.json`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers datetime parsing across every API format, event and player model behaviour,
configuration loading and validation, the API filtering and pairing logic, match-key construction,
and the SQLite repository against a temporary database. It requires no network access or Google
credentials.

## Configuration via environment variables

Any config value can be overridden without editing the file, which is useful for scheduled runs
and CI:

| Variable | Overrides |
| --- | --- |
| `GOOGLE_CAL_ID` | `google_calendar.calendar_id` |
| `SERVICE_ACCOUNT_FILE` | `google_calendar.service_account_file` |
| `DATABASE_PATH` | `database.path` |
| `API_TIMEOUT` | `api.timeout` |
| `API_MAX_RETRIES` | `api.max_retries` |
| `API_MIN_REQUEST_INTERVAL` | `api.min_request_interval` |
| `TIMEZONE` | `timezone` |
| `API_CUSTOM_HEADERS` | `api.custom_headers` (JSON object) |
| `INDIVIDUAL_PLAYERS` | `individual_players` (JSON object) |
| `H2H_PLAYERS` | `h2h_players` (JSON object) |
| `LOG_LEVEL` / `LOG_FORMAT` | logging configuration |

## Project structure

```
main.py                     entry point
src/
├── cli/                    command dispatch and console output formatting
├── core/                   configuration loading and constants
├── data/                   EventDatabase — SQLite repository for events
├── models/                 Event and Player domain models
├── services/               API, Google Calendar, database and sync orchestration
└── utils/                  datetime parsing and timezone conversion
users/
└── default/                config template; copy this per user
```

The layering is deliberate: `services/` holds all I/O, `models/` stays free of external
dependencies, and `EventService` receives its collaborators via constructor injection so each
one can be substituted in tests.

## Rate limiting

snooker.org sits behind IIS dynamic IP restriction and answers bursts with `403`
(substatus 403.502) rather than `429`, so `403` is treated as retryable here. Three measures keep
a sync within the limit:

- **Throttling** — requests are spaced at least `api.min_request_interval` seconds apart
  (default 4).
- **Retry with exponential backoff** — a throttled request is retried up to `api.max_retries`
  times, waiting 5s, 10s then 20s.
- **Per-event round caching** — one request returns every round of a tournament, so it is
  fetched once per event rather than once per round.

If the limit is still hit after retries the run **aborts** rather than continuing with
placeholder names. This is deliberate: a title like `Neil Robertson vs Player 239` written to the
calendar would match the stored record on the next sync, so nothing would ever correct it. Failing
loudly and rerunning later leaves the calendar clean. A record that genuinely has no name is
different — that is a stable fact, so it falls back to a placeholder and the sync continues.

A sync is therefore deliberately unhurried; expect roughly four seconds per lookup.

## Roadmap

Today the tool covers snooker, through the CLI. Three extensions are planned but not yet implemented:

- **Multi-session matches** - support for matches played over several sessions is coming soon.
  Right now only the first session of a snooker match is added to the calendar.
- **Telegram bot interface** - the project is named for its intended end state: a bot front-end
  that lets you manage tracked players and receive match reminders from chat. The sync engine,
  storage layer and calendar integration are already built and working; the Telegram layer is
  designed to sit on top of the same engine the CLI drives today.
- **Additional sport APIs** - the pipeline is deliberately sport-agnostic apart from the
  snooker.org client. Other sports (football first) are intended to slot in as an additional
  service alongside `APIService`, reusing the existing event, calendar and storage layers
  unchanged.

## Notes and limitations

- Only the first session of a match is shown in the calendar. Longer matches played over
  several sessions get a single event for that first session; session support will be added soon.
- Match duration is assumed to be 3 hours, since the API publishes a start time but no end time.
- Match times are converted to the zone named by `timezone` in your config (default
  `Europe/Warsaw`), and daylight saving is applied per match date, so a match in July and one in
  January get the correct local time. An unrecognised zone is rejected at startup rather than
  quietly falling back to a fixed offset.
- The `tzdata` dependency is required on Windows, which ships no system timezone database.
- Google Calendar credentials are never read until a calendar operation actually runs, so
  `check-db` and `help` work without them.
- Service account keys and per-user data are gitignored; only `users/default/` is tracked.
