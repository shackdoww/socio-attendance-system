import sys
from pathlib import Path

# Allow this script to import the application modules from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date, datetime, time, timedelta

from extensions import db
from models import AttendanceLog, AttendanceSession, Socio, User


DEMO_PASSWORD = "Demo123!"

SOCIOS = [
    ("NDMU Rondalla Ensemble", "Demo members for attendance and role testing."),
    ("NDMU Symphonic Band", "Demo members for attendance and role testing."),
    ("NDMU Tambuli Singers", "Demo members for attendance and role testing."),
    ("NDMU Kariktan Dancers", "Demo members for attendance and role testing."),
]

PEOPLE = [
    ("Moderator", "socio_moderator"),
    ("President", "president"),
    ("Vice President", "vice_president"),
    ("Secretary", "secretary"),
    ("Treasurer", "treasurer"),
    ("Member 01", "member"),
    ("Member 02", "member"),
    ("Member 03", "member"),
    ("Member 04", "member"),
    ("Member 05", "member"),
]

ATTENDANCE_STATUSES = ["present", "practicing", "late", "excused", "absent"]


def get_or_create_socio(name, description):
    socio = db.session.execute(
        db.select(Socio).where(Socio.name == name)
    ).scalar_one_or_none()

    if socio is None:
        socio = Socio(name=name, description=description)
        db.session.add(socio)
        db.session.flush()
    elif not socio.description:
        socio.description = description

    return socio


def get_or_create_user(socio, index, label, role):
    username = f"demo_{socio.id}_{index}"
    email = f"{username}@example.test"

    user = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalar_one_or_none()

    if user is None:
        user = User(
            username=username,
            email=email,
            full_name=f"{label} {socio.name.replace('NDMU ', '')}",
            role=role,
            socio_id=socio.id,
            is_active=True,
        )
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
    else:
        user.role = role
        user.socio_id = socio.id
        user.is_active = True

    return user


def seed_attendance(socio, users):
    participants = [user for user in users if user.role not in {"admin", "socio_moderator"}]
    today = date.today()

    for day_offset in range(13, -1, -1):
        attendance_date = today - timedelta(days=day_offset)
        session = db.session.execute(
            db.select(AttendanceSession).where(
                AttendanceSession.socio_id == socio.id,
                AttendanceSession.session_date == attendance_date,
            )
        ).scalar_one_or_none()

        if session is None:
            session = AttendanceSession(
                socio_id=socio.id,
                session_date=attendance_date,
                session_type="regular",
                no_attendance=(day_offset == 7),
                no_attendance_reason="Demo holiday / no attendance day" if day_offset == 7 else None,
                created_by=participants[0].id,
            )
            db.session.add(session)
            db.session.flush()

        if session.no_attendance:
            continue

        for index, user in enumerate(participants):
            record = db.session.execute(
                db.select(AttendanceLog).where(
                    AttendanceLog.session_id == session.id,
                    AttendanceLog.user_id == user.id,
                )
            ).scalar_one_or_none()

            status = ATTENDANCE_STATUSES[(index + day_offset) % len(ATTENDANCE_STATUSES)]

            if record is None:
                record = AttendanceLog(
                    session_id=session.id,
                    user_id=user.id,
                )
                db.session.add(record)

            record.status = status
            record.notes = "Demo attendance record" if status != "absent" else "Demo absent record"

            if status in {"present", "practicing", "late"}:
                start_hour = 16 + (index % 2)
                start_minute = (index * 7) % 45
                duration = 60 + ((index + day_offset) % 5) * 30
                start = datetime.combine(attendance_date, time(start_hour, start_minute))
                end = start + timedelta(minutes=duration)
                record.time_in = start.time()
                record.time_out = end.time()
                record.duration_minutes = duration
            else:
                record.time_in = None
                record.time_out = None
                record.duration_minutes = None


def main():
    from app import create_app

    app = create_app()

    with app.app_context():
        created_users = 0
        socios = []

        for name, description in SOCIOS:
            socio = get_or_create_socio(name, description)
            socios.append(socio)

        db.session.commit()

        for socio in socios:
            users = []
            for index, (label, role) in enumerate(PEOPLE, start=1):
                before = db.session.execute(
                    db.select(User).where(User.username == f"demo_{socio.id}_{index}")
                ).scalar_one_or_none()
                user = get_or_create_user(socio, index, label, role)
                if before is None:
                    created_users += 1
                users.append(user)

            db.session.flush()
            seed_attendance(socio, users)

        db.session.commit()

        print("Demo data is ready.")
        print(f"Socios: {len(socios)}")
        print(f"Demo users created: {created_users}")
        print(f"Demo password: {DEMO_PASSWORD}")
        print()
        print("Usernames follow this pattern:")
        print("  demo_<socio_id>_<person_number>")
        print("Example: demo_1_6")
        print("The first five accounts in each socio are moderator/president/VP/secretary/treasurer.")
        print("The remaining five are members.")
        print("Attendance history for the last 14 days was also generated for testing.")


if __name__ == "__main__":
    main()
