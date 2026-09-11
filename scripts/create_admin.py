from getpass import getpass

from app import app
from extensions import db
from models import User


def main():
    with app.app_context():
        username = input("Admin username: ").strip()
        email = input("Admin email: ").strip()
        full_name = input("Admin full name: ").strip()

        if not username or not email or not full_name:
            print("Username, email, and full name are required.")
            return

        if db.session.execute(db.select(User).where(User.username == username)).scalar_one_or_none():
            print("That username already exists.")
            return

        if db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none():
            print("That email already exists.")
            return

        password = getpass("Admin password: ")
        confirm_password = getpass("Confirm password: ")

        if not password:
            print("Password cannot be empty.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            role="admin",
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        print(f"Admin account '{username}' created successfully.")


if __name__ == "__main__":
    main()
