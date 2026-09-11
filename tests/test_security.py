import os
import re
import uuid

import pytest

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["FLASK_ENV"] = "testing"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

from app import create_app
from extensions import db
from models import Socio, User


def create_test_app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    return app


def create_user(role="member", active=True, socio_id=None):
    suffix = uuid.uuid4().hex
    user = User(
        username=f"test_{role}_{suffix}",
        email=f"test_{role}_{suffix}@example.com",
        full_name="Test User",
        role=role,
        socio_id=socio_id,
        is_active=active,
    )
    user.set_password("TestPass123!")
    db.session.add(user)
    db.session.commit()
    return user


def csrf_token(client, path):
    page = client.get(path)
    assert page.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
    assert match
    return match.group(1)


def authenticate(client, user):
    token = csrf_token(client, "/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": token,
            "username": user.username,
            "password": "TestPass123!",
        },
    )
    assert response.status_code == 302


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


def test_login_is_rate_limited():
    app = create_test_app()
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            responses = [
                client.post(
                    "/login",
                    data={"username": user.username, "password": "wrong"},
                )
                for _ in range(6)
            ]
            assert responses[-1].status_code == 429


def test_dashboard_forbidden_for_member():
    app = create_test_app()
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            authenticate(client, user)
            response = client.get("/dashboard")
            assert response.status_code == 403


def test_admin_area_forbidden_for_member():
    app = create_test_app()
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            authenticate(client, user)
            response = client.get("/admin/users")
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
            authenticate(client, user)
            assert client.get("/logout").status_code == 405
            response = client.post("/logout")
            assert response.status_code == 400


def test_security_headers_are_present():
    app = create_test_app()
    with app.test_client() as client:
        response = client.get("/login")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers


def test_member_cannot_post_bulletin():
    app = create_test_app()
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        user = create_user()
        with app.test_client() as client:
            authenticate(client, user)
            response = client.post("/admin/bulletin/create", data={
                "title": "Unauthorized",
                "content": "Should not be published",
            })
            assert response.status_code == 403


def test_admin_can_post_bulletin():
    app = create_test_app()
    with app.app_context():
        user = create_user(role="admin", socio_id=None)
        with app.test_client() as client:
            authenticate(client, user)
            token = csrf_token(client, "/admin/bulletin")
            response = client.post(
                "/admin/bulletin/create",
                data={
                    "csrf_token": token,
                    "title": "Test announcement",
                    "content": "Test content",
                    "post_type": "announcement",
                },
            )
            assert response.status_code == 302


@pytest.mark.parametrize("path", ["/admin/users", "/admin/socios"])
def test_admin_pages_require_admin(path):
    app = create_test_app()
    with app.app_context():
        user = create_user(role="member")
        with app.test_client() as client:
            authenticate(client, user)
            assert client.get(path).status_code == 403


def test_members_directory_is_available_to_members():
    app = create_test_app()
    with app.app_context():
        socio = db.session.execute(db.select(Socio).limit(1)).scalar_one()
        member = create_user(socio_id=socio.id)
        create_user(role="treasurer", socio_id=socio.id)
        with app.test_client() as client:
            authenticate(client, member)
            response = client.get("/members")
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert "Members" in body
            assert "Test User" in body
            assert "Treasurer" in body


def test_members_directory_is_limited_to_current_socio():
    app = create_test_app()
    with app.app_context():
        socios = db.session.execute(db.select(Socio).order_by(Socio.id).limit(2)).scalars().all()
        first_member = create_user(socio_id=socios[0].id)
        other_member = create_user(socio_id=socios[1].id)
        with app.test_client() as client:
            authenticate(client, first_member)
            response = client.get("/members")
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert first_member.email in body
            assert other_member.email not in body


def test_admin_can_filter_members_by_socio_and_assignment():
    app = create_test_app()
    with app.app_context():
        socios = db.session.execute(db.select(Socio).order_by(Socio.id).limit(2)).scalars().all()
        admin = create_user(role="admin")
        first_member = create_user(socio_id=socios[0].id)
        first_treasurer = create_user(role="treasurer", socio_id=socios[0].id)
        second_member = create_user(socio_id=socios[1].id)
        with app.test_client() as client:
            authenticate(client, admin)
            response = client.get(f"/members?socio={socios[0].id}&role=treasurer")
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert first_treasurer.email in body
            assert first_member.email not in body
            assert second_member.email not in body
