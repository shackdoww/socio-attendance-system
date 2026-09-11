import os
import re

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "testing"

from app import create_app
from extensions import db
from models import Socio, User


def create_test_app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    return app


def create_user(role="member", active=True, socio_id=None):
    user = User(
        username=f"test_{role}_{id(object())}",
        email=f"test_{role}_{id(object())}@example.com",
        full_name="Test User",
        role=role,
        socio_id=socio_id,
        is_active=active,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def test_login_page_contains_csrf_token():
    app = create_test_app()
    with app.test_client() as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert re.search(r'name="csrf_token"', response.get_data(as_text=True))


def test_login_rejects_missing_csrf_token():
    app = create_test_app()
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            response = client.post(
                "/login",
                data={"username": user.username, "password": "TestPass123!"},
            )
            assert response.status_code == 400


def test_dashboard_forbidden_for_member():
    app = create_test_app()
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_user_id"] = str(user.id)
                session["_fresh"] = True
            response = client.get("/dashboard")
            assert response.status_code == 403


def test_inactive_user_is_not_loaded():
    app = create_test_app()
    with app.app_context():
        user = create_user(active=False)
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_user_id"] = str(user.id)
                session["_fresh"] = True
            response = client.get("/attendance")
            assert response.status_code == 302
            assert "/login" in response.headers["Location"]


def test_logout_requires_post_and_csrf():
    app = create_test_app()
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            with client.session_transaction() as session:
                session["_user_id"] = str(user.id)
                session["_fresh"] = True
            assert client.get("/logout").status_code == 405
            response = client.post("/logout")
            assert response.status_code == 400
