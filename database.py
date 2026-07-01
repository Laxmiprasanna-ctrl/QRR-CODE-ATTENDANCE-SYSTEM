"""
database.py - SQL Server database operations via pyodbc
"""
import pyodbc
import os
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# ── Connection ────────────────────────────────────────────────────────────────
SERVER   = 'LAPTOP-PSA8PSTK'
DATABASE = 'attendance_system'
CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"Trusted_Connection=yes;"
)


def get_conn():
    conn = pyodbc.connect(CONN_STR)
    conn.autocommit = False
    return conn


def _rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _row(cursor):
    cols = [c[0] for c in cursor.description]
    row  = cursor.fetchone()
    return dict(zip(cols, row)) if row else None


# ── Init / Setup ──────────────────────────────────────────────────────────────
def init_csv_files():
    """Create tables if missing and seed default admin."""
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='admins' AND xtype='U')
        CREATE TABLE admins (
            admin_id  INT IDENTITY(1,1) PRIMARY KEY,
            username  NVARCHAR(50)  UNIQUE NOT NULL,
            password  NVARCHAR(255) NOT NULL
        )
    """)

    c.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='students' AND xtype='U')
        CREATE TABLE students (
            student_id  INT           PRIMARY KEY,
            name        NVARCHAR(100) NOT NULL,
            department  NVARCHAR(50)  NOT NULL,
            email       NVARCHAR(100) UNIQUE NOT NULL,
            qr_path     NVARCHAR(200),
            face_path   NVARCHAR(200)
        )
    """)

    c.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='attendance' AND xtype='U')
        CREATE TABLE attendance (
            attendance_id INT IDENTITY(1,1) PRIMARY KEY,
            student_id    INT           NOT NULL,
            name          NVARCHAR(100) NOT NULL,
            date          DATE          NOT NULL,
            time          TIME          NOT NULL,
            subject       NVARCHAR(50)  DEFAULT 'N/A',
            period        NVARCHAR(10)  DEFAULT 'N/A',
            status        NVARCHAR(20)  DEFAULT 'Present',
            FOREIGN KEY (student_id) REFERENCES students(student_id)
        )
    """)

    # Add subject/period if table existed without them
    for col, typedef in [("subject", "NVARCHAR(50) DEFAULT 'N/A'"),
                         ("period",  "NVARCHAR(10) DEFAULT 'N/A'")]:
        c.execute(f"""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME='attendance' AND COLUMN_NAME='{col}'
            )
            ALTER TABLE attendance ADD {col} {typedef}
        """)

    c.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='timetable' AND xtype='U')
        CREATE TABLE timetable (
            id         INT IDENTITY(1,1) PRIMARY KEY,
            day        NVARCHAR(20) NOT NULL,
            period     NVARCHAR(10) NOT NULL,
            subject    NVARCHAR(50) NOT NULL,
            start_time NVARCHAR(10) NOT NULL,
            end_time   NVARCHAR(10) NOT NULL
        )
    """)

    # Seed default admin
    c.execute("SELECT COUNT(*) FROM admins WHERE username='admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO admins (username, password) VALUES (?, ?)",
                  ('admin', generate_password_hash('admin123')))

    conn.commit()
    conn.close()


# ── Admin ─────────────────────────────────────────────────────────────────────
def authenticate_admin(username, password):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT password FROM admins WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    return bool(row and check_password_hash(row[0], password))


# ── Students ──────────────────────────────────────────────────────────────────
def get_students():
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT student_id, name, department, email, qr_path, face_path FROM students")
    result = _rows(c)
    conn.close()
    return result


def get_student(student_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT student_id, name, department, email, qr_path, face_path FROM students WHERE student_id=?",
              (student_id,))
    result = _row(c)
    conn.close()
    return result


def add_student(student_id, name, department, email, qr_path, face_path):
    try:
        conn = get_conn()
        c    = conn.cursor()
        c.execute(
            "INSERT INTO students (student_id, name, department, email, qr_path, face_path) VALUES (?,?,?,?,?,?)",
            (student_id, name, department, email, qr_path, face_path)
        )
        conn.commit()
        conn.close()
        return True, "Student added successfully"
    except pyodbc.IntegrityError as e:
        return False, str(e)


def update_student(student_id, name, department, email):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "UPDATE students SET name=?, department=?, email=? WHERE student_id=?",
        (name, department, email, student_id)
    )
    conn.commit()
    affected = c.rowcount
    conn.close()
    return (True, "Student updated successfully") if affected else (False, "Student not found")


def delete_student(student_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT qr_path, face_path FROM students WHERE student_id=?", (student_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Student not found"
    for path in [row[0], row[1]]:
        if path and os.path.exists(str(path)):
            os.remove(path)
    c.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
    c.execute("DELETE FROM students    WHERE student_id=?", (student_id,))
    conn.commit()
    conn.close()
    return True, "Student deleted successfully"


# ── Attendance ────────────────────────────────────────────────────────────────
def get_attendance(limit=None):
    conn = get_conn()
    c    = conn.cursor()
    if limit:
        c.execute(f"SELECT TOP {int(limit)} attendance_id, student_id, name, "
                  f"CONVERT(VARCHAR,date,23) AS date, CONVERT(VARCHAR,time,108) AS time, "
                  f"subject, period, status FROM attendance ORDER BY date DESC, time DESC")
    else:
        c.execute("SELECT attendance_id, student_id, name, "
                  "CONVERT(VARCHAR,date,23) AS date, CONVERT(VARCHAR,time,108) AS time, "
                  "subject, period, status FROM attendance ORDER BY date DESC, time DESC")
    result = _rows(c)
    conn.close()
    return result


def get_attendance_by_date(date):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT attendance_id, student_id, name, "
              "CONVERT(VARCHAR,date,23) AS date, CONVERT(VARCHAR,time,108) AS time, "
              "subject, period, status FROM attendance WHERE date=? ORDER BY time DESC",
              (date,))
    result = _rows(c)
    conn.close()
    return result


def check_attendance_today(student_id, date, subject):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date=? AND subject=?",
              (student_id, date, subject))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def mark_attendance(student_id, name, date, time, subject='N/A', period='N/A', status='Present'):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "INSERT INTO attendance (student_id, name, date, time, subject, period, status) VALUES (?,?,?,?,?,?,?)",
        (student_id, name, date, time, subject, period, status)
    )
    conn.commit()
    conn.close()


def delete_attendance_record(attendance_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("DELETE FROM attendance WHERE attendance_id=?", (attendance_id,))
    conn.commit()
    conn.close()


def get_attendance_stats():
    today = datetime.date.today().isoformat()
    conn  = get_conn()
    c     = conn.cursor()
    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM attendance")
    total_attendance = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (today,))
    present_today = c.fetchone()[0]
    conn.close()
    return {
        "total_students":   total_students,
        "total_attendance": total_attendance,
        "present_today":    present_today
    }


# ── Timetable ─────────────────────────────────────────────────────────────────
_DAY_ORDER = ("CASE day WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 "
              "WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 "
              "WHEN 'Friday' THEN 5 ELSE 6 END")


def get_timetable():
    conn = get_conn()
    c    = conn.cursor()
    c.execute(f"SELECT id, day, period, subject, start_time, end_time, teacher_name "
              f"FROM timetable ORDER BY {_DAY_ORDER}, start_time")
    result = _rows(c)
    conn.close()
    return result


def add_timetable_entry(day, period, subject, start_time, end_time, teacher_name=''):
    try:
        conn = get_conn()
        c    = conn.cursor()
        c.execute(
            "INSERT INTO timetable (day, period, subject, start_time, end_time, teacher_name) VALUES (?,?,?,?,?,?)",
            (day, period, subject, start_time, end_time, teacher_name)
        )
        conn.commit()
        conn.close()
        return True, "Entry added successfully"
    except Exception as e:
        return False, str(e)


def update_timetable_entry(entry_id, day, period, subject, start_time, end_time, teacher_name=''):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "UPDATE timetable SET day=?, period=?, subject=?, start_time=?, end_time=?, teacher_name=? WHERE id=?",
        (day, period, subject, start_time, end_time, teacher_name, entry_id)
    )
    conn.commit()
    affected = c.rowcount
    conn.close()
    return (True, "Entry updated") if affected else (False, "Entry not found")


def delete_timetable_entry(entry_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("DELETE FROM timetable WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()


def get_timetable_by_teacher(teacher_name):
    """Get timetable entries assigned to a specific teacher."""
    conn = get_conn()
    c    = conn.cursor()
    c.execute(f"SELECT id, day, period, subject, start_time, end_time, teacher_name "
              f"FROM timetable WHERE LOWER(teacher_name)=LOWER(?) ORDER BY {_DAY_ORDER}, start_time",
              (teacher_name,))
    result = _rows(c)
    conn.close()
    return result


def get_today_timetable_by_teacher(teacher_name):
    """Get today's timetable entries for a specific teacher."""
    import datetime
    day  = datetime.datetime.now().strftime("%A")
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT id, day, period, subject, start_time, end_time, teacher_name "
              "FROM timetable WHERE day=? AND LOWER(teacher_name)=LOWER(?) ORDER BY start_time",
              (day, teacher_name))
    result = _rows(c)
    conn.close()
    return result


def get_current_class_from_db():
    """Return timetable entry whose time window contains right now."""
    now          = datetime.datetime.now()
    day          = now.strftime("%A")
    current_time = now.strftime("%H:%M")
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "SELECT id, day, period, subject, start_time, end_time "
        "FROM timetable WHERE day=? AND start_time<=? AND end_time>?",
        (day, current_time, current_time)
    )
    result = _row(c)
    conn.close()
    return result


def get_today_schedule_from_db():
    """Return all timetable entries for today ordered by start time."""
    day  = datetime.datetime.now().strftime("%A")
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "SELECT id, day, period, subject, start_time, end_time "
        "FROM timetable WHERE day=? ORDER BY start_time",
        (day,)
    )
    result = _rows(c)
    conn.close()
    return result


def get_current_class_for_teacher(teacher_name):
    """Return the timetable entry active RIGHT NOW for this teacher, or None."""
    now          = datetime.datetime.now()
    day          = now.strftime("%A")
    current_time = now.strftime("%H:%M")
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "SELECT id, day, period, subject, start_time, end_time, teacher_name "
        "FROM timetable "
        "WHERE day=? AND LOWER(teacher_name)=LOWER(?) "
        "  AND start_time<=? AND end_time>?",
        (day, teacher_name, current_time, current_time)
    )
    result = _row(c)
    conn.close()
    return result
