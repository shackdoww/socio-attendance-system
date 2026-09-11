from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import BulletinPost
from routes.admin import admin_required


bulletin_bp = Blueprint("bulletin", __name__)


@bulletin_bp.route("/bulletin")
@login_required
def index():
    posts = db.session.execute(
        db.select(BulletinPost).order_by(BulletinPost.published_at.desc())
    ).scalars().all()
    return render_template("bulletin.html", posts=posts)


@bulletin_bp.route("/admin/bulletin")
@admin_required
def manage():
    posts = db.session.execute(
        db.select(BulletinPost).order_by(BulletinPost.published_at.desc())
    ).scalars().all()
    return render_template("admin/bulletin.html", posts=posts)


@bulletin_bp.route("/admin/bulletin/create", methods=["POST"])
@admin_required
def create():
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    post_type = request.form.get("post_type", "announcement")
    event_at_text = request.form.get("event_at", "").strip()
    location = request.form.get("location", "").strip()

    if post_type not in {"announcement", "event"}:
        post_type = "announcement"

    if not title or not content:
        flash("Title and content are required.", "error")
        return redirect(url_for("bulletin.manage"))

    event_at = None
    if post_type == "event":
        if not event_at_text:
            flash("Event date and time are required for future events.", "error")
            return redirect(url_for("bulletin.manage"))
        try:
            event_at = datetime.fromisoformat(event_at_text)
        except ValueError:
            flash("Invalid event date and time.", "error")
            return redirect(url_for("bulletin.manage"))

    post = BulletinPost(
        title=title,
        content=content,
        post_type=post_type,
        event_at=event_at,
        location=location or None,
        author_id=current_user.id,
    )
    db.session.add(post)
    db.session.commit()

    flash("Bulletin post published successfully.", "success")
    return redirect(url_for("bulletin.manage"))


@bulletin_bp.route("/admin/bulletin/<int:post_id>/edit", methods=["POST"])
@admin_required
def edit(post_id):
    post = db.get_or_404(BulletinPost, post_id)
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    post_type = request.form.get("post_type", "announcement")
    event_at_text = request.form.get("event_at", "").strip()
    location = request.form.get("location", "").strip()

    if post_type not in {"announcement", "event"}:
        post_type = "announcement"

    if not title or not content:
        flash("Title and content are required.", "error")
        return redirect(url_for("bulletin.manage"))

    event_at = None
    if post_type == "event":
        if not event_at_text:
            flash("Event date and time are required for future events.", "error")
            return redirect(url_for("bulletin.manage"))
        try:
            event_at = datetime.fromisoformat(event_at_text)
        except ValueError:
            flash("Invalid event date and time.", "error")
            return redirect(url_for("bulletin.manage"))

    post.title = title
    post.content = content
    post.post_type = post_type
    post.event_at = event_at
    post.location = location or None
    db.session.commit()

    flash("Bulletin post updated successfully.", "success")
    return redirect(url_for("bulletin.manage"))


@bulletin_bp.route("/admin/bulletin/<int:post_id>/delete", methods=["POST"])
@admin_required
def delete(post_id):
    post = db.get_or_404(BulletinPost, post_id)
    db.session.delete(post)
    db.session.commit()

    flash("Bulletin post deleted successfully.", "success")
    return redirect(url_for("bulletin.manage"))
