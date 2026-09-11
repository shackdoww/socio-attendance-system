from collections import OrderedDict

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from extensions import db
from models import Socio, User

members_bp = Blueprint("members", __name__, url_prefix="/members")

MEMBER_ROLES = {
    "socio_moderator": "Socio Moderator",
    "president": "President",
    "vice_president": "Vice President",
    "secretary": "Secretary",
    "treasurer": "Treasurer",
    "member": "Member",
}

ROLE_ORDER = [
    "socio_moderator",
    "president",
    "vice_president",
    "secretary",
    "treasurer",
    "member",
]


@members_bp.route("")
@login_required
def index():
    search = request.args.get("search", "").strip()
    selected_socio = request.args.get("socio", "").strip()
    selected_role = request.args.get("role", "").strip()
    selected_status = request.args.get("status", "active").strip().lower()

    query = db.select(User).where(User.role != "admin")

    if current_user.role != "admin":
        query = query.where(User.socio_id == current_user.socio_id)
    elif selected_socio:
        try:
            query = query.where(User.socio_id == int(selected_socio))
        except ValueError:
            selected_socio = ""

    if search:
        term = f"%{search}%"
        query = query.where(
            db.or_(
                User.full_name.ilike(term),
                User.username.ilike(term),
                User.email.ilike(term),
            )
        )

    if selected_role in MEMBER_ROLES:
        query = query.where(User.role == selected_role)

    if selected_status == "active":
        query = query.where(User.is_active.is_(True))
    elif selected_status == "inactive":
        query = query.where(User.is_active.is_(False))
    else:
        selected_status = "all"

    users = db.session.execute(
        query.order_by(User.socio_id, User.role, User.full_name)
    ).scalars().all()

    if current_user.role == "admin":
        socios = db.session.execute(db.select(Socio).order_by(Socio.name)).scalars().all()
    else:
        socios = [current_user.socio] if current_user.socio else []

    grouped = OrderedDict()
    for user in users:
        socio_name = user.socio.name if user.socio else "Unassigned"
        grouped.setdefault(socio_name, []).append(user)

    return render_template(
        "members/index.html",
        users=users,
        grouped_members=grouped,
        socios=socios,
        roles=MEMBER_ROLES,
        role_order=ROLE_ORDER,
        search=search,
        selected_socio=selected_socio,
        selected_role=selected_role,
        selected_status=selected_status,
    )
