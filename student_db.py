"""
student_db.py - SQL Server database layer for Student Portal
Table: student_portal (attendance_system DB)
Fields: id, roll_no, name, email, password, branch, class, year, semester, phone, qr_path
"""
import pyodbc, os, datetime
from werkzeug.security import generate_password_hash, check_password_hash

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LAPTOP-PSA8PSTK;"
    "DATABASE=attendance_system;"
    "Trusted_Connection=yes;"
)


def get_conn():
    conn = pyodbc.connect(CONN_STR)
    conn.autocommit = False
    return conn


def _row(cursor):
    cols = [c[0] for c in cursor.description]
    row  = cursor.fetchone()
    return dict(zip(cols, row)) if row else None


def _rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


# ── Init & Seed ───────────────────────────────────────────────────────────────
def init_student_db():
    """Create table if missing and seed sample students."""
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='student_portal' AND xtype='U')
        CREATE TABLE student_portal (
            id        INT IDENTITY(1,1) PRIMARY KEY,
            roll_no   NVARCHAR(20)  UNIQUE NOT NULL,
            name      NVARCHAR(100) NOT NULL,
            email     NVARCHAR(100) UNIQUE NOT NULL,
            password  NVARCHAR(255) NOT NULL,
            branch    NVARCHAR(50)  NOT NULL,
            class     NVARCHAR(20)  NOT NULL,
            year      NVARCHAR(20)  NOT NULL,
            semester  NVARCHAR(10)  NOT NULL,
            phone     NVARCHAR(15)  DEFAULT '',
            qr_path   NVARCHAR(200) DEFAULT '',
            created_at DATETIME     DEFAULT GETDATE()
        )
    """)
    conn.commit()

    # Seed sample students
    c.execute("SELECT COUNT(*) FROM student_portal")
    if c.fetchone()[0] == 0:
        samples = [
            ("B23IT001", "Alice Johnson",  "b23it001@kitsw.ac.in", "kitsw123",
             "Information Technology", "B.Tech IT - A",  "2nd Year", "3"),
            ("B23IT002", "Bob Smith",      "b23it002@kitsw.ac.in", "kitsw123",
             "Information Technology", "B.Tech IT - A",  "2nd Year", "3"),
            ("B23IT003", "Carol White",    "b23it003@kitsw.ac.in", "kitsw123",
             "Information Technology", "B.Tech IT - B",  "2nd Year", "3"),
            ("B23IT004", "David Brown",    "b23it004@kitsw.ac.in", "kitsw123",
             "Information Technology", "B.Tech IT - B",  "2nd Year", "3"),
            ("B23CS001", "Eva Martinez",   "b23cs001@kitsw.ac.in", "kitsw123",
             "Computer Science",       "B.Tech CSE - A", "2nd Year", "3"),
            ("B23CS002", "Frank Wilson",   "b23cs002@kitsw.ac.in", "kitsw123",
             "Computer Science",       "B.Tech CSE - A", "2nd Year", "3"),
            ("B23CS003", "Grace Lee",      "b23cs003@kitsw.ac.in", "kitsw123",
             "Computer Science",       "B.Tech CSE - B", "2nd Year", "3"),
        ]
        for roll, name, email, pwd, branch, cls, year, sem in samples:
            c.execute("""
                INSERT INTO student_portal
                    (roll_no, name, email, password, branch, class, year, semester)
                VALUES (?,?,?,?,?,?,?,?)
            """, (roll, name, email, generate_password_hash(pwd), branch, cls, year, sem))
        conn.commit()

    conn.close()


# ── Auth ──────────────────────────────────────────────────────────────────────
def authenticate_student(roll_no, password):
    """Login with roll number + password."""
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM student_portal WHERE roll_no=?", (roll_no.strip().upper(),))
    row = _row(c)
    conn.close()
    if row and check_password_hash(row["password"], password):
        return row
    return None


def get_student_by_id(student_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM student_portal WHERE id=?", (student_id,))
    result = _row(c)
    conn.close()
    return result


def get_student_by_roll(roll_no):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM student_portal WHERE roll_no=?", (roll_no.strip().upper(),))
    result = _row(c)
    conn.close()
    return result


def get_all_students():
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM student_portal ORDER BY id")
    result = _rows(c)
    conn.close()
    return result


def register_student(roll_no, name, email, password, branch, cls, year, semester, phone=""):
    """Register a new student. Returns (success, message, student_id)."""
    if not email.lower().endswith('@kitsw.ac.in'):
        return False, "Email must end with @kitsw.ac.in", None
    try:
        conn = get_conn()
        c    = conn.cursor()
        c.execute("""
            INSERT INTO student_portal
                (roll_no, name, email, password, branch, class, year, semester, phone)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (roll_no.strip().upper(), name.strip(), email.strip().lower(),
              generate_password_hash(password), branch, cls, year, semester, phone.strip()))
        conn.commit()
        c.execute("SELECT @@IDENTITY AS id")
        sid = int(c.fetchone()[0])
        conn.close()
        return True, "Registration successful.", sid
    except pyodbc.IntegrityError:
        return False, "Roll number or email already registered.", None


def update_student_profile(student_id, name, email, phone, year, semester, cls):
    """Update editable profile fields in SQL Server."""
    conn = get_conn()
    c    = conn.cursor()
    try:
        c.execute("""
            UPDATE student_portal
            SET name=?, email=?, phone=?, year=?, semester=?, class=?
            WHERE id=?
        """, (name.strip(), email.strip().lower(), phone.strip(),
              year, str(semester), cls.strip(), student_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def save_student_qr(student_id, qr_path):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("UPDATE student_portal SET qr_path=? WHERE id=?", (qr_path, student_id))
    conn.commit()
    conn.close()


def get_student_qr(student_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT qr_path FROM student_portal WHERE id=?", (student_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


# ── Attendance (reads from teacher_portal.db via SQLite) ──────────────────────
def get_student_attendance_history(student_id):
    """Get attendance from teacher_portal.db for this student's roll_no."""
    import sqlite3
    student = get_student_by_id(student_id)
    if not student:
        return []
    DB_PATH = os.path.join(os.path.dirname(__file__), "teacher_portal.db")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT ta.attendance_id, ta.roll_no, ta.student_name AS name,
               ta.department, qs.subject, ta.date, ta.time, ta.status,
               t.name AS teacher_name
        FROM teacher_attendance ta
        JOIN qr_sessions qs ON ta.session_id = qs.session_id
        JOIN teachers t     ON qs.teacher_id = t.teacher_id
        WHERE ta.roll_no = ?
        ORDER BY ta.date DESC, ta.time DESC
    """, (student["roll_no"],))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_student_attendance_summary(student_id):
    records = get_student_attendance_history(student_id)
    summary = {}
    for r in records:
        subj = r.get("subject", "N/A")
        if subj not in summary:
            summary[subj] = {"present": 0, "teacher": r.get("teacher_name", "N/A")}
        summary[subj]["present"] += 1
    return summary
