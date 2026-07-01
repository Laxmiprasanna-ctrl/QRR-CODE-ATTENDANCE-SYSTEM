"""
student_routes.py - Flask Blueprint for Student Portal
URL prefix: /student
"""
import os, qrcode
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, send_file)
from student_db import (
    authenticate_student, get_student_by_id, register_student,
    update_student_profile, save_student_qr, get_student_qr,
    get_student_attendance_history
)

student_bp     = Blueprint("student", __name__, url_prefix="/student")
STUDENT_QR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "static", "student_qr")
os.makedirs(STUDENT_QR_DIR, exist_ok=True)

BRANCHES  = ["Computer Science", "Information Technology", "Electronics",
              "Mechanical", "Civil", "Electrical", "Chemical"]
YEARS     = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
SEMESTERS = ["1", "2", "3", "4", "5", "6", "7", "8"]


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Must be student AND not admin/teacher
        if "student_uid" not in session:
            flash("Student login required.", "warning")
            return redirect(url_for("student.login"))
        if session.get("admin_id") or session.get("teacher_id"):
            flash("Access denied — student only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


def _build_stats(records):
    """
    Calculate present/absent per subject using admin timetable total classes.
    Returns (subject_stats, total_present, total_absent, overall_pct)
    """
    from database import get_timetable

    # Total scheduled classes per subject from admin timetable
    tt_totals = {}
    for e in get_timetable():
        s = e["subject"]
        tt_totals[s] = tt_totals.get(s, 0) + 1

    # Present count per subject from attendance records
    present_map = {}
    for r in records:
        s = r.get("subject", "N/A")
        present_map[s] = present_map.get(s, 0) + 1

    # Build per-subject stats
    subject_stats = []
    for subj, present in present_map.items():
        total   = tt_totals.get(subj, present)
        absent  = max(0, total - present)
        percent = round((present / total * 100) if total else 0)
        subject_stats.append({
            "subject": subj,
            "present": present,
            "absent":  absent,
            "total":   total,
            "percent": percent
        })

    subject_stats.sort(key=lambda x: x["subject"])
    total_present = sum(s["present"] for s in subject_stats)
    total_absent  = sum(s["absent"]  for s in subject_stats)
    total_classes = total_present + total_absent
    overall_pct   = round((total_present / total_classes * 100) if total_classes else 0)

    return subject_stats, total_present, total_absent, overall_pct


# ── Login ─────────────────────────────────────────────────────────────────────
@student_bp.route("/login", methods=["GET", "POST"])
def login():
    if "student_uid" in session:
        return redirect(url_for("student.dashboard"))
    if request.method == "POST":
        roll_no  = request.form["roll_no"].strip().upper()
        password = request.form["password"]
        student  = authenticate_student(roll_no, password)
        if student:
            session["student_uid"]  = student["id"]
            session["student_name"] = student["name"]
            session["student_roll"] = student["roll_no"]
            flash(f"Welcome, {student['name']}!", "success")
            return redirect(url_for("student.dashboard"))
        flash("Invalid Roll Number or Password.", "danger")
    return render_template("student/login.html")


@student_bp.route("/forgot_password", methods=["POST"])
def forgot_password():
    from werkzeug.security import generate_password_hash
    roll_no = request.form.get("roll_no", "").strip().upper()
    import pyodbc
    _SS = ("DRIVER={ODBC Driver 17 for SQL Server};"
           "SERVER=LAPTOP-PSA8PSTK;"
           "DATABASE=attendance_system;"
           "Trusted_Connection=yes;")
    try:
        conn = pyodbc.connect(_SS)
        c    = conn.cursor()
        c.execute("SELECT id, name FROM student_portal WHERE roll_no=?", (roll_no,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE student_portal SET password=? WHERE roll_no=?",
                      (generate_password_hash("kitsw123"), roll_no))
            conn.commit()
            flash(f"Password reset to kitsw123 for Roll No '{roll_no}'. Please login.", "success")
        else:
            flash("Roll number not found.", "danger")
        conn.close()
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    return redirect(url_for("student.login"))


@student_bp.route("/logout")
def logout():
    session.pop("student_uid",  None)
    session.pop("student_name", None)
    session.pop("student_roll", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("student.login"))


# ── Register ──────────────────────────────────────────────────────────────────
@student_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        roll_no  = request.form["roll_no"].strip().upper()
        name     = request.form["name"].strip()
        email    = request.form["email"].strip().lower()
        password = request.form["password"]
        branch   = request.form["branch"]
        cls      = request.form["class"]
        year     = request.form["year"]
        semester = request.form["semester"]
        phone    = request.form.get("phone", "")

        ok, msg, sid = register_student(
            roll_no, name, email, password,
            branch, cls, year, semester, phone)
        if ok:
            _generate_qr_for_student(sid, roll_no, name, branch)
            flash(f"Registration successful! Login with Roll No: {roll_no} "
                  f"and your chosen password.", "success")
            return redirect(url_for("student.login"))
        flash(msg, "danger")
    return render_template("student/register.html",
                           branches=BRANCHES, years=YEARS, semesters=SEMESTERS)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@student_bp.route("/dashboard")
@student_required
def dashboard():
    uid     = session["student_uid"]
    student = get_student_by_id(uid)
    qr_path = get_student_qr(uid)
    records = get_student_attendance_history(uid)

    subject_stats, total_present, total_absent, overall_pct = _build_stats(records)

    return render_template("student/dashboard.html",
                           student=student,
                           qr_path=qr_path,
                           subject_stats=subject_stats,
                           total_present=total_present,
                           total_absent=total_absent,
                           overall_pct=overall_pct)


# ── Generate QR ───────────────────────────────────────────────────────────────
@student_bp.route("/generate_qr")
@student_required
def generate_qr():
    uid     = session["student_uid"]
    student = get_student_by_id(uid)
    _generate_qr_for_student(uid, student["roll_no"],
                              student["name"], student["branch"])
    flash("QR Code generated successfully!", "success")
    return redirect(url_for("student.dashboard"))


# ── Attendance ────────────────────────────────────────────────────────────────
@student_bp.route("/attendance")
@student_required
def attendance():
    uid     = session["student_uid"]
    student = get_student_by_id(uid)
    records = get_student_attendance_history(uid)

    subject_stats, total_present, total_absent, overall_pct = _build_stats(records)
    total_classes = total_present + total_absent

    return render_template("student/attendance.html",
                           student=student,
                           records=records,
                           subject_stats=subject_stats,
                           total_present=total_present,
                           total_absent=total_absent,
                           total_classes=total_classes,
                           overall_pct=overall_pct)


# ── Profile ───────────────────────────────────────────────────────────────────
@student_bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    uid     = session["student_uid"]
    student = get_student_by_id(uid)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("student.login"))
    if request.method == "POST":
        try:
            update_student_profile(
                uid,
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("phone", ""),
                request.form.get("year", ""),
                request.form.get("semester", ""),
                request.form.get("class", ""))
            session["student_name"] = request.form.get("name", "").strip()
            flash("Profile updated successfully!", "success")
        except Exception as e:
            flash(f"Update failed: {str(e)}", "danger")
        return redirect(url_for("student.profile"))
    return render_template("student/profile.html",
                           student=student, years=YEARS, semesters=SEMESTERS)


# ── Download QR ───────────────────────────────────────────────────────────────
@student_bp.route("/change_password", methods=["POST"])
@student_required
def change_password():
    from werkzeug.security import generate_password_hash, check_password_hash
    import pyodbc
    uid         = session["student_uid"]
    current_pwd = request.form.get("current_password", "")
    new_pwd     = request.form.get("new_password", "")
    confirm_pwd = request.form.get("confirm_password", "")

    if new_pwd != confirm_pwd:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("student.profile"))
    if len(new_pwd) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("student.profile"))
    try:
        conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-PSA8PSTK;DATABASE=attendance_system;Trusted_Connection=yes;")
        c    = conn.cursor()
        c.execute("SELECT password FROM student_portal WHERE id=?", (uid,))
        row = c.fetchone()
        if not row or not check_password_hash(row[0], current_pwd):
            flash("Current password is incorrect.", "danger")
            conn.close()
            return redirect(url_for("student.profile"))
        c.execute("UPDATE student_portal SET password=? WHERE id=?",
                  (generate_password_hash(new_pwd), uid))
        conn.commit()
        conn.close()
        flash("Password changed successfully!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    return redirect(url_for("student.profile"))


@student_bp.route("/download_qr")
@student_required
def download_qr():
    uid     = session["student_uid"]
    qr_path = get_student_qr(uid)
    if not qr_path or not os.path.exists(qr_path):
        flash("QR not found. Please generate it first.", "warning")
        return redirect(url_for("student.dashboard"))
    return send_file(qr_path, as_attachment=True,
                     download_name=f"QR_{session['student_roll']}.png")


# ── Internal ──────────────────────────────────────────────────────────────────
def _generate_qr_for_student(student_id, roll_no, name, branch):
    qr_data  = f"{roll_no}|{name}|{branch}"
    qr_obj   = qrcode.QRCode(version=2,
                              error_correction=qrcode.constants.ERROR_CORRECT_M,
                              box_size=10, border=4)
    qr_obj.add_data(qr_data)
    qr_obj.make(fit=True)
    img      = qr_obj.make_image(fill_color="black", back_color="white")
    filename = f"student_{roll_no.replace('-','_').lower()}.png"
    abs_path = os.path.join(STUDENT_QR_DIR, filename)
    rel_path = f"static/student_qr/{filename}"
    img.save(abs_path)
    save_student_qr(student_id, rel_path)
    return rel_path
