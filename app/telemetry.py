import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def get_bucharest_time() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Bucharest"))
    except Exception:
        now_utc = datetime.now(timezone.utc)
        year = now_utc.year
        dst_start = datetime(year, 3, 31, 1, tzinfo=timezone.utc)
        dst_start = dst_start - timedelta(days=(dst_start.weekday() + 1) % 7)
        dst_end = datetime(year, 10, 31, 1, tzinfo=timezone.utc)
        dst_end = dst_end - timedelta(days=(dst_end.weekday() + 1) % 7)
        if dst_start <= now_utc < dst_end:
            tz = timezone(timedelta(hours=3))
        else:
            tz = timezone(timedelta(hours=2))
        return now_utc.astimezone(tz)

DB_PATH = Path(__file__).resolve().parent / "telemetry.db"
MAX_QUERY_LENGTH = 500
MAX_DETAIL_STRING_LENGTH = 1000
MAX_SERVER_METRIC_ROWS = 500
SERVER_METRIC_MIN_INTERVAL_SECONDS = 60
SENSITIVE_DETAIL_KEYS = {"authorization", "cookie", "request_headers", "headers", "set-cookie"}
SENSITIVE_DETAIL_SUBSTRINGS = ("cookie", "authorization", "token", "secret", "password", "websocket-key")
_last_server_metrics_at = 0.0

def generate_random_username(user_id: str) -> str:
    import hashlib

    h = int(hashlib.sha256(user_id.encode()).hexdigest(), 16)
    num = h % 10000
    return f"guest_{num}"

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            random_username TEXT UNIQUE,
            last_ip TEXT,
            created_at TEXT
        )
    """)
    
    # Create logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            ip TEXT,
            event_type TEXT,
            query TEXT,
            details TEXT,
            timestamp TEXT
        )
    """)
    
    # Create server_metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpu_percent REAL,
            ram_percent REAL,
            active_sessions INTEGER,
            timestamp TEXT
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_event_type ON logs(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_server_metrics_timestamp ON server_metrics(timestamp)")
    
    conn.commit()
    conn.close()

def get_user_username(user_id: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT random_username FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def has_custom_username(user_id: str) -> bool:
    username = get_user_username(user_id)
    if not username:
        return False
    return username != generate_random_username(user_id)

def check_username_exists(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE random_username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_user_id_by_username(username: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE random_username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def update_user_username(user_id: str, username: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = get_bucharest_time().isoformat()
    cursor.execute("SELECT user_id FROM users WHERE random_username = ?", (username,))
    existing = cursor.fetchone()
    if existing and existing[0] != user_id:
        cursor.execute("UPDATE logs SET user_id = ? WHERE user_id = ?", (user_id, existing[0]))
        cursor.execute("DELETE FROM users WHERE user_id = ?", (existing[0],))

    cursor.execute(
        """
        INSERT INTO users (user_id, random_username, last_ip, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET random_username = excluded.random_username
        """,
        (user_id, username, "", now_str),
    )
    conn.commit()
    conn.close()


def merge_user_identity(old_user_id: str | None, new_user_id: str, username: str, ip: str) -> None:
    """Move temporary guest telemetry onto the authenticated student identity."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = get_bucharest_time().isoformat()

    if old_user_id and old_user_id != new_user_id:
        cursor.execute(
            "UPDATE logs SET user_id = ? WHERE user_id = ?",
            (new_user_id, old_user_id),
        )
        cursor.execute(
            "DELETE FROM users WHERE user_id = ? AND random_username != ?",
            (old_user_id, "Admin"),
        )

    cursor.execute("SELECT user_id FROM users WHERE random_username = ?", (username,))
    existing = cursor.fetchone()
    if existing and existing[0] != new_user_id:
        cursor.execute("UPDATE logs SET user_id = ? WHERE user_id = ?", (new_user_id, existing[0]))
        cursor.execute("DELETE FROM users WHERE user_id = ?", (existing[0],))

    cursor.execute(
        """
        INSERT INTO users (user_id, random_username, last_ip, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            random_username = excluded.random_username,
            last_ip = excluded.last_ip
        """,
        (new_user_id, username, ip, now_str),
    )
    conn.commit()
    conn.close()


def delete_user_by_username(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE random_username = ?", (username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    cursor.execute("DELETE FROM users WHERE random_username = ?", (username,))
    cursor.execute("DELETE FROM logs WHERE user_id = ?", (row[0],))
    conn.commit()
    conn.close()
    return True


def delete_guest_users() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE random_username != ?", ("Admin",))
    deleted_count = cursor.fetchone()[0]
    cursor.execute("DELETE FROM users WHERE random_username != ?", ("Admin",))
    cursor.execute("DELETE FROM logs WHERE user_id NOT IN (SELECT user_id FROM users)")
    conn.commit()
    conn.close()
    return deleted_count

def cleanup_inactive_users(hours: float = 2.0) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get the time threshold (Bucharest time)
    threshold = (get_bucharest_time() - timedelta(hours=hours)).isoformat()
    
    # Find all users (except Admin) who:
    # 1. Have no logs in the last 'hours' hours
    # 2. And whose created_at is older than the threshold
    cursor.execute("""
        SELECT user_id FROM users 
        WHERE random_username != 'Admin'
          AND (
              created_at < ? 
              AND user_id NOT IN (
                  SELECT DISTINCT user_id FROM logs WHERE timestamp >= ?
              )
          )
    """, (threshold, threshold))
    
    inactive_user_ids = [row[0] for row in cursor.fetchall()]
    
    deleted_count = 0
    if inactive_user_ids:
        # Delete from users (freeing up their usernames)
        placeholders = ",".join("?" for _ in inactive_user_ids)
        cursor.execute(f"DELETE FROM users WHERE user_id IN ({placeholders})", inactive_user_ids)
        deleted_count = cursor.rowcount
        conn.commit()
        
    conn.close()
    return deleted_count

def get_or_create_user(user_id: str, ip: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT random_username FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row:
        username = row[0]
        # Update IP
        cursor.execute("UPDATE users SET last_ip = ? WHERE user_id = ?", (ip, user_id))
        conn.commit()
    else:
        username = generate_random_username(user_id)
        now_str = get_bucharest_time().isoformat()
        cursor.execute(
            "INSERT INTO users (user_id, random_username, last_ip, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, ip, now_str)
        )
        conn.commit()
        
    conn.close()
    return username

def _is_sensitive_key(key: Any) -> bool:
    key_text = str(key).lower()
    return key_text in SENSITIVE_DETAIL_KEYS or any(part in key_text for part in SENSITIVE_DETAIL_SUBSTRINGS)


def _safe_detail_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _safe_detail_value(v)
            for k, v in value.items()
            if not _is_sensitive_key(k)
        }
    if isinstance(value, list):
        return [_safe_detail_value(item) for item in value[:25]]
    if isinstance(value, str):
        return value[:MAX_DETAIL_STRING_LENGTH]
    return value


def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    return _safe_detail_value(details)


def scrub_sensitive_log_details() -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, details FROM logs")
    updates = []
    for row_id, raw_details in cursor.fetchall():
        try:
            parsed = json.loads(raw_details)
        except Exception:
            continue
        sanitized = sanitize_details(parsed)
        if sanitized != parsed:
            updates.append((json.dumps(sanitized, ensure_ascii=False), row_id))

    if updates:
        cursor.executemany("UPDATE logs SET details = ? WHERE id = ?", updates)
        conn.commit()
    conn.close()
    return len(updates)


def log_event(user_id: str, ip: str, event_type: str, query: str, details: dict[str, Any]) -> None:
    # Ensure user exists and get username
    get_or_create_user(user_id, ip)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = get_bucharest_time().isoformat()
    details_str = json.dumps(sanitize_details(details), ensure_ascii=False)
    
    cursor.execute(
        "INSERT INTO logs (user_id, ip, event_type, query, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, ip, event_type, query[:MAX_QUERY_LENGTH], details_str, now_str)
    )
    conn.commit()
    conn.close()

def log_server_metrics(cpu: float, ram: float, active_sessions: int) -> None:
    global _last_server_metrics_at
    now = time.time()
    if now - _last_server_metrics_at < SERVER_METRIC_MIN_INTERVAL_SECONDS:
        return
    _last_server_metrics_at = now

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = get_bucharest_time().isoformat()
    cursor.execute(
        "INSERT INTO server_metrics (cpu_percent, ram_percent, active_sessions, timestamp) VALUES (?, ?, ?, ?)",
        (cpu, ram, active_sessions, now_str)
    )
    cursor.execute(
        """
        DELETE FROM server_metrics
        WHERE id NOT IN (
            SELECT id FROM server_metrics
            ORDER BY timestamp DESC
            LIMIT ?
        )
        """,
        (MAX_SERVER_METRIC_ROWS,),
    )
    conn.commit()
    conn.close()

# --- Query helpers for Dashboard ---

def get_dashboard_summary() -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total searches
    cursor.execute("SELECT COUNT(*) FROM logs WHERE event_type = 'search'")
    total_searches = cursor.fetchone()[0]
    
    # Total Q&A
    cursor.execute("SELECT COUNT(*) FROM logs WHERE event_type = 'qa'")
    total_qa = cursor.fetchone()[0]
    
    # Total quiz gens
    cursor.execute("SELECT COUNT(*) FROM logs WHERE event_type = 'quiz_gen'")
    total_quiz_gens = cursor.fetchone()[0]
    
    # Total submits
    cursor.execute("SELECT COUNT(*) FROM logs WHERE event_type = 'quiz_submit'")
    total_submits = cursor.fetchone()[0]
    
    # Total visits
    cursor.execute("SELECT COUNT(*) FROM logs WHERE event_type = 'visit'")
    total_visits = cursor.fetchone()[0]
    
    # Unique users
    cursor.execute("SELECT COUNT(*) FROM users")
    unique_users = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total_searches": total_searches,
        "total_qa": total_qa,
        "total_quiz_gens": total_quiz_gens,
        "total_submits": total_submits,
        "total_visits": total_visits,
        "unique_users": unique_users
    }

def get_top_users(limit: int = 10) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            u.random_username,
            u.last_ip,
            COUNT(l.id) as total_activities,
            SUM(CASE WHEN l.event_type = 'search' THEN 1 ELSE 0 END) as searches,
            SUM(CASE WHEN l.event_type = 'qa' THEN 1 ELSE 0 END) as qa,
            SUM(CASE WHEN l.event_type = 'quiz_gen' THEN 1 ELSE 0 END) as quiz_gens,
            SUM(CASE WHEN l.event_type = 'quiz_submit' THEN 1 ELSE 0 END) as quiz_submits,
            SUM(CASE WHEN l.event_type = 'visit' THEN 1 ELSE 0 END) as visits
        FROM users u
        LEFT JOIN logs l ON u.user_id = l.user_id
        GROUP BY u.user_id
        ORDER BY total_activities DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_activity(limit: int = 50) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            l.id,
            u.random_username,
            l.ip,
            l.event_type,
            l.query,
            l.details,
            l.timestamp
        FROM logs l
        JOIN users u ON l.user_id = u.user_id
        ORDER BY l.timestamp DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["details"] = json.loads(d["details"])
        except Exception:
            pass
        result.append(d)
    return result

def get_recent_server_metrics(limit: int = 50) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT cpu_percent, ram_percent, active_sessions, timestamp
        FROM server_metrics
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Initialize on import
init_db()
