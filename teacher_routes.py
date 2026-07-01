"""
teacher_routes.py - Flask Blueprint for Teacher Portal
URL prefix: /teacher
Attendance is written to BOTH:
  - SQLite teacher_portal.db  (teacher/student portal views)
  - SQL Server attendance table (admin portal views)
"""
import os, io, csv, uuid, datetime, qrcode, traceback
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify, Response)
from teacher_db import (
    authenticate_teacher, get_teacher, add_teacher,
    create_session, get_session_by_token, get_active_session,
    expire_session, get_sessions_by_teacher, mark_teacher_attendance,
    get_attendance_by_session, get_attendance_by_teacher,
    get_session_attendance_count, get_teacher_stats
)

teacher_bp        = Blueprint("teacher", __name__, url_prefix="/teacher")
QR_EXPIRY_MINUTES = 2
QR_SESSION_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "static", "qr_sessions")
os.makedirs(QR_SESSION_DIR, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Must be teacher AND not admin/student
        if "teacher_id" not in session:
            flash("Teacher login required.", "warning")
            return redirect(url_for("teacher.login"))
        if session.get("admin_id") or session.get("student_uid"):
            flash("Access denied — teacher only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


def _check_expiry(sess):
    """Expiry = 2 minutes from session start_time."""
    date_str  = sess["date"]
    start_str = sess["start_time"]
    if len(start_str) == 5:
        start_str += ":00"
    start_dt  = datetime.datetime.strptime(f"{date_str} {start_str}", "%Y-%m-%d %H:%M:%S")
    expiry_dt = start_dt + datetime.timedelta(minutes=QR_EXPIRY_MINUTES)
    now        = datetime.datetime.now()
    remaining  = max(0, int((expiry_dt - now).total_seconds()))
    total_secs = QR_EXPIRY_MINUTES * 60
    return expiry_dt, remaining == 0, remaining, total_secs


def _get_session_by_id(session_id):
    from teacher_db import get_conn, _row
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM qr_sessions WHERE session_id=?", (session_id,))
    result = _row(c)
    conn.close()
    return result


def _write_to_sqlserver(roll_no, student_name, subject, date_str, time_str):
    """Write attendance record to SQL Server attendance table (admin portal)."""
    try:
        from database import get_conn as ss_conn
        sc = ss_conn()
        c  = sc.cursor()
        # Get period from timetable
        day = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        c.execute("SELECT TOP 1 period FROM timetable WHERE subject=? AND day=?",
                  (subject, day))
        row    = c.fetchone()
        period = row[0] if row else "N/A"
        # Get student_id from student_portal
        c.execute("SELECT id FROM student_portal WHERE roll_no=?", (roll_no,))
        sp = c.fetchone()
        if sp:
            sid = sp[0]
            c.execute(
                "SELECT COUNT(*) FROM attendance WHERE student_id=? AND date=? AND subject=?",
                (sid, date_str, subject))
            if c.fetchone()[0] == 0:
                c.execute(
                    "INSERT INTO attendance (student_id,name,date,time,subject,period,status)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (sid, student_name, date_str, time_str, subject, period, "Present"))
                sc.commit()
        sc.close()
    except Exception:
        pass  # SQLite record already saved; SQL Server is best-effort


# ── Auth ──────────────────────────────────────────────────────────────────────
@teacher_bp.route("/login", methods=["GET", "POST"])
def login():
    if "teacher_id" in session:
        return redirect(url_for("teacher.dashboard"))
    if request.method == "POST":
        teacher = authenticate_teacher(
            request.form["identifier"].strip(),
            request.form["password"])
        if teacher:
            session["teacher_id"]   = teacher["teacher_id"]
            session["teacher_name"] = teacher["name"]
            session["teacher_subj"] = teacher["subject"]
            flash(f"Welcome back, {teacher['name']}!", "success")
            return redirect(url_for("teacher.dashboard"))
        flash("Invalid name/email or password.", "danger")
    return render_template("teacher/login.html")


@teacher_bp.route("/forgot_password", methods=["POST"])
def forgot_password():
    from werkzeug.security import generate_password_hash
    identifier = request.form.get("identifier", "").strip()
    from teacher_db import get_conn, _row
    conn = get_conn()
    c    = conn.cursor()
    # Try by name or email
    c.execute("SELECT teacher_id, name FROM teachers WHERE LOWER(name)=LOWER(?) OR LOWER(email)=LOWER(?)",
              (identifier, identifier))
    row = _row(c)
    if row:
        c.execute("UPDATE teachers SET password=? WHERE teacher_id=?",
                  (generate_password_hash("kitsw@123"), row["teacher_id"]))
        conn.commit()
        flash(f"Password reset to kitsw@123 for '{row['name']}'. Please login.", "success")
    else:
        flash("Name or email not found.", "danger")
    conn.close()
    return redirect(url_for("teacher.login"))


@teacher_bp.route("/logout")
def logout():
    session.pop("teacher_id",   None)
    session.pop("teacher_name", None)
    session.pop("teacher_subj", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("teacher.login"))


@teacher_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        ok, msg = add_teacher(
            request.form["name"].strip(),
            request.form["email"].strip().lower(),
            request.form["password"],
            request.form["subject"].strip(),
            request.form["department"].strip())
        flash(msg, "success" if ok else "danger")
        if ok:
            return redirect(url_for("teacher.login"))
    return render_template("teacher/register.html")


# ── Dashboard ─────────────────────────────────────────────────────────────────
@teacher_bp.route("/dashboard")
@teacher_required
def dashboard():
    tid    = session["teacher_id"]
    teacher = get_teacher(tid)
    stats   = get_teacher_stats(tid)
    active  = get_active_session(tid)

    if active:
        _, is_exp, _, _ = _check_expiry(active)
        if is_exp:
            expire_session(active["session_id"])
            active = None

    recent = get_sessions_by_teacher(tid)[:5]
    for s in recent:
        s["count"] = get_session_attendance_count(s["session_id"])

    return render_template("teacher/dashboard.html",
                           teacher=teacher, stats=stats,
                           active_session=active, recent_sessions=recent,
                           today=datetime.date.today().isoformat())


# ── QR Generation — subjects from Admin Timetable ────────────────────────────
@teacher_bp.route("/generate_qr", methods=["GET", "POST"])
@teacher_required
def generate_qr():
    tid     = session["teacher_id"]
    teacher = get_teacher(tid)
    error   = None

    from database import get_timetable, get_today_schedule_from_db, get_timetable_by_teacher, \
        get_today_timetable_by_teacher, get_current_class_for_teacher

    teacher_name  = teacher["name"]
    my_entries    = get_timetable_by_teacher(teacher_name)
    my_subjects   = sorted({e["subject"] for e in my_entries}) if my_entries else sorted({e["subject"] for e in get_timetable()})
    today_classes = get_today_timetable_by_teacher(teacher_name) or get_today_schedule_from_db()

    # ── Time-gate: find the active class slot right now ───────────────────────
    active_class = get_current_class_for_teacher(teacher_name)
    outside_schedule = active_class is None

    if request.method == "POST":
        # Re-check on every POST — prevents API abuse
        active_class = get_current_class_for_teacher(teacher_name)
        if active_class is None:
            flash("QR generation is only allowed during your scheduled class time.", "warning")
            return redirect(url_for("teacher.generate_qr"))

        try:
            subject = active_class["subject"]
            period  = active_class["period"]
            now     = datetime.datetime.now()
            date    = now.strftime("%Y-%m-%d")
            start   = now.strftime("%H:%M:%S")
            # Use real timetable end_time as expiry
            end     = active_class["end_time"] if len(active_class["end_time"]) == 8 \
                      else active_class["end_time"] + ":00"
            token   = str(uuid.uuid4())

            qr_data = f"TEACHER_SESSION|{tid}|{subject}|{date}|{start}|{token}"

            qr_obj = qrcode.QRCode(version=2,
                                   error_correction=qrcode.constants.ERROR_CORRECT_M,
                                   box_size=10, border=4)
            qr_obj.add_data(qr_data)
            qr_obj.make(fit=True)
            img      = qr_obj.make_image(fill_color="black", back_color="white")
            filename = f"session_{token[:8]}.png"
            abs_path = os.path.join(QR_SESSION_DIR, filename)
            rel_path = f"static/qr_sessions/{filename}"
            img.save(abs_path)

            sid = create_session(tid, subject, date, start, end, token, rel_path)
            expiry_time = (datetime.datetime.strptime(start, "%H:%M:%S") + datetime.timedelta(minutes=QR_EXPIRY_MINUTES)).strftime("%H:%M:%S")
            flash(f"QR generated for '{subject}'. Expires in {QR_EXPIRY_MINUTES} minutes (at {expiry_time}).", "success")
            return redirect(url_for("teacher.show_qr", session_id=sid))

        except Exception as e:
            error = str(e)
            traceback.print_exc()
            flash(f"QR generation failed: {error}", "danger")

    return render_template("teacher/generate_qr.html",
                           teacher=teacher,
                           expiry_minutes=QR_EXPIRY_MINUTES,
                           all_subjects=my_subjects,
                           today_classes=today_classes,
                           active_class=active_class,
                           outside_schedule=outside_schedule,
                           error=error)


# ── Show QR ───────────────────────────────────────────────────────────────────
@teacher_bp.route("/qr/<int:session_id>")
@teacher_required
def show_qr(session_id):
    tid  = session["teacher_id"]
    sess = _get_session_by_id(session_id)
    if not sess or sess["teacher_id"] != tid:
        flash("Session not found.", "danger")
        return redirect(url_for("teacher.dashboard"))

    expiry_dt, is_expired, remaining_secs, expiry_secs = _check_expiry(sess)
    if is_expired:
        expire_session(session_id)

    count    = get_session_attendance_count(session_id)
    students = get_attendance_by_session(session_id)
    qr_url   = sess["qr_image"].replace("\\", "/").replace("static/", "", 1)

    return render_template("teacher/show_qr.html",
                           sess=sess, count=count, students=students,
                           is_expired=is_expired,
                           expiry=expiry_dt.strftime("%H:%M:%S"),
                           expiry_secs=expiry_secs,
                           remaining_secs=remaining_secs,
                           qr_url=qr_url)


# ── API: poll session status ──────────────────────────────────────────────────
@teacher_bp.route("/api/session_status/<int:session_id>")
@teacher_required
def session_status(session_id):
    sess = _get_session_by_id(session_id)
    if not sess:
        return jsonify({"error": "not found"})
    _, is_expired, remaining, _ = _check_expiry(sess)
    if is_expired:
        expire_session(session_id)
    students = get_attendance_by_session(session_id)
    return jsonify({"count": len(students), "remaining": remaining,
                    "is_expired": is_expired, "students": students})


# ── API: student scans teacher QR → mark attendance ───────────────────────────
@teacher_bp.route("/api/mark", methods=["POST"])
def api_mark():
    data  = request.get_json(force=True, silent=True) or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"success": False, "message": "No token provided."})

    sess = get_session_by_token(token)
    if not sess:
        return jsonify({"success": False, "message": "Invalid QR code — session not found."})

    _, is_expired, _, _ = _check_expiry(sess)
    if is_expired:
        expire_session(sess["session_id"])
        return jsonify({"success": False, "message": "QR code has expired."})

    if not sess["is_active"]:
        return jsonify({"success": False, "message": "This session is no longer active."})

    now          = datetime.datetime.now()
    roll_no      = data.get("roll_no", "").strip()
    student_name = data.get("student_name", "Unknown").strip()
    department   = data.get("department", "").strip()
    subject      = sess["subject"]
    date_str     = now.strftime("%Y-%m-%d")
    time_str     = now.strftime("%H:%M:%S")

    # Write to SQLite (teacher portal)
    ok, msg = mark_teacher_attendance(
        sess["session_id"],
        str(data.get("student_id", "")).strip(),
        student_name, roll_no, department, date_str, time_str)

    if ok:
        # Write to SQL Server (admin portal)
        _write_to_sqlserver(roll_no, student_name, subject, date_str, time_str)

    return jsonify({"success": ok, "message": msg,
                    "subject": subject, "teacher_id": sess["teacher_id"]})


# ── Attendance views ──────────────────────────────────────────────────────────
@teacher_bp.route("/attendance")
@teacher_required
def attendance():
    tid     = session["teacher_id"]
    date_f  = request.args.get("date", "")
    subj_f  = request.args.get("subject", "")
    records = get_attendance_by_teacher(tid, date_f or None, subj_f or None)
    all_s   = get_sessions_by_teacher(tid)
    subjects = sorted({s["subject"] for s in all_s})
    return render_template("teacher/attendance.html",
                           records=records, subjects=subjects,
                           date_filter=date_f, subject_filter=subj_f)


@teacher_bp.route("/session/<int:session_id>/attendance")
@teacher_required
def session_attendance(session_id):
    tid  = session["teacher_id"]
    sess = _get_session_by_id(session_id)
    if not sess or sess["teacher_id"] != tid:
        flash("Session not found.", "danger")
        return redirect(url_for("teacher.attendance"))
    records = get_attendance_by_session(session_id)
    return render_template("teacher/session_attendance.html",
                           sess=sess, records=records)


# ── Sessions list ─────────────────────────────────────────────────────────────
@teacher_bp.route("/sessions")
@teacher_required
def sessions():
    tid      = session["teacher_id"]
    all_sess = get_sessions_by_teacher(tid)
    for s in all_sess:
        s["count"] = get_session_attendance_count(s["session_id"])
    return render_template("teacher/sessions.html", sessions=all_sess)


# ── Export ────────────────────────────────────────────────────────────────────
@teacher_bp.route("/export")
@teacher_required
def export():
    tid     = session["teacher_id"]
    date_f  = request.args.get("date", "")
    subj_f  = request.args.get("subject", "")
    records = get_attendance_by_teacher(tid, date_f or None, subj_f or None)
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["#","Student ID","Roll No","Name","Department","Subject","Date","Time","Status"])
    for i, r in enumerate(records, 1):
        w.writerow([i, r["student_id"], r["roll_no"], r["student_name"],
                    r["department"], r["subject"], r["date"], r["time"], r["status"]])
    tname = session["teacher_name"].replace(" ", "_")
    fname = f"attendance_{tname}{('_'+date_f) if date_f else ''}{('_'+subj_f) if subj_f else ''}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={fname}"})


@teacher_bp.route("/export/session/<int:session_id>")
@teacher_required
def export_session(session_id):
    tid  = session["teacher_id"]
    sess = _get_session_by_id(session_id)
    if not sess or sess["teacher_id"] != tid:
        flash("Session not found.", "danger")
        return redirect(url_for("teacher.attendance"))
    records = get_attendance_by_session(session_id)
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["Session ID","Subject","Date","Start Time","End Time"])
    w.writerow([sess["session_id"], sess["subject"], sess["date"],
                sess["start_time"], sess["end_time"]])
    w.writerow([])
    w.writerow(["#","Student ID","Roll No","Name","Department","Time","Status"])
    for i, r in enumerate(records, 1):
        w.writerow([i, r["student_id"], r["roll_no"], r["student_name"],
                    r["department"], r["time"], r["status"]])
    fname = f"session_{session_id}_{sess['subject'].replace(' ','_')}_{sess['date']}.csv"
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename={fname}"})
