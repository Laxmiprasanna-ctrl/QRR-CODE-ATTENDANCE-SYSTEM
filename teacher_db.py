"""
teacher_db.py
SQLite database layer for the Teacher Portal.
Tables: teachers, qr_sessions, teacher_attendance
Uses a separate teacher_portal.db so it does not touch the main SQL Server DB.
"""
import sqlite3
import os
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "teacher_portal.db")


# ── Connection helper ─────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row(cursor):
    r = cursor.fetchone()
    return dict(r) if r else None


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


# ── Init ──────────────────────────────────────────────────────────────────────
def init_teacher_db():
    """Create all tables and seed sample teachers."""
    conn = get_conn()
    c = conn.cursor()

    # Teachers table
    c.execute("""
        CREATE TABLE IF NOT EXISTS teachers (
            teacher_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            email        TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            subject      TEXT NOT NULL,
            department   TEXT NOT NULL DEFAULT 'General'
        )
    """)

    # QR Sessions table — one row per generated QR
    c.execute("""
        CREATE TABLE IF NOT EXISTS qr_sessions (
            session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id   INTEGER NOT NULL,
            subject      TEXT NOT NULL,
            date         TEXT NOT NULL,
            start_time   TEXT NOT NULL,
            end_time     TEXT NOT NULL,
            token        TEXT UNIQUE NOT NULL,
            qr_image     TEXT,
            is_active    INTEGER DEFAULT 1,
            FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
        )
    """)

    # Teacher attendance table — records when students scan teacher QR
    c.execute("""
        CREATE TABLE IF NOT EXISTS teacher_attendance (
            attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER NOT NULL,
            student_id    TEXT NOT NULL,
            student_name  TEXT NOT NULL,
            roll_no       TEXT DEFAULT '',
            department    TEXT DEFAULT '',
            date          TEXT NOT NULL,
            time          TEXT NOT NULL,
            status        TEXT DEFAULT 'Present',
            FOREIGN KEY (session_id) REFERENCES qr_sessions(session_id)
        )
    """)

    conn.commit()

    # Seed sample teachers if empty
    c.execute("SELECT COUNT(*) FROM teachers")
    if c.fetchone()[0] == 0:
        sample_teachers = [
            ("Dr. Ahmed Khan",    "ahmed@college.edu",   "teacher123", "Data Structures",      "Computer Science"),
            ("Prof. Sara Ali",    "sara@college.edu",    "teacher123", "Database Management",  "Information Technology"),
            ("Mr. Ravi Kumar",    "ravi@college.edu",    "teacher123", "Operating Systems",    "Computer Science"),
            ("Ms. Priya Sharma",  "priya@college.edu",   "teacher123", "Web Technologies",     "Information Technology"),
            ("Dr. John Smith",    "john@college.edu",    "teacher123", "Computer Networks",    "Electronics"),
        ]
        for name, email, pwd, subject, dept in sample_teachers:
            c.execute(
                "INSERT INTO teachers (name, email, password, subject, department) VALUES (?,?,?,?,?)",
                (name, email, generate_password_hash(pwd), subject, dept)
            )
        conn.commit()

    conn.close()


# ── Teacher Auth ──────────────────────────────────────────────────────────────
def authenticate_teacher(identifier, password):
    """Login with name OR email + password."""
    conn = get_conn()
    c    = conn.cursor()
    # Try email first, then name (case-insensitive)
    c.execute("SELECT * FROM teachers WHERE LOWER(email)=LOWER(?)", (identifier,))
    row = _row(c)
    if not row:
        c.execute("SELECT * FROM teachers WHERE LOWER(name)=LOWER(?)", (identifier,))
        row = _row(c)
    conn.close()
    if row and check_password_hash(row["password"], password):
        return row
    return None


def get_teacher(teacher_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM teachers WHERE teacher_id=?", (teacher_id,))
    result = _row(c)
    conn.close()
    return result


def get_all_teachers():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT teacher_id, name, email, subject, department FROM teachers ORDER BY name")
    result = _rows(c)
    conn.close()
    return result


def add_teacher(name, email, password, subject, department):
    # Enforce college email domain
    if not email.endswith('@kitsw.ac.in'):
        return False, "Email must be a college email ending with @kitsw.ac.in"
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO teachers (name, email, password, subject, department) VALUES (?,?,?,?,?)",
            (name, email, generate_password_hash(password), subject, department)
        )
        conn.commit()
        conn.close()
        return True, "Teacher registered successfully."
    except sqlite3.IntegrityError:
        return False, "Email already registered."


# ── QR Sessions ───────────────────────────────────────────────────────────────
def create_session(teacher_id, subject, date, start_time, end_time, token, qr_image):
    """Insert a new QR session and return its session_id."""
    conn = get_conn()
    c = conn.cursor()
    # Expire any previous active sessions for this teacher
    c.execute(
        "UPDATE qr_sessions SET is_active=0 WHERE teacher_id=? AND is_active=1",
        (teacher_id,)
    )
    c.execute(
        """INSERT INTO qr_sessions
           (teacher_id, subject, date, start_time, end_time, token, qr_image, is_active)
           VALUES (?,?,?,?,?,?,?,1)""",
        (teacher_id, subject, date, start_time, end_time, token, qr_image)
    )
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_session_by_token(token):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM qr_sessions WHERE token=?", (token,))
    result = _row(c)
    conn.close()
    return result


def get_active_session(teacher_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM qr_sessions WHERE teacher_id=? AND is_active=1 ORDER BY session_id DESC LIMIT 1",
        (teacher_id,)
    )
    result = _row(c)
    conn.close()
    return result


def expire_session(session_id):
    conn = get_conn()
    conn.execute("UPDATE qr_sessions SET is_active=0 WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


def get_sessions_by_teacher(teacher_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM qr_sessions WHERE teacher_id=? ORDER BY date DESC, start_time DESC",
        (teacher_id,)
    )
    result = _rows(c)
    conn.close()
    return result


# ── Teacher Attendance ────────────────────────────────────────────────────────
def mark_teacher_attendance(session_id, student_id, student_name, roll_no, department, date, time):
    """Mark attendance for a student in a session. Returns (success, message)."""
    conn = get_conn()
    c = conn.cursor()
    # Duplicate check — one entry per student per session
    c.execute(
        "SELECT COUNT(*) FROM teacher_attendance WHERE session_id=? AND student_id=?",
        (session_id, student_id)
    )
    if c.fetchone()[0] > 0:
        conn.close()
        return False, f"{student_name} already marked for this session."
    c.execute(
        """INSERT INTO teacher_attendance
           (session_id, student_id, student_name, roll_no, department, date, time, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, student_id, student_name, roll_no, department, date, time, "Present")
    )
    conn.commit()
    conn.close()
    return True, "Attendance marked."


def get_attendance_by_session(session_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM teacher_attendance WHERE session_id=? ORDER BY time ASC",
        (session_id,)
    )
    result = _rows(c)
    conn.close()
    return result


def get_attendance_by_teacher(teacher_id, date_filter=None, subject_filter=None):
    """Get all attendance records for a teacher with optional filters."""
    conn = get_conn()
    c = conn.cursor()
    query = """
        SELECT ta.*, qs.subject, qs.date AS session_date, qs.start_time
        FROM teacher_attendance ta
        JOIN qr_sessions qs ON ta.session_id = qs.session_id
        WHERE qs.teacher_id = ?
    """
    params = [teacher_id]
    if date_filter:
        query += " AND ta.date = ?"
        params.append(date_filter)
    if subject_filter:
        query += " AND qs.subject = ?"
        params.append(subject_filter)
    query += " ORDER BY ta.date DESC, ta.time DESC"
    c.execute(query, params)
    result = _rows(c)
    conn.close()
    return result


def get_session_attendance_count(session_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM teacher_attendance WHERE session_id=?", (session_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_teacher_stats(teacher_id):
    """Return summary stats for teacher dashboard."""
    conn = get_conn()
    c = conn.cursor()
    today = datetime.date.today().isoformat()

    c.execute("SELECT COUNT(*) FROM qr_sessions WHERE teacher_id=?", (teacher_id,))
    total_sessions = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM qr_sessions WHERE teacher_id=? AND date=?", (teacher_id, today))
    today_sessions = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM teacher_attendance ta
        JOIN qr_sessions qs ON ta.session_id = qs.session_id
        WHERE qs.teacher_id=?
    """, (teacher_id,))
    total_marked = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM teacher_attendance ta
        JOIN qr_sessions qs ON ta.session_id = qs.session_id
        WHERE qs.teacher_id=? AND ta.date=?
    """, (teacher_id, today))
    today_marked = c.fetchone()[0]

    conn.close()
    return {
        "total_sessions": total_sessions,
        "today_sessions":  today_sessions,
        "total_marked":    total_marked,
        "today_marked":    today_marked,
    }
