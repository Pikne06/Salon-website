import sqlite3

def get_conn():
    return sqlite3.connect("users.db")

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
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
    """)
    
    # Services table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        price REAL NOT NULL
    )
    """)
    
    # Appointments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        service_id INTEGER,
        phone_number TEXT DEFAULT NULL,
        FOREIGN KEY(username) REFERENCES users(username),
        FOREIGN KEY(service_id) REFERENCES services(id)
    )
    """)
    
    conn.commit()
    conn.close()