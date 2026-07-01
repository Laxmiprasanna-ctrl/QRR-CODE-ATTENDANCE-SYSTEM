# app.py - Main Flask application for QR Attendance System
import os, datetime, csv, io, cv2, numpy as np, pyodbc
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, Response)

from database import (init_csv_files, authenticate_admin,
                      get_timetable, add_timetable_entry, update_timetable_entry,
                      delete_timetable_entry, get_current_class_from_db, get_today_schedule_from_db,
                      get_conn as get_conn_db)
from qr_generator import generate_qr, decode_qr_from_frame
from teacher_routes import teacher_bp
from teacher_db import init_teacher_db, get_all_teachers, get_conn as tconn, _rows as trows
from student_routes import student_bp
from student_db import init_student_db

# ── SQL Server connection for student_portal ──────────────────────────────────
_SS = ("DRIVER={ODBC Driver 17 for SQL Server};"
       "SERVER=LAPTOP-PSA8PSTK;"
       "DATABASE=attendance_system;"
       "Trusted_Connection=yes;")

def ss_conn():
    c = pyodbc.connect(_SS)
    c.autocommit = False
    return c

def ss_rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


# ── Unified helpers ───────────────────────────────────────────────────────────
def get_all_students_unified():
    conn = ss_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT id AS student_id, roll_no, name, email,
               branch, class, year, semester, phone, qr_path
        FROM student_portal ORDER BY id
    """)
    rows = ss_rows(c)
    conn.close()
    return rows


def get_unified_stats():
    today  = datetime.date.today().isoformat()
    sc = ss_conn()
    c  = sc.cursor()
    c.execute("SELECT COUNT(*) FROM student_portal")
    total_students = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM attendance")
    total_attendance = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT student_id) FROM attendance WHERE CONVERT(VARCHAR,date,23)=?", (today,))
    present_today = c.fetchone()[0]
    sc.close()
    tc = tconn()
    c2 = tc.cursor()
    c2.execute("SELECT COUNT(*) FROM teachers")
    total_teachers = c2.fetchone()[0]
    c2.execute("SELECT COUNT(*) FROM qr_sessions")
    total_sessions = c2.fetchone()[0]
    tc.close()
    return {
        "total_students":   total_students,
        "total_teachers":   total_teachers,
        "total_attendance": total_attendance,
        "present_today":    present_today,
        "total_sessions":   total_sessions
    }


def get_all_attendance_unified(date_filter=None, subject_filter=None, limit=None):
    """Read attendance from SQL Server attendance table (written by teacher QR scan)."""
    conn = ss_conn()
    c    = conn.cursor()
    q = """
        SELECT a.attendance_id, sp.roll_no, a.name,
               sp.branch AS department, a.subject,
               CONVERT(VARCHAR,a.date,23) AS date,
               CONVERT(VARCHAR,a.time,108) AS time,
               a.status, a.period,
               'Teacher QR' AS teacher_name
        FROM attendance a
        LEFT JOIN student_portal sp ON sp.id = a.student_id
        WHERE 1=1
    """
    params = []
    if date_filter:
        q += " AND CONVERT(VARCHAR,a.date,23) = ?"
        params.append(date_filter)
    if subject_filter:
        q += " AND a.subject = ?"
        params.append(subject_filter)
    q += " ORDER BY a.date DESC, a.time DESC"
    if limit:
        q = q.replace("SELECT ", f"SELECT TOP {int(limit)} ", 1)
    c.execute(q, params)
    rows = ss_rows(c)
    conn.close()
    return rows


def get_student_attendance_unified(roll_no):
    """Get attendance for one student from SQL Server."""
    conn = ss_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT a.attendance_id, sp.roll_no, a.name,
               sp.branch AS department, a.subject,
               CONVERT(VARCHAR,a.date,23) AS date,
               CONVERT(VARCHAR,a.time,108) AS time,
               a.status, a.period,
               'Teacher QR' AS teacher_name
        FROM attendance a
        LEFT JOIN student_portal sp ON sp.id = a.student_id
        WHERE sp.roll_no = ?
        ORDER BY a.date DESC, a.time DESC
    """, (roll_no,))
    rows = ss_rows(c)
    conn.close()
    return rows


# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "qr_attendance_secret_2024"
app.register_blueprint(teacher_bp)
app.register_blueprint(student_bp)
os.makedirs(os.path.join("static", "faces"), exist_ok=True)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        # Must be admin AND not teacher/student
        if "admin_id" not in session:
            flash("Admin login required.", "warning")
            return redirect(url_for("admin_login"))
        if session.get("teacher_id") or session.get("student_uid"):
            flash("Access denied — admin only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


# ── Public ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    # Redirect to correct portal based on who is logged in
    if session.get("admin_id"):
        return redirect(url_for("dashboard"))
    if session.get("teacher_id"):
        return redirect(url_for("teacher.dashboard"))
    if session.get("student_uid"):
        return redirect(url_for("student.dashboard"))
    return render_template("home.html")


@app.route("/forgot_password_admin", methods=["POST"])
def forgot_password_admin():
    from werkzeug.security import generate_password_hash
    username = request.form.get("username", "").strip()
    conn = get_conn_db()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM admins WHERE username=?", (username,))
    if c.fetchone()[0] > 0:
        c.execute("UPDATE admins SET password=? WHERE username=?",
                  (generate_password_hash("admin123"), username))
        conn.commit()
        flash(f"Password reset to admin123 for '{username}'. Please login.", "success")
    else:
        flash("Username not found.", "danger")
    conn.close()
    return redirect(url_for("admin_login"))


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if authenticate_admin(username, password):
            session["admin_id"]   = username
            session["admin_name"] = username
            flash(f"Welcome back, {username}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))


# ── Admin Dashboard ───────────────────────────────────────────────────────────
@app.route("/dashboard")
@admin_required
def dashboard():
    stats  = get_unified_stats()
    today  = datetime.date.today().isoformat()
    recent = get_all_attendance_unified(limit=10)

    total_students   = stats["total_students"]
    total_attendance = stats["total_attendance"]
    present_today    = stats["present_today"]
    absent_count     = max(0, total_students - present_today)
    attendance_pct   = round((present_today / total_students * 100) if total_students else 0)

    # Subject-wise today
    subject_attendance = {}
    for r in get_all_attendance_unified(date_filter=today):
        subj = r.get("subject") or "N/A"
        subject_attendance[subj] = subject_attendance.get(subj, 0) + 1

    # Subject-wise ALL TIME for the bar breakdown
    subject_all = {}
    for r in get_all_attendance_unified():
        subj = r.get("subject") or "N/A"
        subject_all[subj] = subject_all.get(subj, 0) + 1

    return render_template("dashboard.html",
                           today=today,
                           total_students=total_students,
                           total_teachers=stats["total_teachers"],
                           total_sessions=stats["total_sessions"],
                           total_attendance=total_attendance,
                           present_today=present_today,
                           absent_count=absent_count,
                           attendance_pct=attendance_pct,
                           subject_attendance=subject_attendance,
                           subject_all=subject_all,
                           recent=recent,
                           teachers=get_all_teachers())


# ── Admin Teachers ────────────────────────────────────────────────────────────
@app.route("/admin/teachers")
@admin_required
def admin_teachers():
    teachers = get_all_teachers()
    # Attach session count per teacher
    from teacher_db import get_conn as tc, _rows as tr
    conn = tc()
    c    = conn.cursor()
    for t in teachers:
        c.execute("SELECT COUNT(*) FROM qr_sessions WHERE teacher_id=?", (t["teacher_id"],))
        t["session_count"] = c.fetchone()[0]
        c.execute("""
            SELECT COUNT(*) FROM teacher_attendance ta
            JOIN qr_sessions qs ON ta.session_id=qs.session_id
            WHERE qs.teacher_id=?
        """, (t["teacher_id"],))
        t["attendance_count"] = c.fetchone()[0]
    conn.close()
    return render_template("admin_teachers.html", teachers=teachers)


# ── Admin QR Sessions ────────────────────────────────────────────────────────────
@app.route("/admin/sessions")
@admin_required
def admin_sessions():
    from teacher_db import get_conn as tc, _rows as tr, get_session_attendance_count
    conn = tc()
    c    = conn.cursor()
    c.execute("""
        SELECT qs.*, t.name AS teacher_name, t.subject AS teacher_subject
        FROM qr_sessions qs
        JOIN teachers t ON qs.teacher_id = t.teacher_id
        ORDER BY qs.date DESC, qs.start_time DESC
    """)
    sessions = tr(c)
    conn.close()
    for s in sessions:
        s["count"] = get_session_attendance_count(s["session_id"])
    return render_template("admin_sessions.html", sessions=sessions)


# ── Admin Students ────────────────────────────────────────────────────────────
@app.route("/students")
@admin_required
def students():
    return render_template("students.html", students=get_all_students_unified())


@app.route("/students/edit/<int:sid>", methods=["POST"])
@admin_required
def admin_edit_student(sid):
    try:
        conn = ss_conn()
        c    = conn.cursor()
        c.execute("""
            UPDATE student_portal
            SET name=?, email=?, roll_no=?, branch=?, class=?,
                year=?, semester=?, phone=?
            WHERE id=?
        """, (
            request.form["name"].strip(),
            request.form["email"].strip().lower(),
            request.form["roll_no"].strip().upper(),
            request.form["branch"],
            request.form["class"].strip(),
            request.form["year"],
            request.form["semester"],
            request.form.get("phone", "").strip(),
            sid
        ))
        conn.commit()
        conn.close()
        flash(f"Student updated successfully.", "success")
    except Exception as e:
        flash(f"Update failed: {str(e)}", "danger")
    return redirect(url_for("students"))


# ── Admin Attendance ──────────────────────────────────────────────────────────
@app.route("/attendance")
@admin_required
def attendance():
    date_f = request.args.get("date", "")
    subj_f = request.args.get("subject", "")
    records  = get_all_attendance_unified(date_f or None, subj_f or None)
    all_recs = get_all_attendance_unified()
    subjects = sorted({r.get("subject") or "N/A" for r in all_recs} - {"N/A"})
    return render_template("attendance.html",
                           records=records, date_filter=date_f,
                           subject_filter=subj_f, subjects=subjects)


@app.route("/export_attendance")
@admin_required
def export_attendance():
    records = get_all_attendance_unified()
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["#","Roll No","Name","Branch","Subject","Teacher","Date","Time","Status"])
    for i, r in enumerate(records, 1):
        w.writerow([i, r.get("roll_no",""), r["name"], r.get("department",""),
                    r["subject"], r.get("teacher_name",""),
                    r["date"], r["time"], r["status"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=all_attendance.csv"})


# ── Admin Student Report ──────────────────────────────────────────────────────
@app.route("/student/<int:sid>/report")
@admin_required
def student_report(sid):
    all_students = get_all_students_unified()
    student = next((s for s in all_students if s["student_id"] == sid), None)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))

    records = get_student_attendance_unified(student["roll_no"])
    summary = {}
    for r in records:
        subj = r.get("subject", "N/A")
        if subj not in summary:
            summary[subj] = {"present": 0, "teacher": r.get("teacher_name", "N/A")}
        summary[subj]["present"] += 1

    subject_list = [{"subject": s, "present": d["present"],
                     "teacher": d["teacher"], "percent": 100}
                    for s, d in summary.items()]

    return render_template("student_report.html",
                           student=student,
                           summary=subject_list,
                           records=records,
                           overall_present=len(records),
                           overall_absent=0,
                           overall_total=len(records),
                           overall_pct=100 if records else 0)


@app.route("/export_student/<int:sid>")
@admin_required
def export_student_attendance(sid):
    all_students = get_all_students_unified()
    student = next((s for s in all_students if s["student_id"] == sid), None)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))
    records = get_student_attendance_unified(student["roll_no"])
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["Roll No","Name","Subject","Teacher","Date","Time","Status"])
    for r in records:
        w.writerow([r.get("roll_no",""), r["name"], r["subject"],
                    r.get("teacher_name",""), r["date"], r["time"], r["status"]])
    fname = f"attendance_{student['name'].replace(' ','_')}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={fname}"})


# ── Timetable ─────────────────────────────────────────────────────────────────
@app.route("/reset_student_password/<int:sid>", methods=["POST"])
@admin_required
def reset_student_password(sid):
    from werkzeug.security import generate_password_hash
    conn = ss_conn()
    c    = conn.cursor()
    c.execute("UPDATE student_portal SET password=? WHERE id=?",
              (generate_password_hash("kitsw123"), sid))
    conn.commit()
    conn.close()
    flash("Password reset to kitsw123 successfully.", "success")
    return redirect(url_for("students"))


@app.route("/timetable")
@admin_required
def timetable():
    return render_template("timetable.html",
                           entries=get_timetable(),
                           teachers=get_all_teachers(),
                           days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"])


@app.route("/timetable/add", methods=["POST"])
@admin_required
def add_timetable():
    ok, msg = add_timetable_entry(
        request.form["day"], request.form["period"].strip(),
        request.form["subject"].strip(), request.form["start_time"], request.form["end_time"],
        request.form.get("teacher_name", "").strip())
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("timetable"))


@app.route("/timetable/edit/<int:tid>", methods=["POST"])
@admin_required
def edit_timetable(tid):
    ok, msg = update_timetable_entry(
        tid, request.form["day"], request.form["period"].strip(),
        request.form["subject"].strip(), request.form["start_time"], request.form["end_time"],
        request.form.get("teacher_name", "").strip())
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("timetable"))


@app.route("/timetable/delete/<int:tid>", methods=["POST"])
@admin_required
def delete_timetable(tid):
    delete_timetable_entry(tid)
    flash("Entry deleted.", "success")
    return redirect(url_for("timetable"))


# ── Scanner ───────────────────────────────────────────────────────────────────
@app.route("/scan")
def scan():
    return render_template("scan.html",
                           current_class=get_current_class_from_db(),
                           today_schedule=get_today_schedule_from_db())


@app.route("/api/scan", methods=["POST"])
def api_scan():
    import base64
    data = request.get_json()
    if not data or "frame" not in data:
        return jsonify({"success": False, "message": "No frame provided"})
    frame = cv2.imdecode(
        np.frombuffer(base64.b64decode(data["frame"].split(",")[-1]), np.uint8),
        cv2.IMREAD_COLOR)
    qr_data = decode_qr_from_frame(frame)
    if not qr_data:
        return jsonify({"success": False, "message": "No QR code detected"})
    if qr_data.startswith("TEACHER_SESSION|"):
        return jsonify({"success": False, "qr_text": qr_data, "message": "teacher_session"})
    return jsonify({"success": False, "message": "No QR code detected"})


@app.route("/api/student_info")
def api_student_info():
    """Return logged-in student's details for auto-fill during QR scan."""
    if "student_uid" not in session:
        return jsonify({"success": False})
    from student_db import get_student_by_id
    student = get_student_by_id(session["student_uid"])
    if not student:
        return jsonify({"success": False})
    return jsonify({
        "success":    True,
        "student_id": str(student["id"]),
        "name":       student["name"],
        "roll_no":    student["roll_no"],
        "branch":     student["branch"]
    })


@app.route("/api/chart_data")
def chart_data():
    labels, values = [], []
    # Show last 30 days so historical data is visible
    for i in range(29, -1, -1):
        d = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        labels.append(d[5:])  # show MM-DD only
        values.append(len(get_all_attendance_unified(date_filter=d)))
    return jsonify({"labels": labels, "values": values})


if __name__ == "__main__":
    init_csv_files()
    init_teacher_db()
    init_student_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
