from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager, current_user, login_required
from dotenv import load_dotenv
import os
from sqlalchemy import inspect, text

from extensions import db

load_dotenv()

login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///socio_attendance.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    from models import Activity, Socio, Transaction, User
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.bulletin import bulletin_bp
    from routes.attendance import attendance_bp

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(bulletin_bp)
    app.register_blueprint(attendance_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
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
        return {"status": "ok"}

    with app.app_context():
        import models
        db.create_all()

        # Keep existing local SQLite databases compatible when new attendance fields are added.
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            inspector = inspect(db.engine)
            columns = {column["name"] for column in inspector.get_columns("attendance_sessions")}
            if "no_attendance" not in columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_sessions ADD COLUMN no_attendance BOOLEAN NOT NULL DEFAULT 0"
                ))
            if "no_attendance_reason" not in columns:
                db.session.execute(text(
                    "ALTER TABLE attendance_sessions ADD COLUMN no_attendance_reason VARCHAR(255)"
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
    app.run(debug=True)
