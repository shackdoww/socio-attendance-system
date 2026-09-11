from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager, current_user, login_required
from dotenv import load_dotenv
import os

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

    from models import Socio, User
    from routes.auth import auth_bp
    from routes.admin import admin_bp

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    with app.app_context():
        import models
        db.create_all()

        default_socios = [
            "NDMU Rondalla Ensemble",
            "NDMU Symphonic Band",
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
