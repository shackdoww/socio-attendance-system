from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import AttendanceLog, AttendanceSession, Socio, User


attendance_bp = Blueprint("attendance", __name__)
MANAGER_ROLES = {"admin", "socio_moderator"}
NON_ATTENDANCE_ROLES = {"admin", "socio_moderator"}
ATTENDANCE_STATUSES = {"present", "late", "excused", "absent"}
SELF_STATUSES = {"present", "late", "excused"}


def attendance_manager_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role not in MANAGER_ROLES:
            return "Forbidden", 403
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            return "Forbidden", 403
        return view(*args, **kwargs)
    return wrapped


def get_session_for_date(session_date, socio_id):
    return db.session.execute(db.select(AttendanceSession).where(
        AttendanceSession.session_date == session_date,
        AttendanceSession.socio_id == socio_id,
    )).scalar_one_or_none()


def attendance_member_query(socio_id):
    return db.select(User).where(
        User.socio_id == socio_id,
        User.is_active.is_(True),
        User.role.notin_(NON_ATTENDANCE_ROLES),
    ).order_by(User.full_name)


def attendance_records_query(session_id):
    return db.select(AttendanceLog).where(
        AttendanceLog.session_id == session_id,
        User.role.notin_(NON_ATTENDANCE_ROLES),
    ).join(User).order_by(User.full_name)


def ensure_session(session_date, socio_id, created_by):
    session = get_session_for_date(session_date, socio_id)
    if session:
        return session
    session = AttendanceSession(
        socio_id=socio_id,
        session_date=session_date,
        session_type="regular",
        created_by=created_by,
    )
    db.session.add(session)
    db.session.flush()
    members = db.session.execute(attendance_member_query(socio_id)).scalars().all()
    for member in members:
        db.session.add(AttendanceLog(
            session_id=session.id,
            user_id=member.id,
            status="absent",
            approval_status="not_required",
        ))
    db.session.commit()
    return session


def calculate_duration(session_date, time_in, time_out):
    if not time_in or not time_out:
        return None
    start = datetime.combine(session_date, time_in)
    end = datetime.combine(session_date, time_out)
    if end < start:
        end += timedelta(days=1)
    return max(0, int((end - start).total_seconds() // 60))


def get_current_user_record(session):
    return db.session.execute(db.select(AttendanceLog).where(
        AttendanceLog.session_id == session.id,
        AttendanceLog.user_id == current_user.id,
    )).scalar_one_or_none()


@attendance_bp.route("/attendance")
@login_required
def index():
    selected_date_text = request.args.get("date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_date_text)
    except ValueError:
        selected_date = date.today()

    if current_user.role == "admin":
        socios = db.session.execute(db.select(Socio).order_by(Socio.name)).scalars().all()
        selected_sessions = [ensure_session(selected_date, socio.id, current_user.id) for socio in socios]
        sessions = db.session.execute(db.select(AttendanceSession).order_by(
            AttendanceSession.session_date.desc(), AttendanceSession.socio_id
        ).limit(100)).scalars().all()
        return render_template(
            "attendance/index.html",
            session=selected_sessions[0] if selected_sessions else None,
            selected_sessions=selected_sessions,
            sessions=sessions,
            socios=socios,
            selected_date=selected_date,
        )

    if not current_user.socio_id:
        return render_template("attendance/index.html", session=None, records=[], selected_date=selected_date)

    session = ensure_session(selected_date, current_user.socio_id, current_user.id)
    if current_user.role == "socio_moderator":
        records = [] if session.no_attendance else db.session.execute(
            attendance_records_query(session.id)
        ).scalars().all()
        pending_count = sum(1 for record in records if record.approval_status == "pending")
        return render_template(
            "attendance/index.html",
            session=session,
            records=records,
            selected_date=selected_date,
            pending_count=pending_count,
        )

    record = get_current_user_record(session)
    return render_template(
        "attendance/index.html",
        session=session,
        record=record,
        selected_date=selected_date,
    )


@attendance_bp.route("/attendance/<int:session_id>")
@attendance_manager_required
def manage(session_id):
    session = db.get_or_404(AttendanceSession, session_id)
    if current_user.role != "admin" and current_user.socio_id != session.socio_id:
        return "Forbidden", 403
    records = [] if session.no_attendance else db.session.execute(
        attendance_records_query(session.id)
    ).scalars().all()
    return render_template("attendance/manage.html", session=session, records=records)


@attendance_bp.route("/attendance/<int:session_id>/self/submit", methods=["POST"])
@login_required
def self_submit(session_id):
    if current_user.role in NON_ATTENDANCE_ROLES or not current_user.socio_id:
        return "Forbidden", 403
    session = db.get_or_404(AttendanceSession, session_id)
    if session.socio_id != current_user.socio_id or session.session_date != date.today():
        return "Attendance can only be submitted for your current socio and today's date.", 403
    if session.no_attendance:
        flash("Attendance is disabled for this date.", "error")
        return redirect(url_for("attendance.index"))

    record = get_current_user_record(session)
    if record is None:
        record = AttendanceLog(session_id=session.id, user_id=current_user.id, status="present")
        db.session.add(record)

    if record.approval_status == "approved":
        flash("Your attendance has already been approved and cannot be edited.", "error")
        return redirect(url_for("attendance.index"))

    status = request.form.get("status", "present")
    if status not in SELF_STATUSES:
        status = "present"
    notes = request.form.get("notes", "").strip()

    if status in {"present", "late"} and not record.time_in:
        flash("Please use Time In before submitting this attendance status.", "error")
        return redirect(url_for("attendance.index"))

    if status == "excused":
        record.duration_minutes = calculate_duration(session.session_date, record.time_in, record.time_out)
    else:
        record.duration_minutes = calculate_duration(session.session_date, record.time_in, record.time_out)

    record.status = status
    record.notes = notes or None
    record.approval_status = "pending"
    record.approved_by = None
    record.approved_at = None
    record.rejection_reason = None
    db.session.commit()
    flash("Attendance submitted for Socio Moderator approval.", "success")
    return redirect(url_for("attendance.index"))


@attendance_bp.route("/attendance/<int:session_id>/self/time-in", methods=["POST"])
@login_required
def self_time_in(session_id):
    if current_user.role in NON_ATTENDANCE_ROLES or not current_user.socio_id:
        return "Forbidden", 403
    session = db.get_or_404(AttendanceSession, session_id)
    if session.socio_id != current_user.socio_id or session.session_date != date.today():
        return "Attendance can only be logged for today's date.", 403
    if session.no_attendance:
        flash("Attendance is disabled for this date.", "error")
        return redirect(url_for("attendance.index"))

    record = get_current_user_record(session)
    if record is None:
        record = AttendanceLog(session_id=session.id, user_id=current_user.id, status="present")
        db.session.add(record)
    if record.approval_status == "approved":
        flash("Your attendance is already approved.", "error")
        return redirect(url_for("attendance.index"))
    if record.time_in:
        flash("You have already timed in.", "error")
        return redirect(url_for("attendance.index"))

    record.time_in = datetime.now().time().replace(second=0, microsecond=0)
    record.status = "present"
    record.approval_status = "pending"
    record.rejection_reason = None
    db.session.commit()
    flash("Time In recorded. Remember to Time Out when you finish.", "success")
    return redirect(url_for("attendance.index"))


@attendance_bp.route("/attendance/<int:session_id>/self/time-out", methods=["POST"])
@login_required
def self_time_out(session_id):
    if current_user.role in NON_ATTENDANCE_ROLES or not current_user.socio_id:
        return "Forbidden", 403
    session = db.get_or_404(AttendanceSession, session_id)
    if session.socio_id != current_user.socio_id or session.session_date != date.today():
        return "Attendance can only be logged for today's date.", 403
    if session.no_attendance:
        flash("Attendance is disabled for this date.", "error")
        return redirect(url_for("attendance.index"))

    record = get_current_user_record(session)
    if record is None or not record.time_in:
        flash("You must Time In before you can Time Out.", "error")
        return redirect(url_for("attendance.index"))
    if record.approval_status == "approved":
        flash("Your attendance is already approved.", "error")
        return redirect(url_for("attendance.index"))
    if record.time_out:
        flash("You have already timed out.", "error")
        return redirect(url_for("attendance.index"))

    record.time_out = datetime.now().time().replace(second=0, microsecond=0)
    record.duration_minutes = calculate_duration(session.session_date, record.time_in, record.time_out)
    record.approval_status = "pending"
    record.rejection_reason = None
    db.session.commit()
    flash("Time Out recorded. Your attendance is now waiting for approval.", "success")
    return redirect(url_for("attendance.index"))


@attendance_bp.route("/attendance/<int:session_id>/record/<int:record_id>", methods=["POST"])
@admin_required
def record(session_id, record_id):
    session = db.get_or_404(AttendanceSession, session_id)
    record = db.get_or_404(AttendanceLog, record_id)
    if record.session_id != session.id or record.user.role in NON_ATTENDANCE_ROLES:
        return "Forbidden", 403
    if session.no_attendance:
        flash("Attendance is disabled for this date.", "error")
        return redirect(url_for("attendance.manage", session_id=session.id))

    status = request.form.get("status", "absent")
    if status not in ATTENDANCE_STATUSES:
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
    record.duration_minutes = calculate_duration(session.session_date, record.time_in, record.time_out)
    record.approval_status = "approved"
    record.approved_by = current_user.id
    record.approved_at = datetime.utcnow()
    record.rejection_reason = None
    db.session.commit()
    flash(f"Attendance for {record.user.full_name} updated by Administrator.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/<int:session_id>/approve/<int:record_id>", methods=["POST"])
@attendance_manager_required
def approve(session_id, record_id):
    session = db.get_or_404(AttendanceSession, session_id)
    record = db.get_or_404(AttendanceLog, record_id)
    if record.session_id != session.id or current_user.role != "admin" and current_user.socio_id != session.socio_id:
        return "Forbidden", 403
    if current_user.role == "socio_moderator" and record.approval_status != "pending":
        flash("Only pending attendance can be approved.", "error")
        return redirect(url_for("attendance.manage", session_id=session.id))
    if session.no_attendance:
        flash("Attendance is disabled for this date.", "error")
        return redirect(url_for("attendance.manage", session_id=session.id))

    record.approval_status = "approved"
    record.approved_by = current_user.id
    record.approved_at = datetime.utcnow()
    record.rejection_reason = None
    db.session.commit()
    flash(f"Attendance for {record.user.full_name} approved.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/<int:session_id>/reject/<int:record_id>", methods=["POST"])
@attendance_manager_required
def reject(session_id, record_id):
    session = db.get_or_404(AttendanceSession, session_id)
    record = db.get_or_404(AttendanceLog, record_id)
    if record.session_id != session.id or current_user.role != "admin" and current_user.socio_id != session.socio_id:
        return "Forbidden", 403
    if record.approval_status != "pending":
        flash("Only pending attendance can be rejected.", "error")
        return redirect(url_for("attendance.manage", session_id=session.id))

    reason = request.form.get("reason", "").strip()
    record.approval_status = "rejected"
    record.approved_by = None
    record.approved_at = None
    record.rejection_reason = reason or "Attendance submission was rejected by the reviewer."
    db.session.commit()
    flash(f"Attendance for {record.user.full_name} was rejected.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/<int:session_id>/no-attendance", methods=["POST"])
@admin_required
def set_no_attendance(session_id):
    session = db.get_or_404(AttendanceSession, session_id)
    enabled = request.form.get("no_attendance") == "on"
    session.no_attendance = enabled
    session.no_attendance_reason = request.form.get("reason", "").strip() or None
    db.session.commit()
    flash("Date marked as no attendance." if enabled else "Attendance restored for this date.", "success")
    return redirect(url_for("attendance.manage", session_id=session.id))


@attendance_bp.route("/attendance/history")
@login_required
def history():
    query = db.select(AttendanceLog).join(AttendanceSession).join(User).where(
        AttendanceSession.no_attendance.is_(False),
        User.role.notin_(NON_ATTENDANCE_ROLES),
    ).order_by(AttendanceSession.session_date.desc(), User.full_name)
    if current_user.role != "admin":
        query = query.where(AttendanceLog.user_id == current_user.id)
    records = db.session.execute(query.limit(1000)).scalars().all()
    return render_template("attendance/history.html", records=records)


@attendance_bp.route("/attendance/reports")
@login_required
def reports():
    query = db.select(AttendanceLog).join(AttendanceSession).join(User).where(
        AttendanceSession.no_attendance.is_(False),
        User.role.notin_(NON_ATTENDANCE_ROLES),
        AttendanceLog.approval_status.in_(["approved", "not_required"]),
    )
    if current_user.role != "admin":
        query = query.where(AttendanceLog.user_id == current_user.id)
    records = db.session.execute(query).scalars().all()
    stats = {}
    for record in records:
        item = stats.setdefault(record.user_id, {
            "user": record.user, "total": 0, "attended": 0,
            "late": 0, "excused": 0, "absent": 0, "minutes": 0,
        })
        item["total"] += 1
        if record.status in {"present", "late"}:
            item["attended"] += 1
        if record.status == "late":
            item["late"] += 1
        if record.status == "excused":
            item["excused"] += 1
        if record.status == "absent":
            item["absent"] += 1
        item["minutes"] += record.duration_minutes or 0
    for item in stats.values():
        item["attendance_rate"] = round(item["attended"] / item["total"] * 100, 1) if item["total"] else 0
    return render_template("attendance/reports.html", stats=sorted(stats.values(), key=lambda x: x["user"].full_name))
