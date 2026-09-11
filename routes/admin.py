from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from models import Socio, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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


@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    full_name = request.form.get("full_name", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "member")
    socio_id = request.form.get("socio_id") or None

    allowed_roles = {"admin", "socio_moderator", "president", "vice_president", "secretary", "treasurer", "member"}
    if role not in allowed_roles:
        role = "member"

    if not username or not email or not full_name or not password:
        flash("All required fields must be filled in.", "error")
        return redirect(url_for("admin.users"))

    if db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none():
        flash("That username already exists.", "error")
        return redirect(url_for("admin.users"))

    if db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none():
        flash("That email already exists.", "error")
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
