from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import List, Optional, Tuple

from db import get_conn

__all__ = [
    "AppointmentError",
    "get_appointments",
    "is_slot_available",
    "has_technician_overlap",
    "book_appointment",
]

BUSINESS_START = time(10, 0)
BUSINESS_END = time(18, 0)
ALLOWED_MINUTES = {0, 15, 30, 45}


class AppointmentError(Exception):
    pass


def get_appointments(username: str) -> List[Tuple[int, datetime, str, float, Optional[str]]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.id, a.appointment_time, s.name, s.price, t.id as technician_id, t.name as technician
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN technicians t ON a.technician_id = t.id
        WHERE a.username = ?
        ORDER BY a.appointment_time
        """,
        (username,),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        result.append(
            (
                row["id"],
                datetime.fromisoformat(row["appointment_time"]),
                row["name"] if row["name"] else "Unknown Service",
                row["price"] if row["price"] else 0.0,
                (row["technician_id"] if "technician_id" in row.keys() else None),
                (row["technician"] if "technician" in row.keys() and row["technician"] else None),
            )
        )
    return result


def is_slot_available(start_time: datetime) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM appointments WHERE appointment_time = ?",
        (start_time.isoformat(),),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return not exists


def _get_service_duration(service_id: int) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT duration FROM services WHERE id = ?", (service_id,))
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row and row[0] else 60


def is_technician_available(technician_id: Optional[int], start: datetime, end: datetime) -> bool:
    if not technician_id:
        return True
    conn = get_conn()
    cursor = conn.cursor()
    weekday = start.weekday()

    # Vacation blocks
    cursor.execute(
        "SELECT 1 FROM technician_vacations WHERE technician_id = ? AND start_date <= ? AND end_date >= ?",
        (technician_id, start.date().isoformat(), start.date().isoformat()),
    )
    if cursor.fetchone():
        conn.close()
        return False

    # Weekday availability; fall back to legacy work_start/work_end if no row exists
    cursor.execute(
        "SELECT start_time, end_time, is_closed FROM technician_availability WHERE technician_id = ? AND weekday = ?",
        (technician_id, weekday),
    )
    avail = cursor.fetchone()
    if avail:
        if avail["is_closed"]:
            conn.close()
            return False
        try:
            start_bound = time.fromisoformat(avail["start_time"] or "10:00")
            end_bound = time.fromisoformat(avail["end_time"] or "18:00")
            if not (start_bound <= start.time() and end.time() <= end_bound):
                conn.close()
                return False
        except Exception:
            pass
    else:
        cursor.execute("SELECT work_start, work_end FROM technicians WHERE id = ?", (technician_id,))
        tech = cursor.fetchone()
        if tech:
            try:
                ws = time.fromisoformat(tech["work_start"] or "10:00")
                we = time.fromisoformat(tech["work_end"] or "18:00")
                if not (ws <= start.time() and end.time() <= we):
                    conn.close()
                    return False
            except Exception:
                pass
    conn.close()
    return not has_technician_overlap(technician_id, start, end)


def has_technician_overlap(technician_id: Optional[int], start: datetime, end: datetime) -> bool:
    if not technician_id:
        return False
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT appointment_time, service_id FROM appointments WHERE technician_id = ?", (technician_id,))
    rows = cursor.fetchall()
    conn.close()
    for row in rows:
        existing_start = datetime.fromisoformat(row["appointment_time"])
        dur = _get_service_duration(row["service_id"]) if row["service_id"] else 60
        existing_end = existing_start + timedelta(minutes=dur)
        if not (end <= existing_start or start >= existing_end):
            return True
    return False


def book_appointment(
    username: str,
    service_id: int,
    appointment_time: datetime,
    email: Optional[str],
    phone_number: Optional[str],
    notes: Optional[str] = None,
    technician_id: Optional[int] = None,
    strict_time: bool = True,
    enforce_technician_schedule: bool = True,
) -> Tuple[bool, str]:
    appt_time = appointment_time.time()
    if strict_time:
        if not (BUSINESS_START <= appt_time <= BUSINESS_END):
            return False, "Appointment must be scheduled during business hours (10:00-18:00)."

        # enforce bookings on 15-minute increments (00, 15, 30, 45)
        if appt_time.minute not in ALLOWED_MINUTES or appt_time.second != 0 or appt_time.microsecond != 0:
            return False, "Appointments must be scheduled on 15-minute increments (e.g. 10:00, 10:15, 10:30)."

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM services WHERE id = ?", (service_id,))
    if cursor.fetchone() is None:
        conn.close()
        return False, "Selected service is no longer available."

    duration = _get_service_duration(service_id)
    start = appointment_time
    end = start + timedelta(minutes=duration)

    # ensure technician is available for the full duration
    if enforce_technician_schedule:
        if not is_technician_available(technician_id, start, end):
            conn.close()
            return False, "Selected technician is not available for that duration."
    else:
        if has_technician_overlap(technician_id, start, end):
            conn.close()
            return False, "Selected technician already has a booking in that time window."

    # also ensure no other appointment with exact start exists for same technician
    cursor.execute("SELECT 1 FROM appointments WHERE appointment_time = ? AND (technician_id IS ? OR technician_id IS NULL)", (start.isoformat(), technician_id))
    if cursor.fetchone():
        conn.close()
        return False, "This exact time slot is already booked."

    cursor.execute(
        """
        INSERT INTO appointments (username, appointment_time, service_id, email, phone_number, notes, technician_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            start.isoformat(),
            service_id,
            email,
            phone_number,
            notes,
            technician_id,
        ),
    )
    conn.commit()
    conn.close()
    return True, "Appointment booked successfully."