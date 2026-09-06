from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from db import get_conn


class ServiceNotFoundError(Exception):
    pass


def list_services() -> List[Tuple[int, str, float, Optional[str], int, Optional[str], Optional[str], Optional[str]]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, price, image_url, duration, description, includes_text, aftercare_text FROM services ORDER BY name"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        (
            row["id"],
            row["name"],
            row["price"],
            row["image_url"],
            row["duration"] or 60,
            row["description"],
            row["includes_text"],
            row["aftercare_text"],
        )
        for row in rows
    ]


def add_service(
    name: str,
    price: float,
    image_url: Optional[str] = None,
    duration: int = 60,
    description: Optional[str] = None,
    includes_text: Optional[str] = None,
    aftercare_text: Optional[str] = None,
) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO services (name, price, image_url, duration, description, includes_text, aftercare_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, price, image_url, duration, description, includes_text, aftercare_text),
    )
    conn.commit()
    conn.close()


def remove_service(service_id: int) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id = ?", (service_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise ServiceNotFoundError(f"Service with id {service_id} not found")
    conn.commit()
    conn.close()


def seed_services(defaults: Optional[Iterable[Tuple[str, float]]] = None) -> None:
    if defaults is None:
        defaults = [
            ("Consultation", 49.0, 45),
            ("Follow-up", 29.0, 30),
            ("Premium Support", 99.0, 90),
        ]
    for name, price, duration in defaults:
        add_service(name, price, None, duration)