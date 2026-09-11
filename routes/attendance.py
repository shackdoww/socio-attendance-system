from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import AttendanceLog, AttendanceSession, Socio, User


attendance_bp = Blueprint("attendance", __name__)
MANAGER_ROLES = {"admin", "socio_moderator", "president", "vice_president", "secretary"}


def attendance_manager_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role not in MANAGER_ROLES:
            return "Forbidden", 403
        return view(*args, **kwargs)

    return wrapped


def get_session_for_date(session_date, socio_id):
    return db.session.execute(
        db.select(AttendanceSession).where(
            AttendanceSession.session_date == session_date,
            AttendanceSession.socio_id == socio_id,
        )
    ).scalar_one_or_none()


@attendance_bp.route("/attendance")
@login_required
def index():
    selected_date = request.args.get("date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date)
    except ValueError:
        selected_date = date.today()

    if selected_date.weekday() == 6:
        flash("Sunday has no regular attendance session.", "error")
        selected_date = date.today()

    if current_user.role == "admin":
        sessions = db.session.execute(
            db.select(AttendanceSession).order_by(AttendanceSession.session_date.desc()).limit(30)
        ).scalars().all()
        socios = db.session.execute(db.select(Socio).order_by(Socio.name)).scalars().all()
        session = None
        if request.args.get("date"):
            session = db.session.execute(
                db.select(AttendanceSession).where(AttendanceSession.session_date == selected_date)
                .order_by(AttendanceSession.socio_id)
            ).scalars().first()
        return render_template("attendance/index.html", session=session, sessions=sessions, socios=socios, selected_date=selected_date)

    session = get_session_for_date(selected_date, current_user.socio_id) if current_user.socio_id else None
    records = []
    if session:
        records = db.session.execute(
            db.select(AttendanceLog).where(AttendanceLog.session_id == session.id).order_by(AttendanceLog.time_in, AttendanceLog.user_id)
        ).scalars().all()
    return render_template("attendance/index.html", session=session, records=records, selected_date=selected_date)


@attendance_bp.route("/attendance/create", methods=["POST"])
@attendance_manager_required
def create_session():
    selected_date = request.form.get("session_date", "").strip()
    socio_id = request.form.get("socio_id") if current_user.role == "admin" else current_user.socio_id

    try:
        session_date = date.fromisoformat(selected_date)
    except ValueError:
        flash("Invalid attendance date.", "error")
        return redirect(url_for("attendance.index"))

    if session_date.weekday() == 6:
        flash("Regular attendance is only available Monday through Saturday.", "error")
        return redirect(url_for("attendance.index"))
    if not socio_id:
        flash("A socio must be assigned before attendance can be created.", "error")
        return redirect(url_for("attendance.index"))
    if get_session_for_date(session_date, int(socio_id)):
        flash("An attendance session already exists for that date.", "error")
        return redirect(url_for("attendance.index", date=session_date.isoformat()))

    socio = db.get_or_404(Socio, int(socio_id))
    if current_user.role != "admin" and current_user.socio_id != socio.id:
        return "Forbidden", 403

    session = AttendanceSession(socio_id=socio.id, session_date=session_date, session_type="regular", created_by=current_user.id)
    db.session.add(session)
    db.session.flush()

    members = db.session.execute(
        db.select(User).where(User.socio_id == socio.id, User.is_active.is_(True)).order_by(User.full_name)
    ).scalars().all()
    for member in members:
        db.session.add(AttendanceLog(session_id=session.id, user_id=member.id, status="absent"))

    db.session.commit()
    flash("Daily attendance session created.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/<int:session_id>")
@login_required
def manage(session_id):
    session = db.get_or_404(AttendanceSession, session_id)
    if current_user.role != "admin" and current_user.socio_id != session.socio_id:
        return "Forbidden", 403

    records = db.session.execute(
        db.select(AttendanceLog).where(AttendanceLog.session_id == session.id).join(User).order_by(User.full_name)
    ).scalars().all()
    return render_template("attendance/manage.html", session=session, records=records)


@attendance_bp.route("/attendance/<int:session_id>/record/<int:record_id>", methods=["POST"])
@attendance_manager_required
def record(session_id, record_id):
    session = db.get_or_404(AttendanceSession, session_id)
    record = db.get_or_404(AttendanceLog, record_id)
    if record.session_id != session.id or (current_user.role != "admin" and current_user.socio_id != session.socio_id):
        return "Forbidden", 403

    status = request.form.get("status", "absent")
    if status not in {"present", "practicing", "late", "excused", "absent"}:
        status = "absent"

    time_in_text = request.form.get("time_in", "").strip()
    time_out_text = request.form.get("time_out", "").strip()
    notes = request.form.get("notes", "").strip()

    def parse_time(value):
        return datetime.strptime(value, "%H:%M").time() if value else None

    try:
        record.time_in = parse_time(time_in_text)
        record.time_out = parse_time(time_out_text)
    except ValueError:
        flash("Time must use HH:MM format.", "error")
        return redirect(url_for("attendance.manage", session_id=session.id))

    record.status = status
    record.notes = notes or None
    if record.time_in and record.time_out:
        start = datetime.combine(session.session_date, record.time_in)
        end = datetime.combine(session.session_date, record.time_out)
        if end < start:
            end += timedelta(days=1)
        record.duration_minutes = max(0, int((end - start).total_seconds() // 60))
    else:
        record.duration_minutes = None

    db.session.commit()
    flash(f"Attendance for {record.user.full_name} updated.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/history")
@login_required
def history():
    query = db.select(AttendanceLog).join(AttendanceSession).join(User).order_by(AttendanceSession.session_date.desc(), User.full_name)
    if current_user.role != "admin":
        query = query.where(AttendanceSession.socio_id == current_user.socio_id)
    records = db.session.execute(query.limit(500)).scalars().all()
    return render_template("attendance/history.html", records=records)


@attendance_bp.route("/attendance/reports")
@login_required
def reports():
    query = db.select(AttendanceLog).join(AttendanceSession).join(User)
    if current_user.role != "admin":
        query = query.where(AttendanceSession.socio_id == current_user.socio_id)
    records = db.session.execute(query).scalars().all()

    stats = {}
    for record in records:
        user_id = record.user_id
        if user_id not in stats:
            stats[user_id] = {"user": record.user, "total": 0, "attended": 0, "practicing": 0, "late": 0, "excused": 0, "absent": 0, "minutes": 0}
        item = stats[user_id]
        item["total"] += 1
        if record.status in {"present", "practicing", "late"}:
            item["attended"] += 1
        if record.status == "practicing":
            item["practicing"] += 1
        if record.status == "late":
            item["late"] += 1
        if record.status == "excused":
            item["excused"] += 1
        if record.status == "absent":
            item["absent"] += 1
        item["minutes"] += record.duration_minutes or 0

    for item in stats.values():
        item["attendance_rate"] = round((item["attended"] / item["total"]) * 100, 1) if item["total"] else 0

    return render_template("attendance/reports.html", stats=sorted(stats.values(), key=lambda x: x["user"].full_name))
