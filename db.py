import sqlite3
from pathlib import Path

DB_PATH = Path("users.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            failed_attempts INTEGER DEFAULT 0,
            lock_until INTEGER DEFAULT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            last_login INTEGER DEFAULT NULL,
            is_admin INTEGER DEFAULT 0,
            email TEXT DEFAULT NULL,
            reset_token TEXT DEFAULT NULL,
            reset_expiry INTEGER DEFAULT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            image_url TEXT DEFAULT NULL,
            duration INTEGER DEFAULT 60,
            description TEXT DEFAULT NULL,
            includes_text TEXT DEFAULT NULL,
            aftercare_text TEXT DEFAULT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            service_id INTEGER,
            phone_number TEXT DEFAULT NULL,
            email TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            FOREIGN KEY(username) REFERENCES users(username),
            FOREIGN KEY(service_id) REFERENCES services(id)
        )
        """
    )

    # Migrate existing appointments table (add optional columns if missing)
    cursor.execute("PRAGMA table_info(appointments)")
    cols = {row[1] for row in cursor.fetchall()}
    if "email" not in cols:
        try:
            cursor.execute("ALTER TABLE appointments ADD COLUMN email TEXT DEFAULT NULL")
        except Exception:
            pass
    if "notes" not in cols:
        try:
            cursor.execute("ALTER TABLE appointments ADD COLUMN notes TEXT DEFAULT NULL")
        except Exception:
            pass
    # Ensure services have image_url column for optional thumbnails
    cursor.execute("PRAGMA table_info(services)")
    svc_cols = {row[1] for row in cursor.fetchall()}
    if "image_url" not in svc_cols:
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN image_url TEXT DEFAULT NULL")
        except Exception:
            pass
    if "duration" not in svc_cols:
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN duration INTEGER DEFAULT 60")
        except Exception:
            pass
    if "description" not in svc_cols:
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN description TEXT DEFAULT NULL")
        except Exception:
            pass
    if "includes_text" not in svc_cols:
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN includes_text TEXT DEFAULT NULL")
        except Exception:
            pass
    if "aftercare_text" not in svc_cols:
        try:
            cursor.execute("ALTER TABLE services ADD COLUMN aftercare_text TEXT DEFAULT NULL")
        except Exception:
            pass

    # Technicians table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS technicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT DEFAULT NULL,
            phone TEXT DEFAULT NULL,
            title TEXT DEFAULT NULL,
            bio TEXT DEFAULT NULL,
            photo_url TEXT DEFAULT NULL,
            specialties TEXT DEFAULT NULL,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    # Add schedule columns if missing
    cursor.execute("PRAGMA table_info(technicians)")
    tech_cols = {row[1] for row in cursor.fetchall()}
    if "work_start" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN work_start TEXT DEFAULT '10:00'")
        except Exception:
            pass
    if "work_end" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN work_end TEXT DEFAULT '18:00'")
        except Exception:
            pass
    if "title" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN title TEXT DEFAULT NULL")
        except Exception:
            pass
    if "bio" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN bio TEXT DEFAULT NULL")
        except Exception:
            pass
    if "photo_url" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN photo_url TEXT DEFAULT NULL")
        except Exception:
            pass
    if "specialties" not in tech_cols:
        try:
            cursor.execute("ALTER TABLE technicians ADD COLUMN specialties TEXT DEFAULT NULL")
        except Exception:
            pass

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS technician_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            start_time TEXT DEFAULT '10:00',
            end_time TEXT DEFAULT '18:00',
            is_closed INTEGER DEFAULT 0,
            UNIQUE(technician_id, weekday),
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS technician_vacations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT DEFAULT NULL,
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS availability_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_booked INTEGER DEFAULT 0,
            booked_by TEXT DEFAULT NULL,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS waitlist_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER DEFAULT NULL,
            technician_id INTEGER DEFAULT NULL,
            name TEXT DEFAULT NULL,
            email TEXT DEFAULT NULL,
            phone TEXT DEFAULT NULL,
            preferred_date TEXT DEFAULT NULL,
            preferred_time TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            status TEXT DEFAULT 'new',
            created_at INTEGER DEFAULT (strftime('%s','now')),
            FOREIGN KEY(service_id) REFERENCES services(id),
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    # Messages table (simple message log)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER,
            username TEXT,
            message TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    # Service photos and reviews
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS service_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER,
            technician_id INTEGER DEFAULT NULL,
            image_url TEXT,
            caption TEXT DEFAULT NULL,
            FOREIGN KEY(service_id) REFERENCES services(id),
            FOREIGN KEY(technician_id) REFERENCES technicians(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER,
            username TEXT,
            rating INTEGER DEFAULT 5,
            comment TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            FOREIGN KEY(service_id) REFERENCES services(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS site_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT DEFAULT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS site_faqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS featured_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT DEFAULT NULL,
            quote TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
        """
    )

    # Add technician_id to appointments if missing
    cursor.execute("PRAGMA table_info(appointments)")
    appt_cols = {row[1] for row in cursor.fetchall()}
    if "technician_id" not in appt_cols:
        try:
            cursor.execute("ALTER TABLE appointments ADD COLUMN technician_id INTEGER DEFAULT NULL")
        except Exception:
            pass

    cursor.execute("PRAGMA table_info(availability_slots)")
    slot_cols = {row[1] for row in cursor.fetchall()}
    if "end_time" not in slot_cols:
        try:
            cursor.execute("ALTER TABLE availability_slots ADD COLUMN end_time TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
    if "is_booked" not in slot_cols:
        try:
            cursor.execute("ALTER TABLE availability_slots ADD COLUMN is_booked INTEGER DEFAULT 0")
        except Exception:
            pass
    if "booked_by" not in slot_cols:
        try:
            cursor.execute("ALTER TABLE availability_slots ADD COLUMN booked_by TEXT DEFAULT NULL")
        except Exception:
            pass

    cursor.execute("PRAGMA table_info(service_photos)")
    photo_cols = {row[1] for row in cursor.fetchall()}
    if "technician_id" not in photo_cols:
        try:
            cursor.execute("ALTER TABLE service_photos ADD COLUMN technician_id INTEGER DEFAULT NULL")
        except Exception:
            pass

    conn.commit()
    conn.close()


def seed_admin(hash_password):
    conn = get_conn()
    cursor = conn.cursor()
    admin_username = "admin"
    admin_password = hash_password("ChangeMe123!")

    cursor.execute("SELECT id, is_admin FROM users WHERE username = ?", (admin_username,))
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
            (admin_username, admin_password, 1),
        )
        conn.commit()
    elif not row["is_admin"]:
        cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (admin_username,))
        conn.commit()
    conn.close()


def is_admin(username):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    return bool(result and result["is_admin"])