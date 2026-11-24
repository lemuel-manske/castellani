BROWSER_SLOTS_TABLE = "capture_browser_slots"
FRONTIER_TABLE = "capture_frontier"
OUTBOX_TABLE = "capture_outbox"
RUNS_TABLE = "capture_runs"
SNAPSHOTS_TABLE = "capture_snapshots"
SESSIONS_TABLE = "capture_sessions"
SESSION_REQUESTS_TABLE = "capture_session_requests"

CAPTURE_TABLES = (
    FRONTIER_TABLE,
    RUNS_TABLE,
    SNAPSHOTS_TABLE,
    OUTBOX_TABLE,
    BROWSER_SLOTS_TABLE,
)

LOGIN_TABLES = (
    RUNS_TABLE,
    SESSIONS_TABLE,
    SESSION_REQUESTS_TABLE,
)
