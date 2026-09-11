from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class Socio(db.Model):
    __tablename__ = "socios"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    users = db.relationship("User", back_populates="socio", lazy=True)
    activities = db.relationship("Activity", back_populates="socio", cascade="all, delete-orphan", lazy=True)
    transactions = db.relationship("Transaction", back_populates="socio", cascade="all, delete-orphan", lazy=True)
    attendance_sessions = db.relationship("AttendanceSession", back_populates="socio", cascade="all, delete-orphan", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="member")
    socio_id = db.Column(db.Integer, db.ForeignKey("socios.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    socio = db.relationship("Socio", back_populates="users")
    attendance_records = db.relationship("Attendance", back_populates="user", cascade="all, delete-orphan", lazy=True)
    daily_attendance_records = db.relationship("AttendanceLog", back_populates="user", cascade="all, delete-orphan", lazy=True)
    bulletin_posts = db.relationship("BulletinPost", back_populates="author", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Activity(db.Model):
    __tablename__ = "activities"
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey("socios.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    socio = db.relationship("Socio", back_populates="activities")
    attendance_records = db.relationship("Attendance", back_populates="activity", cascade="all, delete-orphan", lazy=True)


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="absent")
    checked_in_at = db.Column(db.DateTime)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    activity = db.relationship("Activity", back_populates="attendance_records")
    user = db.relationship("User", back_populates="attendance_records")
    __table_args__ = (db.UniqueConstraint("activity_id", "user_id", name="uq_activity_user_attendance"),)


class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey("socios.id"), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    session_type = db.Column(db.String(20), nullable=False, default="regular")
    no_attendance = db.Column(db.Boolean, nullable=False, default=False)
    no_attendance_reason = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    socio = db.relationship("Socio", back_populates="attendance_sessions")
    records = db.relationship("AttendanceLog", back_populates="session", cascade="all, delete-orphan", lazy=True)
    __table_args__ = (db.UniqueConstraint("socio_id", "session_date", name="uq_socio_attendance_date"),)


class AttendanceLog(db.Model):
    __tablename__ = "attendance_logs"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_sessions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="absent")
    time_in = db.Column(db.Time)
    time_out = db.Column(db.Time)
    duration_minutes = db.Column(db.Integer)
    notes = db.Column(db.String(255))
    approval_status = db.Column(db.String(20), nullable=False, default="not_required")
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(255))
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    session = db.relationship("AttendanceSession", back_populates="records")
    user = db.relationship("User", back_populates="daily_attendance_records", foreign_keys=[user_id])
    approver = db.relationship("User", foreign_keys=[approved_by])
    __table_args__ = (db.UniqueConstraint("session_id", "user_id", name="uq_daily_attendance_user"),)


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    socio_id = db.Column(db.Integer, db.ForeignKey("socios.id"), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    socio = db.relationship("Socio", back_populates="transactions")


class BulletinPost(db.Model):
    __tablename__ = "bulletin_posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    post_type = db.Column(db.String(20), nullable=False, default="announcement")
    event_at = db.Column(db.DateTime)
    location = db.Column(db.String(200))
    published_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author = db.relationship("User", back_populates="bulletin_posts")
