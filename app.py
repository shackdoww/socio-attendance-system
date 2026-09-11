from flask import Flask, abort, redirect, render_template, url_for
from flask_login import LoginManager, current_user, login_required
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from dotenv import load_dotenv
import os
import re
from sqlalchemy import inspect, text

from extensions import db

load_dotenv()

login_manager = LoginManager()
login_manager.login_view = "auth.login"
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if os.getenv("FLASK_ENV", "development").lower() == "production":
            raise RuntimeError("SECRET_KEY must be set in production.")
        secret_key = "dev-secret-key-change-me"

    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///socio_attendance.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from models import Activity, Socio, Transaction, User
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.bulletin import bulletin_bp
    from routes.attendance import attendance_bp

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
        if user is None or not user.is_active:
            return None
        return user

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(bulletin_bp)
    app.register_blueprint(attendance_bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template(
            "errors/400.html",
            title="Security Check Failed",
            message="This form could not be verified. Please refresh the page and try again.",
        ), 400

    @app.errorhandler(400)
    def handle_bad_request(error):
        return render_template(
            "errors/400.html",
            title="Bad Request",
            message="The request could not be processed.",
        ), 400

    @app.errorhandler(403)
    def handle_forbidden(error):
        return render_template(
            "errors/403.html",
            title="Access Denied",
            message="You do not have permission to access this page.",
        ), 403

    @app.errorhandler(404)
    def handle_not_found(error):
        return render_template(
            "errors/404.html",
            title="Page Not Found",
            message="The page you requested does not exist.",
        ), 404

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.after_request
    def inject_shared_sidebar_script(response):
        if response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            marker = "</body>"
            script = '<script src="/static/js/sidebar.js?v=20260912"></script>'
            if marker in html and "static/js/sidebar.js" not in html:
                html = html.replace(marker, script + marker)

            logout_pattern = r'<a([^>]*class="nav-item"[^>]*)href="/logout"([^>]*)>(.*?)</a>'
            logout_replacement = (
                '<form method="post" action="/logout" style="margin:0">'
                '<button type="submit" class="nav-item" '
                'style="width:100%;border:0;background:transparent;text-align:left;'
                'font:inherit;cursor:pointer;">\g<3></button></form>'
            )
            html = re.sub(logout_pattern, logout_replacement, html, flags=re.IGNORECASE | re.DOTALL)

            if "<form" in html:
                token = generate_csrf()
                hidden_field = f'<input type="hidden" name="csrf_token" value="{token}">'
                html = re.sub(
                    r'(<form\b(?=[^>]*\bmethod=["\']?post\b)[^>]*>)',
                    lambda match: match.group(1) + hidden_field,
                    html,
                    flags=re.IGNORECASE,
                )
            response.set_data(html)
        return response

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.role == "admin":
                return redirect(url_for("dashboard"))
            return redirect(url_for("attendance.index"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.role != "admin":
            abort(403)

        user_count = db.session.scalar(db.select(db.func.count(User.id))) or 0
        socio_count = db.session.scalar(db.select(db.func.count(Socio.id))) or 0
        activity_count = db.session.scalar(db.select(db.func.count(Activity.id))) or 0
        transaction_count = db.session.scalar(db.select(db.func.count(Transaction.id))) or 0
        recent_users = db.session.execute(
            db.select(User).order_by(User.created_at.desc()).limit(8)
        ).scalars().all()

        return render_template(
            "dashboard.html",
            user_count=user_count,
            socio_count=socio_count,
            activity_count=activity_count,
            transaction_count=transaction_count,
            recent_users=recent_users,
        )

    @app.route("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            db.session.rollback()
            return {"status": "unhealthy"}, 503

    with app.app_context():
        import models
        db.create_all()

        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            inspector = inspect(db.engine)
            session_columns = {column["name"] for column in inspector.get_columns("attendance_sessions")}
            log_columns = {column["name"] for column in inspector.get_columns("attendance_logs")}

            if "no_attendance" not in session_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_sessions ADD COLUMN no_attendance BOOLEAN NOT NULL DEFAULT 0"
                ))
            if "no_attendance_reason" not in session_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_sessions ADD COLUMN no_attendance_reason VARCHAR(255)"
                ))
            if "approval_status" not in log_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_logs ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required'"
                ))
            if "approved_by" not in log_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_logs ADD COLUMN approved_by INTEGER"
                ))
            if "approved_at" not in log_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_logs ADD COLUMN approved_at DATETIME"
                ))
            if "rejection_reason" not in log_columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_logs ADD COLUMN rejection_reason VARCHAR(255)"
                ))
            db.session.execute(text(
                "UPDATE attendance_logs SET status = 'present' WHERE status = 'practicing'"
            ))
            db.session.commit()

        default_socios = [
            "NDMU Rondalla Ensemble",
            "NDMU Symphonic Band",
            "NDMU Tambuli Singers",
            "NDMU Kariktan Dancers",
        ]

        for socio_name in default_socios:
            existing = db.session.execute(
                db.select(Socio).where(Socio.name == socio_name)
            ).scalar_one_or_none()
            if existing is None:
                db.session.add(Socio(name=socio_name))

        db.session.commit()

    return app


app = create_app()


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
