# Socio Attendance System

A web-based attendance and socio organization management system for Notre Dame of Marbel University.

## Stack

- Python
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF / CSRF protection
- Flask-Limiter
- Flask-Migrate / Alembic
- HTML, CSS, JavaScript
- SQLite for development
- PostgreSQL for production

## Roles

- System Administrator
- Socio Moderator
- President
- Vice President
- Secretary
- Treasurer
- Socio Member

The Administrator manages the whole system. Socio Moderators supervise their assigned socio. Officers manage operational work within their own socio. Bulletin Board posting is restricted to Administrators; all other roles can only view announcements and events.

## Development

This project is being developed with IntelliJ IDEA and managed through GitHub.

1. Install dependencies:

       py -m pip install -r requirements.txt

2. Copy `.env.example` to `.env` and set a local `SECRET_KEY`.
3. Run the development server:

       py app.py

Development keeps `AUTO_CREATE_DB=1` by default so the existing SQLite workflow remains simple.

## Database migrations

Production deployments use Flask-Migrate instead of automatic table creation.

Apply migrations:

    flask --app app db upgrade

Create a migration after changing models:

    flask --app app db migrate -m "describe the change"

Review generated migrations before committing them.

For an existing database whose schema already matches the checked-in initial migration, mark it as migrated once:

    flask --app app db stamp 20260912_0001

Do not use `stamp` on a database whose schema does not actually match the migration.

## Production configuration

Production should set:

- `FLASK_ENV=production`
- a strong random `SECRET_KEY`
- `SESSION_COOKIE_SECURE=1` behind HTTPS
- PostgreSQL through `DATABASE_URL`
- shared rate-limit storage through `RATELIMIT_STORAGE_URI`, preferably Redis
- `TRUSTED_HOSTS` for the real application hostnames
- `AUTO_CREATE_DB=0`

The production application should be run behind a real WSGI server rather than Flask's development server.
