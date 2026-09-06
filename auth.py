from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from db import get_conn
from utils import hash_password, verify_password, validate_password, is_legacy_hash
import hashlib


@dataclass
class User:
    id: int
    username: str
    password: str
    email: Optional[str]
    is_admin: bool

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row["id"],
            username=row["username"],
            password=row["password"],
            email=row["email"],
            is_admin=bool(row["is_admin"]),
        )


def get_user(username: str) -> Optional[User]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return User.from_row(row)
    return None


def register_user(username: str, email: str, password: str) -> Tuple[bool, str]:
    valid, message = validate_password(password)
    if not valid:
        return False, message

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return False, "Username already exists."

    cursor.execute("SELECT 1 FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False, "An account with this email already exists."

    cursor.execute(
        "INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
        (username, hash_password(password), email),
    )
    conn.commit()
    conn.close()
    return True, "Registration successful."


def authenticate_user(username: str, password: str) -> Tuple[bool, Optional[User]]:
    user = get_user(username)
    if not user:
        return False, None
    # Modern check
    if verify_password(password, user.password):
        return True, user

    # Support legacy SHA-256 hashes: if password matches legacy hash, upgrade it
    if is_legacy_hash(user.password):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if legacy == user.password:
            # upgrade hash in database
            new_hash = hash_password(password)
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_hash, username))
            conn.commit()
            conn.close()
            return True, user

    return False, None


def change_password(username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
    user = get_user(username)
    if not user:
        return False, "User not found."
    if not verify_password(current_password, user.password):
        return False, "Current password is incorrect."

    valid, message = validate_password(new_password)
    if not valid:
        return False, message

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = ? WHERE username = ?",
        (hash_password(new_password), username),
    )
    conn.commit()
    conn.close()
    return True, "Password updated successfully."


def delete_user(username: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()


def update_email(username: str, email: str) -> Tuple[bool, str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE email = ? AND username != ?", (email, username))
    if cursor.fetchone():
        conn.close()
        return False, "Email already in use."

    cursor.execute("UPDATE users SET email = ? WHERE username = ?", (email, username))
    conn.commit()
    conn.close()
    return True, "Email updated."