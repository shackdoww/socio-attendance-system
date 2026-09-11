from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from models import Socio, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


ALLOWED_ROLES = {
    "admin",
    "socio_moderator",
    "president",
    "vice_president",
    "secretary",
    "treasurer",
    "member",
}

OFFICER_ROLES = [
    ("president", "President"),
    ("vice_president", "Vice President"),
    ("secretary", "Secretary"),
    ("treasurer", "Treasurer"),
]

SOCIO_ROLES = {"socio_moderator", "president", "vice_president", "secretary", "treasurer", "member"}
LEADERSHIP_ROLES = {"socio_moderator", "president", "vice_president", "secretary", "treasurer"}


def admin_required(view):
    from functools import wraps

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            return "Forbidden", 403
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/users")
@admin_required
def users():
    search = request.args.get("search", "").strip()
    query = db.select(User).order_by(User.created_at.desc())

    if search:
        term = f"%{search}%"
        query = query.where(
            or_(
                User.username.ilike(term),
                User.email.ilike(term),
                User.full_name.ilike(term),
            )
        )

    users = db.session.execute(query).scalars().all()
    socios = db.session.execute(db.select(Socio).order_by(Socio.name)).scalars().all()
    return render_template("admin/users.html", users=users, socios=socios, search=search)


@admin_bp.route("/socios")
@admin_required
def socios():
    socios = db.session.execute(db.select(Socio).order_by(Socio.name)).scalars().all()
    return render_template("admin/socios.html", socios=socios)


@admin_bp.route("/socios/<int:socio_id>")
@admin_required
def socio_detail(socio_id):
    socio = db.get_or_404(Socio, socio_id)
    members = db.session.execute(
        db.select(User).where(User.socio_id == socio.id).order_by(User.role, User.full_name)
    ).scalars().all()

    role_users = {}
    for role in ["socio_moderator", "president", "vice_president", "secretary", "treasurer"]:
        role_users[role] = db.session.execute(
            db.select(User)
            .where(User.role == role, User.is_active.is_(True))
            .order_by(User.full_name)
        ).scalars().all()

    assignments = {
        "socio_moderator": next((u for u in members if u.role == "socio_moderator"), None),
        "president": next((u for u in members if u.role == "president"), None),
        "vice_president": next((u for u in members if u.role == "vice_president"), None),
        "secretary": next((u for u in members if u.role == "secretary"), None),
        "treasurer": next((u for u in members if u.role == "treasurer"), None),
    }

    return render_template(
        "admin/socio_detail.html",
        socio=socio,
        members=members,
        role_users=role_users,
        assignments=assignments,
        officer_roles=OFFICER_ROLES,
    )


@admin_bp.route("/socios/create", methods=["POST"])
@admin_required
def create_socio():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("Socio group name is required.", "error")
        return redirect(url_for("admin.users"))

    existing = db.session.execute(
        db.select(Socio).where(Socio.name.ilike(name))
    ).scalar_one_or_none()

    if existing:
        flash("That socio group already exists.", "error")
        return redirect(url_for("admin.users"))

    socio = Socio(name=name, description=description or None)
    db.session.add(socio)
    db.session.commit()

    flash(f"Socio group '{name}' created successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/socios/<int:socio_id>/update", methods=["POST"])
@admin_required
def update_socio(socio_id):
    socio = db.get_or_404(Socio, socio_id)
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    if not name:
        flash("Socio group name is required.", "error")
        return redirect(url_for("admin.socio_detail", socio_id=socio.id))

    duplicate = db.session.execute(
        db.select(Socio).where(Socio.name.ilike(name), Socio.id != socio.id)
    ).scalar_one_or_none()
    if duplicate:
        flash("Another socio group already uses that name.", "error")
        return redirect(url_for("admin.socio_detail", socio_id=socio.id))

    socio.name = name
    socio.description = description or None
    db.session.commit()

    flash(f"Socio group '{name}' updated successfully.", "success")
    return redirect(url_for("admin.socio_detail", socio_id=socio.id))


@admin_bp.route("/socios/<int:socio_id>/assign", methods=["POST"])
@admin_required
def assign_socio_roles(socio_id):
    socio = db.get_or_404(Socio, socio_id)

    assignments = {
        "socio_moderator": request.form.get("socio_moderator_id") or None,
        "president": request.form.get("president_id") or None,
        "vice_president": request.form.get("vice_president_id") or None,
        "secretary": request.form.get("secretary_id") or None,
        "treasurer": request.form.get("treasurer_id") or None,
    }

    selected_ids = [int(value) for value in assignments.values() if value]
    if len(selected_ids) != len(set(selected_ids)):
        flash("A person cannot hold two officer positions in the same socio.", "error")
        return redirect(url_for("admin.socio_detail", socio_id=socio.id))

    for role, user_id in assignments.items():
        if user_id is None:
            continue

        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            user = None
        if not user or not user.is_active or user.role != role:
            flash("One or more selected users are invalid for their assigned position.", "error")
            return redirect(url_for("admin.socio_detail", socio_id=socio.id))

    managed_roles = ["socio_moderator", "president", "vice_president", "secretary", "treasurer"]
    for role in managed_roles:
        users_in_role = db.session.execute(
            db.select(User).where(User.socio_id == socio.id, User.role == role)
        ).scalars().all()
        selected_id = assignments[role]
        for user in users_in_role:
            if selected_id is None or user.id != int(selected_id):
                user.socio_id = None

    for role, user_id in assignments.items():
        if user_id:
            user = db.session.get(User, int(user_id))
            user.socio_id = socio.id

    db.session.commit()
    flash(f"Leadership assignments for '{socio.name}' updated successfully.", "success")
    return redirect(url_for("admin.socio_detail", socio_id=socio.id))


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "member")
    socio_id = request.form.get("socio_id") or None

    if role not in ALLOWED_ROLES:
        flash("Invalid role selected.", "error")
        return redirect(url_for("admin.users"))

    if not username or not email or not full_name or not password:
        flash("All required fields must be filled in.", "error")
        return redirect(url_for("admin.users"))

    if db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none():
        flash("That username already exists.", "error")
        return redirect(url_for("admin.users"))

    if db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none():
        flash("That email already exists.", "error")
        return redirect(url_for("admin.users"))

    if role == "admin" and socio_id:
        flash("Administrator accounts cannot be assigned to a socio.", "error")
        return redirect(url_for("admin.users"))

    if role in SOCIO_ROLES and not socio_id:
        flash("A socio must be selected for this role.", "error")
        return redirect(url_for("admin.users"))

    if socio_id:
        try:
            socio = db.session.get(Socio, int(socio_id))
        except (TypeError, ValueError):
            socio = None
        if not socio:
            flash("The selected socio does not exist.", "error")
            return redirect(url_for("admin.users"))

        if role in LEADERSHIP_ROLES:
            existing_position = db.session.execute(
                db.select(User).where(User.socio_id == socio.id, User.role == role)
            ).scalar_one_or_none()
            if existing_position:
                flash(f"That socio already has a {role.replace('_', ' ').title()}.", "error")
                return redirect(url_for("admin.users"))

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        role=role,
        socio_id=int(socio_id) if socio_id else None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)

    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.users"))

    user.is_active = not user.is_active
    db.session.commit()
    status = "activated" if user.is_active else "deactivated"
    flash(f"User '{user.username}' {status}.", "success")
    return redirect(url_for("admin.users"))
