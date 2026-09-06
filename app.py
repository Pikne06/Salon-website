from __future__ import annotations

import os
import secrets
from datetime import datetime
from datetime import date, timedelta
from functools import wraps
from typing import Callable

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    abort,
)

from appointments import book_appointment, get_appointments
from auth import authenticate_user, change_password, delete_user, get_user, register_user, update_email
from db import init_db, seed_admin, get_conn
from services import add_service, list_services, remove_service, seed_services
from utils import hash_password


DEFAULT_SITE_SETTINGS = {
    "business_name": "Auraline Salon",
    "address": "123 Main Street, Suite 4, Your City",
    "maps_url": "https://maps.google.com",
    "phone": "(555) 123-4567",
    "email": "hello@example.com",
    "hours_text": "Mon-Fri 9:00 AM-6:00 PM · Sat 9:00 AM-2:00 PM",
    "cancellation_policy": "Please cancel or reschedule at least 24 hours in advance.",
    "parking_note": "Free street parking available nearby.",
    "accessibility_note": "Step-free entrance available.",
    "instagram_url": "https://instagram.com/",
    "facebook_url": "",
    "tiktok_url": "",
    "theme_primary": "#0EA5A4",
    "theme_secondary": "#2563EB",
    "background_color": "#F6FBFE",
    "card_background": "#FFFFFF",
    "text_color": "#042033",
    "body_font": "Manrope, sans-serif",
    "heading_font": "Fraunces, serif",
    "show_services": "1",
    "show_faqs": "1",
    "show_reviews": "1",
    "show_proof": "1",
}


def get_setting(cursor, key: str, default: str = "") -> str:
    cursor.execute("SELECT setting_value FROM site_settings WHERE setting_key = ?", (key,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return row[0]
    return default


def set_setting(cursor, key: str, value: str) -> None:
    cursor.execute(
        "INSERT INTO site_settings (setting_key, setting_value) VALUES (?, ?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
        (key, value),
    )


def load_site_settings():
    conn = get_conn()
    cursor = conn.cursor()
    settings = {key: get_setting(cursor, key, default) for key, default in DEFAULT_SITE_SETTINGS.items()}
    conn.close()
    return settings


def load_site_context():
    conn = get_conn()
    cursor = conn.cursor()
    settings = {key: get_setting(cursor, key, default) for key, default in DEFAULT_SITE_SETTINGS.items()}
    cursor.execute("SELECT id, question, answer, sort_order FROM site_faqs WHERE is_active = 1 ORDER BY sort_order, id")
    faqs = cursor.fetchall()
    cursor.execute("SELECT id, name, role, quote, sort_order FROM featured_reviews WHERE is_active = 1 ORDER BY sort_order, id")
    featured_reviews = cursor.fetchall()
    conn.close()
    return settings, faqs, featured_reviews


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
    # Session cookie hardening (opt-in secure flag when FORCE_HTTPS set)
    force_https = bool(os.environ.get("FORCE_HTTPS", ""))
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=force_https,
    )

    with app.app_context():
        init_db()
        seed_admin(hash_password)
        seed_services()
        conn = get_conn()
        cursor = conn.cursor()
        for key, value in DEFAULT_SITE_SETTINGS.items():
            cursor.execute("SELECT 1 FROM site_settings WHERE setting_key = ?", (key,))
            if cursor.fetchone() is None:
                set_setting(cursor, key, value)
        cursor.execute("SELECT COUNT(*) FROM site_faqs")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO site_faqs (question, answer, sort_order) VALUES (?, ?, ?)", ("How do I book?", "Choose a service, pick a time, and confirm.", 1))
            cursor.execute("INSERT INTO site_faqs (question, answer, sort_order) VALUES (?, ?, ?)", ("Can I reschedule?", "Yes, contact us before your appointment window.", 2))
        cursor.execute("SELECT COUNT(*) FROM featured_reviews")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO featured_reviews (name, role, quote, sort_order) VALUES (?, ?, ?, ?)", ("Studio owner", "Private client launch", "It feels like a product, not a starter kit.", 1))
            cursor.execute("INSERT INTO featured_reviews (name, role, quote, sort_order) VALUES (?, ?, ?, ?)", ("Agency builder", "White-label project", "The layout is simple enough to understand, but polished enough to pitch.", 2))
        conn.commit()
        conn.close()

    # CSRF: lightweight token stored in session and required for state-changing requests
    def generate_csrf_token() -> str:
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(16)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    def send_welcome_email(to_email: str, temp_password: str) -> bool:
        """Send a simple welcome email if SMTP settings are configured via env vars.
        Returns True if sent (or queued), False if skipped or failed."""
        host = os.environ.get("MAIL_HOST")
        if not host:
            app.logger.info("MAIL_HOST not configured; skipping welcome email")
            return False
        try:
            port = int(os.environ.get("MAIL_PORT", 587))
            username = os.environ.get("MAIL_USERNAME")
            password = os.environ.get("MAIL_PASSWORD")
            mail_from = os.environ.get("MAIL_FROM", username or "noreply@example.com")
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = "Welcome to %s" % (DEFAULT_SITE_SETTINGS["business_name"])
            msg["From"] = mail_from
            msg["To"] = to_email
            msg.set_content(
                f"Hello,\n\nAn account was created for {to_email}.\nTemporary password: {temp_password}\n\nPlease sign in and change your password.\n\nThanks,\n{DEFAULT_SITE_SETTINGS['business_name']}"
            )

            if os.environ.get("MAIL_USE_SSL", "").lower() in ("1", "true"):
                import smtplib

                with smtplib.SMTP_SSL(host, port) as s:
                    if username and password:
                        s.login(username, password)
                    s.send_message(msg)
            else:
                import smtplib

                with smtplib.SMTP(host, port) as s:
                    s.starttls()
                    if username and password:
                        s.login(username, password)
                    s.send_message(msg)
            app.logger.info("Sent welcome email to %s", to_email)
            return True
        except Exception as exc:
            app.logger.exception("Failed to send welcome email: %s", exc)
            return False

    @app.before_request
    def validate_csrf():
        if request.method in ("POST", "PUT", "DELETE"):
            token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not token or token != session.get("_csrf_token"):
                abort(400, description="CSRF token missing or invalid")

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer-when-downgrade")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        # Content Security Policy: prefer 'self' for all assets. Allow 'unsafe-inline' for styles
        # to avoid breaking templates that use inline CSS variables and small style blocks.
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self';"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response

    def login_required(view: Callable):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "username" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    @app.context_processor
    def inject_user():
        return {
            "current_user": session.get("username"),
            "is_admin": session.get("is_admin", False),
            "site_name": "Auraline",
            "site_tagline": "Beautiful booking, made simple",
            "site_settings": load_site_settings(),
        }

    @app.route("/")
    def index():
        services = list_services()
        settings, faqs, featured_reviews = load_site_context()
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.start_time, t.name as technician_name, t.id as technician_id
            FROM availability_slots s
            LEFT JOIN technicians t ON s.technician_id = t.id
            WHERE s.is_booked = 0 AND s.start_time >= ?
            ORDER BY s.start_time
            LIMIT 3
            """,
            (datetime.now().isoformat(),),
        )
        next_slots = []
        for row in cursor.fetchall():
            start = datetime.fromisoformat(row["start_time"])
            next_slots.append(
                {
                    "date": start.date().isoformat(),
                    "label": start.strftime("%A, %b %d"),
                    "time": start.strftime("%I:%M %p"),
                    "technician": row["technician_name"] or "Staff",
                    "technician_id": row["technician_id"],
                }
            )
        conn.close()
        offer_end = (datetime.now() + timedelta(days=10)).replace(microsecond=0).isoformat()
        trust_items = [
            "Licensed stylists",
            "Premium color systems",
            "5-star average rating",
            "Sanitized tools every visit",
        ]
        return render_template(
            "index.html",
            title="Auraline | Beautiful booking made simple",
            services=services,
            showcase_services=[
                {
                    "name": "Signature Cut",
                    "price": 55.0,
                    "duration": 60,
                    "image": url_for("static", filename="images/salon-station.svg"),
                },
                {
                    "name": "Color Refresh",
                    "price": 85.0,
                    "duration": 90,
                    "image": url_for("static", filename="images/shot-hero.svg"),
                },
                {
                    "name": "Style & Finish",
                    "price": 45.0,
                    "duration": 45,
                    "image": url_for("static", filename="images/shot-book.svg"),
                },
                {
                    "name": "Treatment Session",
                    "price": 70.0,
                    "duration": 60,
                    "image": url_for("static", filename="images/shot-admin.svg"),
                },
            ],
            settings=settings,
            faqs=faqs,
            featured_reviews=featured_reviews,
            homepage_reviews=[
                {
                    "quote": "The homepage feels calm, premium, and easy to navigate.",
                    "name": "Studio client",
                    "role": "Online booking",
                },
                {
                    "quote": "Everything important is visible without digging through menus.",
                    "name": "Returning guest",
                    "role": "Simple scheduling",
                },
                {
                    "quote": "It looks polished enough to launch with confidence.",
                    "name": "Independent stylist",
                    "role": "Template setup",
                },
            ],
            stats=[
                {"value": "3 screens", "label": "clients actually use"},
                {"value": "1 flow", "label": "from discovery to booking"},
                {"value": "24/7", "label": "always-on scheduling"},
                {"value": "0 clutter", "label": "clean admin and dashboard views"},
            ],
            features=[
                {
                    "title": "Client-first booking",
                    "text": "A landing page, account flow, and booking experience that looks polished enough to sell.",
                },
                {
                    "title": "Admin-ready by default",
                    "text": "Manage services without touching the database or a spreadsheet.",
                },
                {
                    "title": "Fast to brand",
                    "text": "A single design system lets you re-skin the entire app for a clinic, salon, or studio.",
                },
                {
                    "title": "Deployment-friendly",
                    "text": "Compact Flask structure, database bootstrap, and a clean assets layout for hosting.",
                },
            ],
            steps=[
                {
                    "title": "Launch the front door",
                    "text": "Use the homepage to explain the offer, prove the value, and send visitors into signup.",
                },
                {
                    "title": "Book in seconds",
                    "text": "Customers choose a service, a date, and a time without extra friction.",
                },
                {
                    "title": "Manage from one place",
                    "text": "Admin users can update the catalog and keep the booking surface current.",
                },
            ],
            testimonials=[
                {
                    "quote": "It feels like a product, not a starter kit. That matters when you are trying to sell the page.",
                    "name": "Studio owner",
                    "role": "Private client launch",
                },
                {
                    "quote": "The layout is simple enough to understand, but polished enough to pitch to a real customer.",
                    "name": "Agency builder",
                    "role": "White-label project",
                },
                {
                    "quote": "Strong enough for a demo, flexible enough to brand as your own appointment system.",
                    "name": "Freelance developer",
                    "role": "Reusable template",
                },
            ],
            audiences=[
                "Clinics",
                "Salons",
                "Consultants",
                "Studios",
            ],
            next_slots=next_slots,
            offer_end=offer_end,
            trust_items=trust_items,
        )

    @app.route("/faq")
    def faq():
        settings, faqs, featured_reviews = load_site_context()
        return render_template("faq.html", title="FAQ | Auraline", faqs=faqs, settings=settings)

    @app.route("/gallery")
    def gallery():
        import os
        images = []
        reviews = []
        rating_summary = []
        rating_total = 0
        rating_avg = None
        before_after_pairs = []
        # First, include any photos stored in the service_photos table (these may have captions)
        conn = get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT p.image_url, p.caption, p.service_id, s.name, t.name as technician_name "
                "FROM service_photos p "
                "LEFT JOIN services s ON p.service_id = s.id "
                "LEFT JOIN technicians t ON p.technician_id = t.id "
                "ORDER BY COALESCE(p.sort_order,0) DESC, p.id DESC"
            )
            raw_photos = []
            for row in cursor.fetchall():
                technician_name = row["technician_name"] if "technician_name" in row.keys() else None
                raw_photos.append({
                    "url": row[0],
                    "caption": row[1],
                    "service_name": row[3] if row[3] else None,
                    "technician_name": technician_name,
                })
                images.append(
                    {
                        "url": row[0],
                        "caption": row[1],
                        "by": technician_name,
                    }
                )
            pairs_by_service = {}
            for photo in raw_photos:
                caption = (photo.get("caption") or "").lower()
                if "before" in caption:
                    kind = "before"
                elif "after" in caption:
                    kind = "after"
                else:
                    continue
                key = photo.get("service_name") or photo.get("technician_name") or "General"
                if key not in pairs_by_service:
                    pairs_by_service[key] = {}
                if kind not in pairs_by_service[key]:
                    pairs_by_service[key][kind] = photo
            for key, pair in pairs_by_service.items():
                if "before" in pair and "after" in pair:
                    before_after_pairs.append({
                        "label": key,
                        "before_url": pair["before"]["url"],
                        "after_url": pair["after"]["url"],
                    })
        except Exception:
            # table may not exist or other error: ignore and fall back to filesystem images
            pass
        try:
            cursor.execute(
                "SELECT r.username, r.rating, r.comment, r.created_at, s.name as service_name "
                "FROM reviews r LEFT JOIN services s ON r.service_id = s.id "
                "ORDER BY r.created_at DESC LIMIT 12"
            )
            reviews = cursor.fetchall()
        except Exception:
            reviews = []
        try:
            cursor.execute("SELECT rating, COUNT(*) as cnt FROM reviews GROUP BY rating")
            counts = {row["rating"]: row["cnt"] for row in cursor.fetchall()}
            rating_total = sum(counts.values())
            if rating_total:
                rating_avg = round(sum(rating * count for rating, count in counts.items()) / rating_total, 1)
            rating_summary = [
                {"rating": rating, "count": counts.get(rating, 0)}
                for rating in range(5, 0, -1)
            ]
        except Exception:
            rating_summary = []
        conn.close()

        # Add static theme images afterwards (avoid duplicates)
        hair_images_dir = os.path.join(app.static_folder, "hairsal", "images")
        if os.path.isdir(hair_images_dir):
            for fname in sorted(os.listdir(hair_images_dir)):
                if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
                    url = url_for("static", filename=f"hairsal/images/{fname}")
                    if not any(x.get("url") == url for x in images):
                        images.append({"url": url, "caption": None, "by": None})

        uploads_dir = os.path.join(app.static_folder, "uploads", "services")
        if os.path.isdir(uploads_dir):
            for fname in sorted(os.listdir(uploads_dir)):
                if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")):
                    url = url_for("static", filename=f"uploads/services/{fname}")
                    if not any(x.get("url") == url for x in images):
                        images.append({"url": url, "caption": None, "by": None})

        return render_template(
            "gallery.html",
            title="Gallery | Auraline",
            images=images,
            reviews=reviews,
            rating_summary=rating_summary,
            rating_total=rating_total,
            rating_avg=rating_avg,
            before_after_pairs=before_after_pairs,
        )

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            success, message = register_user(username, email, password)
            if success:
                flash(message, "success")
                return redirect(url_for("login"))
            flash(message, "danger")
        return render_template("register.html", title="Create account | Auraline")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            authenticated, user = authenticate_user(username, password)
            if authenticated and user:
                session["username"] = user.username
                session["is_admin"] = user.is_admin
                flash("Welcome back!", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid username or password.", "danger")
        return render_template("login.html", title="Sign in | Auraline")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        username = session["username"]
        services = list_services()
        appointments = get_appointments(username)
        loyalty_total = 6
        loyalty_completed = min(len(appointments), loyalty_total)
        loyalty_remaining = max(loyalty_total - loyalty_completed, 0)
        return render_template(
            "dashboard.html",
            title="Dashboard | Auraline",
            services=services,
            appointments=appointments,
            service_count=len(services),
            appointment_count=len(appointments),
            loyalty_total=loyalty_total,
            loyalty_completed=loyalty_completed,
            loyalty_remaining=loyalty_remaining,
            loyalty_reward="Complimentary finishing treatment",
        )

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        username = session["username"]
        user = get_user(username)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "reorder":
                # accept an ordered list of photo ids (comma-separated)
                order_raw = request.form.get("order", "")
                if order_raw:
                    ids = [int(x) for x in order_raw.split(",") if x.isdigit()]
                    # ensure sort_order column exists
                    cursor.execute("PRAGMA table_info(service_photos)")
                    cols = {r[1] for r in cursor.fetchall()}
                    if "sort_order" not in cols:
                        try:
                            cursor.execute("ALTER TABLE service_photos ADD COLUMN sort_order INTEGER DEFAULT 0")
                        except Exception:
                            pass
                    # update sort_order according to provided order (higher first)
                    for idx, pid in enumerate(reversed(ids)):
                        try:
                            cursor.execute("UPDATE service_photos SET sort_order = ? WHERE id = ?", (idx, pid))
                        except Exception:
                            pass
                    conn.commit()
                    flash("Gallery order saved.", "success")
                else:
                    flash("No order provided.", "danger")
                cursor.execute("SELECT id, service_id, image_url, caption FROM service_photos ORDER BY COALESCE(sort_order, 0) DESC, id DESC")
                photos = cursor.fetchall()
                conn.close()
                return render_template("admin_gallery.html", title="Gallery manager | Auraline", photos=photos)
            if action == "update_password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                success, message = change_password(username, current_password, new_password)
                flash(message, "success" if success else "danger")
            elif action == "update_email":
                email = request.form.get("email", "").strip()
                success, message = update_email(username, email)
                flash(message, "success" if success else "danger")
            elif action == "delete_account":
                delete_user(username)
                session.clear()
                flash("Account deleted.", "info")
                return redirect(url_for("index"))
        return render_template(
            "profile.html",
            title="Profile | Auraline",
            user_email=user.email if user else None,
        )

    @app.route("/book", methods=["GET", "POST"])
    def book():
        services = list_services()
        # fetch technicians for selection
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM technicians WHERE is_active = 1 ORDER BY name")
        technicians = cursor.fetchall()
        conn.close()
        selected_technician_id = request.args.get("technician_id")
        selected_service_id = request.args.get("service_id")
        try:
            selected_technician_id = int(selected_technician_id) if selected_technician_id else None
        except Exception:
            selected_technician_id = None
        try:
            selected_service_id = int(selected_service_id) if selected_service_id else None
        except Exception:
            selected_service_id = None

        if session.get("username"):
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT service_id, technician_id FROM appointments WHERE username = ? ORDER BY appointment_time DESC LIMIT 1",
                (session["username"],),
            )
            last_appt = cursor.fetchone()
            conn.close()
            if last_appt:
                if not selected_service_id and last_appt["service_id"]:
                    selected_service_id = last_appt["service_id"]
                if not selected_technician_id and "technician_id" in last_appt.keys() and last_appt["technician_id"]:
                    selected_technician_id = last_appt["technician_id"]

        slot_groups = {}
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id, s.technician_id, s.start_time, s.end_time, s.is_booked, s.booked_by,
                   t.name as technician_name
            FROM availability_slots s
            LEFT JOIN technicians t ON s.technician_id = t.id
            WHERE s.is_booked = 0 AND s.start_time >= ?
            ORDER BY s.start_time
            """,
            (datetime.now().isoformat(),),
        )
        slot_rows = cursor.fetchall()
        conn.close()
        next_slot = None
        if slot_rows:
            first = slot_rows[0]
            start = datetime.fromisoformat(first["start_time"])
            next_slot = {
                "date": start.date().isoformat(),
                "time_24": start.strftime("%H:%M"),
                "time_label": start.strftime("%I:%M %p"),
                "label": start.strftime("%A, %b %d"),
                "technician": first["technician_name"] or "Staff",
                "technician_id": first["technician_id"],
            }
        for row in slot_rows:
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"]) if row["end_time"] else start + timedelta(minutes=60)
            date_key = start.date().isoformat()
            if date_key not in slot_groups:
                slot_groups[date_key] = {
                    "label": start.strftime("%A, %b %d"),
                    "short_label": start.strftime("%a"),
                    "date": date_key,
                    "slots": [],
                }
            slot_groups[date_key]["slots"].append(
                {
                    "id": row["id"],
                    "start": start.strftime("%I:%M %p"),
                    "start_24": start.strftime("%H:%M"),
                    "end": end.strftime("%I:%M %p"),
                    "technician": row["technician_name"] or "Staff",
                    "technician_id": row["technician_id"],
                }
            )
        slots_by_date = [slot_groups[k] for k in sorted(slot_groups.keys())]

        def render_booking():
            return render_template(
                "book.html",
                title="Book appointment | Auraline",
                services=services,
                technicians=technicians,
                slots_by_date=slots_by_date,
                next_slot=next_slot,
                selected_technician_id=selected_technician_id,
                selected_service_id=selected_service_id,
            )
        if not services:
            flash("No services available to book.", "warning")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            if request.form.get("action") == "waitlist":
                name = request.form.get("name", "").strip() or None
                email = request.form.get("email", "").strip() or None
                phone = request.form.get("phone", "").strip() or None
                preferred_date = request.form.get("preferred_date") or None
                preferred_time = request.form.get("preferred_time") or None
                notes = request.form.get("notes", "").strip() or None
                service_id = request.form.get("service_id") or None
                technician_id = request.form.get("technician_id") or None
                if service_id:
                    try:
                        service_id = int(service_id)
                    except Exception:
                        service_id = None
                if technician_id:
                    try:
                        technician_id = int(technician_id)
                    except Exception:
                        technician_id = None
                if not email and not phone:
                    flash("Please provide an email or phone for the waitlist.", "danger")
                    return render_booking()
                conn = get_conn()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO waitlist_requests (service_id, technician_id, name, email, phone, preferred_date, preferred_time, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (service_id, technician_id, name, email, phone, preferred_date, preferred_time, notes),
                )
                conn.commit()
                conn.close()
                flash("You're on the waitlist. We'll reach out when a slot opens.", "success")
                return redirect(url_for("book"))

            service_raw = request.form.get("service_id")
            date_str = request.form.get("date")
            time_str = request.form.get("time")
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            notes = request.form.get("notes", "").strip() or None
            create_account = bool(request.form.get("create_account"))

            # Determine username: prefer logged-in user; otherwise create a guest id
            from uuid import uuid4
            username_val = session.get("username") if session.get("username") else None

            if not service_raw or not date_str or not time_str:
                flash("Please choose a service, date, and time.", "danger")
                return render_booking()

            try:
                service_id = int(service_raw)
            except (TypeError, ValueError):
                flash("Select a valid service.", "danger")
                return render_booking()

            try:
                appointment_time = datetime.fromisoformat(f"{date_str}T{time_str}")
            except ValueError:
                flash("Invalid date or time.", "danger")
                return render_booking()

            tech_raw = request.form.get("technician_id")
            technician_id = None
            try:
                technician_id = int(tech_raw) if tech_raw else None
            except Exception:
                technician_id = None

            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT duration FROM services WHERE id = ?", (service_id,))
            row = cursor.fetchone()
            service_duration = int(row[0]) if row and row[0] else 60

            slot_id = None
            strict_time = True
            enforce_schedule = True
            if technician_id:
                cursor.execute(
                    "SELECT id, technician_id, start_time, end_time FROM availability_slots WHERE start_time = ? AND is_booked = 0 AND technician_id = ?",
                    (appointment_time.isoformat(), technician_id),
                )
            else:
                cursor.execute(
                    "SELECT id, technician_id, start_time, end_time FROM availability_slots WHERE start_time = ? AND is_booked = 0",
                    (appointment_time.isoformat(),),
                )
            slot_row = cursor.fetchone()
            if slot_row:
                slot_start = datetime.fromisoformat(slot_row["start_time"])
                slot_end = datetime.fromisoformat(slot_row["end_time"]) if slot_row["end_time"] else slot_start + timedelta(minutes=service_duration)
                if slot_end < slot_start + timedelta(minutes=service_duration):
                    conn.close()
                    flash("That slot is too short for the selected service.", "danger")
                    return render_booking()
                slot_id = slot_row["id"]
                if not technician_id:
                    technician_id = slot_row["technician_id"]
                strict_time = False
                enforce_schedule = False
            else:
                cursor.execute(
                    "SELECT 1 FROM availability_slots WHERE date(start_time) = ? AND is_booked = 0",
                    (date_str,),
                )
                if cursor.fetchone():
                    conn.close()
                    flash("That time isn't available. Choose one of the listed slots.", "danger")
                    return render_booking()

            # If there's no logged-in user and user requested account creation, try to register
            created_password = None
            if not username_val and create_account and email:
                # use email as username; generate a strong password that meets validation
                import secrets, string

                def _gen_password():
                    # ensure at least 1 upper, 1 digit, 1 special, length 10
                    specials = "!@#$%^&*()-_=+"
                    pw = [secrets.choice(string.ascii_uppercase), secrets.choice(string.digits), secrets.choice(specials)]
                    # fill remaining
                    while len(pw) < 10:
                        pw.append(secrets.choice(string.ascii_letters + string.digits + specials))
                    secrets.SystemRandom().shuffle(pw)
                    return "".join(pw)

                pwd = _gen_password()
                # attempt to register; register_user returns (success, message)
                success_reg, msg_reg = register_user(email, email, pwd)
                if success_reg:
                    created_password = pwd
                    session["username"] = email
                    username_val = email
                    flash("Account created and you are now logged in.", "info")
                    # Attempt to email the temporary password (best-effort)
                    if email:
                        sent = send_welcome_email(email, pwd)
                        if sent:
                            flash("A welcome email has been sent to your address.", "info")
                else:
                    flash("Could not create account: " + msg_reg, "warning")

            if not username_val:
                # guest username token (must be non-null for DB NOT NULL constraint)
                username_val = f"guest:{uuid4().hex}"

            success, message = book_appointment(
                username_val,
                service_id,
                appointment_time,
                email,
                phone,
                notes,
                technician_id=technician_id,
                strict_time=strict_time,
                enforce_technician_schedule=enforce_schedule,
            )
            if success and slot_id:
                cursor.execute(
                    "UPDATE availability_slots SET is_booked = 1, booked_by = ? WHERE id = ?",
                    (username_val, slot_id),
                )
                conn.commit()
            conn.close()
            flash(message, "success" if success else "danger")
            if success:
                # If we created an account, show the generated password so the user can log in
                if created_password:
                    flash(f"Your temporary password: {created_password}", "info")
                return redirect(url_for("dashboard"))
        return render_booking()

    @app.route("/admin/services", methods=["GET", "POST"])
    @login_required
    def manage_services():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                name = request.form.get("name", "").strip()
                price_raw = request.form.get("price", "0")
                duration_raw = request.form.get("duration", "60")
                image_url = request.form.get("image_url", "").strip() or None
                description = request.form.get("description", "").strip() or None
                includes_text = request.form.get("includes_text", "").strip() or None
                aftercare_text = request.form.get("aftercare_text", "").strip() or None
                image_file = request.files.get("image_file")
                try:
                    price = float(price_raw)
                    duration = int(duration_raw)
                except ValueError:
                    flash("Enter a valid price.", "danger")
                else:
                    if not name:
                        flash("Service name is required.", "danger")
                    else:
                        # prepare uploads folder and helpers
                        import os
                        from werkzeug.utils import secure_filename

                        uploads = os.path.join(app.root_path, "static", "uploads")
                        os.makedirs(uploads, exist_ok=True)

                        # handle optional upload
                        if image_file and image_file.filename:
                            filename = secure_filename(image_file.filename)
                            save_path = os.path.join(uploads, filename)
                            image_file.save(save_path)
                            image_url = url_for("static", filename=f"uploads/{filename}")

                        # If admin supplied a remote image URL, try to fetch and save it
                        if image_url and image_url.startswith(("http://", "https://")) and not (image_file and image_file.filename):
                            try:
                                import urllib.request
                                from urllib.parse import urlparse

                                parsed = urlparse(image_url)
                                remote_name = os.path.basename(parsed.path) or f"img_{secrets.token_hex(6)}.jpg"
                                remote_name = secure_filename(remote_name)
                                save_path = os.path.join(uploads, remote_name)
                                urllib.request.urlretrieve(image_url, save_path)
                                image_url = url_for("static", filename=f"uploads/{remote_name}")
                            except Exception:
                                # if fetch fails, keep the original URL (may be blocked by CSP)
                                pass

                        add_service(name, price, image_url, duration, description, includes_text, aftercare_text)
                        flash("Service added.", "success")
            elif action == "update":
                service_raw = request.form.get("service_id")
                try:
                    service_id = int(service_raw)
                except Exception:
                    service_id = None
                description = request.form.get("description", "").strip() or None
                includes_text = request.form.get("includes_text", "").strip() or None
                aftercare_text = request.form.get("aftercare_text", "").strip() or None
                if service_id:
                    conn = get_conn()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE services SET description = ?, includes_text = ?, aftercare_text = ? WHERE id = ?",
                        (description, includes_text, aftercare_text, service_id),
                    )
                    conn.commit()
                    conn.close()
                    flash("Service details updated.", "success")
                else:
                    flash("Select a valid service.", "danger")
            elif action == "add_photos":
                try:
                    service_id = int(request.form.get("service_id"))
                except Exception:
                    flash("Select a valid service.", "danger")
                    service_id = None
                tech_raw = request.form.get("technician_id")
                try:
                    technician_id = int(tech_raw) if tech_raw else None
                except Exception:
                    technician_id = None
                caption = request.form.get("caption", "").strip() or None
                photos = request.files.getlist("photos")
                if service_id and photos:
                    import os
                    from werkzeug.utils import secure_filename

                    uploads = os.path.join(app.root_path, "static", "uploads", "services")
                    os.makedirs(uploads, exist_ok=True)
                    conn = get_conn()
                    cursor = conn.cursor()
                    for photo in photos:
                        if not photo or not photo.filename:
                            continue
                        filename = secure_filename(photo.filename)
                        save_path = os.path.join(uploads, filename)
                        photo.save(save_path)
                        image_url = url_for("static", filename=f"uploads/services/{filename}")
                        cursor.execute(
                            "INSERT INTO service_photos (service_id, image_url, caption, technician_id) VALUES (?, ?, ?, ?)",
                            (service_id, image_url, caption, technician_id),
                        )
                    conn.commit()
                    conn.close()
                    flash("Service photos uploaded.", "success")
                else:
                    flash("Please select a service and at least one photo.", "danger")
            elif action == "remove":
                service_raw = request.form.get("service_id")
                try:
                    service_id = int(service_raw)
                    remove_service(service_id)
                    flash("Service removed.", "info")
                except Exception as exc:  # pragma: no cover - simple feedback
                    flash(str(exc), "danger")
        services = list_services()
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM technicians WHERE is_active = 1 ORDER BY name")
        technicians = cursor.fetchall()
        conn.close()
        return render_template(
            "admin_services.html",
            title="Service manager | Auraline",
            services=services,
            service_count=len(services),
            technicians=technicians,
        )

    @app.route("/admin/settings", methods=["GET", "POST"])
    @login_required
    def admin_settings():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_general":
                for key in DEFAULT_SITE_SETTINGS.keys():
                    if key in request.form:
                        set_setting(cursor, key, request.form.get(key, "").strip())
                conn.commit()
                flash("General settings saved.", "success")
            elif action == "add_faq":
                question = request.form.get("question", "").strip()
                answer = request.form.get("answer", "").strip()
                sort_order = int(request.form.get("sort_order") or 0)
                if question and answer:
                    cursor.execute("INSERT INTO site_faqs (question, answer, sort_order) VALUES (?, ?, ?)", (question, answer, sort_order))
                    conn.commit()
                    flash("FAQ added.", "success")
                else:
                    flash("Question and answer are required.", "danger")
            elif action == "update_faq":
                try:
                    faq_id = int(request.form.get("faq_id"))
                except (TypeError, ValueError):
                    faq_id = 0
                question = request.form.get("question", "").strip()
                answer = request.form.get("answer", "").strip()
                sort_order = int(request.form.get("sort_order") or 0)
                if faq_id and question and answer:
                    cursor.execute(
                        "UPDATE site_faqs SET question = ?, answer = ?, sort_order = ? WHERE id = ?",
                        (question, answer, sort_order, faq_id),
                    )
                    conn.commit()
                    flash("FAQ updated.", "success")
                else:
                    flash("Question and answer are required.", "danger")
            elif action == "remove_faq":
                faq_id = request.form.get("faq_id")
                cursor.execute("DELETE FROM site_faqs WHERE id = ?", (faq_id,))
                conn.commit()
                flash("FAQ removed.", "info")
            elif action == "add_review":
                name = request.form.get("name", "").strip()
                role = request.form.get("role", "").strip() or None
                quote = request.form.get("quote", "").strip()
                sort_order = int(request.form.get("sort_order") or 0)
                if name and quote:
                    cursor.execute("INSERT INTO featured_reviews (name, role, quote, sort_order) VALUES (?, ?, ?, ?)", (name, role, quote, sort_order))
                    conn.commit()
                    flash("Featured review added.", "success")
                else:
                    flash("Name and quote are required.", "danger")
            elif action == "update_review":
                try:
                    review_id = int(request.form.get("review_id"))
                except (TypeError, ValueError):
                    review_id = 0
                name = request.form.get("name", "").strip()
                role = request.form.get("role", "").strip() or None
                quote = request.form.get("quote", "").strip()
                sort_order = int(request.form.get("sort_order") or 0)
                if review_id and name and quote:
                    cursor.execute(
                        "UPDATE featured_reviews SET name = ?, role = ?, quote = ?, sort_order = ? WHERE id = ?",
                        (name, role, quote, sort_order, review_id),
                    )
                    conn.commit()
                    flash("Featured review updated.", "success")
                else:
                    flash("Name and quote are required.", "danger")
            elif action == "remove_review":
                review_id = request.form.get("review_id")
                cursor.execute("DELETE FROM featured_reviews WHERE id = ?", (review_id,))
                conn.commit()
                flash("Featured review removed.", "info")

        settings, faqs, featured_reviews = load_site_context()
        conn.close()
        return render_template(
            "admin_settings.html",
            title="Site settings | Auraline",
            settings=settings,
            faqs=faqs,
            featured_reviews=featured_reviews,
        )

    @app.route("/admin/appearance", methods=["GET", "POST"])
    @login_required
    def admin_appearance():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            if request.form.get("action") == "save_appearance":
                for key in (
                    "theme_primary",
                    "theme_secondary",
                    "background_color",
                    "card_background",
                    "text_color",
                    "body_font",
                    "heading_font",
                    "show_services",
                    "show_faqs",
                    "show_reviews",
                    "show_proof",
                ):
                    if key in request.form:
                        set_setting(cursor, key, request.form.get(key, "").strip())
                conn.commit()
                flash("Appearance settings saved.", "success")

        settings = load_site_settings()
        conn.close()
        return render_template(
            "admin_appearance.html",
            title="Appearance | Auraline",
            settings=settings,
        )

    @app.route("/admin/reports")
    @login_required
    def admin_reports():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))
        conn = get_conn()
        cursor = conn.cursor()
        # revenue
        cursor.execute("SELECT SUM(s.price) as revenue FROM appointments a JOIN services s ON a.service_id = s.id")
        rev = cursor.fetchone()[0] or 0
        # bookings per tech
        cursor.execute("SELECT t.name, COUNT(*) as cnt FROM appointments a JOIN technicians t ON a.technician_id = t.id GROUP BY t.id ORDER BY cnt DESC")
        per_tech = cursor.fetchall()
        # busiest hour
        cursor.execute("SELECT strftime('%H', appointment_time) as hour, COUNT(*) as cnt FROM appointments GROUP BY hour ORDER BY cnt DESC LIMIT 1")
        busy = cursor.fetchone()
        conn.close()
        return render_template("admin_reports.html", revenue=rev, per_tech=per_tech, busiest=busy)

    @app.route("/admin/export.csv")
    @login_required
    def admin_export_csv():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))
        import csv
        from io import StringIO

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT a.id, a.username, a.appointment_time, s.name as service, s.price, a.technician_id FROM appointments a LEFT JOIN services s ON a.service_id = s.id")
        rows = cursor.fetchall()
        conn.close()
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id","username","appointment_time","service","price","technician_id"])
        for r in rows:
            writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
        output = buf.getvalue()
        return app.response_class(output, mimetype='text/csv', headers={"Content-Disposition":"attachment; filename=export.csv"})

    @app.route("/admin/seed_demo", methods=["POST"]) 
    @login_required
    def admin_seed_demo():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))
        conn = get_conn()
        cursor = conn.cursor()
        # add sample technicians
        cursor.execute("INSERT INTO technicians (name, email, phone) VALUES (?, ?, ?)", ("Alex", "alex@example.com", ""))
        cursor.execute("INSERT INTO technicians (name, email, phone) VALUES (?, ?, ?)", ("Sam", "sam@example.com", ""))
        # add sample services if none
        cursor.execute("SELECT COUNT(*) FROM services")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO services (name, price, duration) VALUES (?, ?, ?)", ("Basic Manicure", 35.0, 45))
            cursor.execute("INSERT INTO services (name, price, duration) VALUES (?, ?, ?)", ("Gel Polish", 55.0, 60))
        conn.commit()
        conn.close()
        flash("Demo data seeded.", "success")
        return redirect(url_for("admin_reports"))

    @app.route("/admin/technicians", methods=["GET", "POST"])
    @login_required
    def manage_technicians():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                name = request.form.get("name", "").strip()
                email = request.form.get("email", "").strip() or None
                phone = request.form.get("phone", "").strip() or None
                title = request.form.get("title", "").strip() or None
                specialties = request.form.get("specialties", "").strip() or None
                bio = request.form.get("bio", "").strip() or None
                photo_url = request.form.get("photo_url", "").strip() or None
                work_start = request.form.get("work_start") or "10:00"
                work_end = request.form.get("work_end") or "18:00"
                if not name:
                    flash("Technician name is required.", "danger")
                else:
                    cursor.execute(
                        "INSERT INTO technicians (name, email, phone, title, specialties, bio, photo_url, work_start, work_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, email, phone, title, specialties, bio, photo_url, work_start, work_end),
                    )
                    conn.commit()
                    flash("Technician added.", "success")
            elif action == "update":
                try:
                    tech_id = int(request.form.get("technician_id"))
                except Exception:
                    tech_id = None
                name = request.form.get("name", "").strip()
                email = request.form.get("email", "").strip() or None
                phone = request.form.get("phone", "").strip() or None
                title = request.form.get("title", "").strip() or None
                specialties = request.form.get("specialties", "").strip() or None
                bio = request.form.get("bio", "").strip() or None
                photo_url = request.form.get("photo_url", "").strip() or None
                if tech_id and name:
                    cursor.execute(
                        "UPDATE technicians SET name = ?, email = ?, phone = ?, title = ?, specialties = ?, bio = ?, photo_url = ? WHERE id = ?",
                        (name, email, phone, title, specialties, bio, photo_url, tech_id),
                    )
                    conn.commit()
                    flash("Technician updated.", "success")
                else:
                    flash("Technician name is required.", "danger")
            elif action == "save_availability":
                try:
                    tech_id = int(request.form.get("technician_id"))
                    weekday = int(request.form.get("weekday"))
                    start_time = request.form.get("start_time") or "10:00"
                    end_time = request.form.get("end_time") or "18:00"
                    is_closed = int(request.form.get("is_closed") or 0)
                    cursor.execute(
                        "INSERT INTO technician_availability (technician_id, weekday, start_time, end_time, is_closed) VALUES (?, ?, ?, ?, ?) ON CONFLICT(technician_id, weekday) DO UPDATE SET start_time=excluded.start_time, end_time=excluded.end_time, is_closed=excluded.is_closed",
                        (tech_id, weekday, start_time, end_time, is_closed),
                    )
                    conn.commit()
                    flash("Availability saved.", "success")
                except Exception as exc:
                    flash(str(exc), "danger")
            elif action == "add_vacation":
                try:
                    tech_id = int(request.form.get("technician_id"))
                    start_date = request.form.get("start_date")
                    end_date = request.form.get("end_date")
                    reason = request.form.get("reason", "").strip() or None
                    cursor.execute(
                        "INSERT INTO technician_vacations (technician_id, start_date, end_date, reason) VALUES (?, ?, ?, ?)",
                        (tech_id, start_date, end_date, reason),
                    )
                    conn.commit()
                    flash("Vacation added.", "success")
                except Exception as exc:
                    flash(str(exc), "danger")
            elif action == "remove":
                try:
                    tech_id = int(request.form.get("technician_id"))
                    cursor.execute("DELETE FROM technicians WHERE id = ?", (tech_id,))
                    conn.commit()
                    flash("Technician removed.", "info")
                except Exception as exc:
                    flash(str(exc), "danger")

        cursor.execute("SELECT id, name, email, phone, title, specialties, bio, photo_url FROM technicians ORDER BY name")
        technicians = cursor.fetchall()
        cursor.execute(
            "SELECT v.id, t.name, v.start_date, v.end_date, v.reason FROM technician_vacations v JOIN technicians t ON v.technician_id = t.id ORDER BY v.start_date DESC"
        )
        vacations = cursor.fetchall()
        conn.close()
        return render_template("admin_technicians.html", title="Manage technicians | Auraline", technicians=technicians, vacations=vacations)

    @app.route("/admin/availability", methods=["GET", "POST"])
    @login_required
    def admin_availability():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add_slot":
                try:
                    technician_id = int(request.form.get("technician_id"))
                except Exception:
                    technician_id = None
                date_str = request.form.get("slot_date")
                time_str = request.form.get("slot_time")
                duration_raw = request.form.get("duration") or "60"
                try:
                    duration = int(duration_raw)
                except Exception:
                    duration = 60
                if not technician_id or not date_str or not time_str:
                    flash("Technician, date, and time are required.", "danger")
                else:
                    try:
                        start = datetime.fromisoformat(f"{date_str}T{time_str}")
                        end = start + timedelta(minutes=duration)
                    except ValueError:
                        flash("Invalid date or time.", "danger")
                    else:
                        cursor.execute(
                            "SELECT 1 FROM availability_slots WHERE start_time = ? AND technician_id = ?",
                            (start.isoformat(), technician_id),
                        )
                        if cursor.fetchone():
                            flash("That slot already exists for this technician.", "warning")
                        else:
                            cursor.execute(
                                "INSERT INTO availability_slots (technician_id, start_time, end_time) VALUES (?, ?, ?)",
                                (technician_id, start.isoformat(), end.isoformat()),
                            )
                            conn.commit()
                            flash("Availability slot added.", "success")
            elif action == "add_recurring":
                try:
                    technician_id = int(request.form.get("technician_id"))
                except Exception:
                    technician_id = None
                weekdays_raw = request.form.getlist("weekdays")
                if not weekdays_raw:
                    weekdays_raw = [request.form.get("weekday")]
                weekdays = []
                for val in weekdays_raw:
                    try:
                        if val is None or val == "":
                            continue
                        weekdays.append(int(val))
                    except Exception:
                        continue
                weekdays = sorted(set([w for w in weekdays if 0 <= w <= 6]))
                start_date_raw = request.form.get("start_date")
                end_date_raw = request.form.get("end_date")
                time_str = request.form.get("start_time")
                duration_raw = request.form.get("duration") or "60"
                try:
                    duration = int(duration_raw)
                except Exception:
                    duration = 60
                if not technician_id or not weekdays or not start_date_raw or not end_date_raw or not time_str:
                    flash("Technician, weekday(s), date range, and start time are required.", "danger")
                else:
                    try:
                        start_date = date.fromisoformat(start_date_raw)
                        end_date = date.fromisoformat(end_date_raw)
                    except ValueError:
                        flash("Invalid date range.", "danger")
                    else:
                        if end_date < start_date:
                            flash("End date must be on or after the start date.", "danger")
                        else:
                            created = 0
                            current = start_date
                            while current <= end_date:
                                if current.weekday() in weekdays:
                                    try:
                                        start = datetime.fromisoformat(f"{current.isoformat()}T{time_str}")
                                    except ValueError:
                                        flash("Invalid start time.", "danger")
                                        created = 0
                                        break
                                    end = start + timedelta(minutes=duration)
                                    cursor.execute(
                                        "SELECT 1 FROM availability_slots WHERE start_time = ? AND technician_id = ?",
                                        (start.isoformat(), technician_id),
                                    )
                                    if not cursor.fetchone():
                                        cursor.execute(
                                            "INSERT INTO availability_slots (technician_id, start_time, end_time) VALUES (?, ?, ?)",
                                            (technician_id, start.isoformat(), end.isoformat()),
                                        )
                                        created += 1
                                current += timedelta(days=1)
                            if created:
                                conn.commit()
                                flash(f"Added {created} recurring slots.", "success")
                            else:
                                flash("No recurring slots were added.", "warning")
            elif action == "remove_slot":
                try:
                    slot_id = int(request.form.get("slot_id"))
                except Exception:
                    slot_id = None
                if slot_id:
                    cursor.execute("DELETE FROM availability_slots WHERE id = ?", (slot_id,))
                    conn.commit()
                    flash("Slot removed.", "info")
            elif action == "mark_open":
                try:
                    slot_id = int(request.form.get("slot_id"))
                except Exception:
                    slot_id = None
                if slot_id:
                    cursor.execute(
                        "UPDATE availability_slots SET is_booked = 0, booked_by = NULL WHERE id = ?",
                        (slot_id,),
                    )
                    conn.commit()
                    flash("Slot marked as open.", "success")

        cursor.execute("SELECT id, name FROM technicians WHERE is_active = 1 ORDER BY name")
        technicians = cursor.fetchall()
        cursor.execute(
            """
            SELECT s.id, s.start_time, s.end_time, s.is_booked, s.booked_by,
                   t.name as technician_name
            FROM availability_slots s
            LEFT JOIN technicians t ON s.technician_id = t.id
            WHERE s.start_time >= ?
            ORDER BY s.start_time
            """,
            (datetime.now().isoformat(),),
        )
        slot_rows = cursor.fetchall()
        conn.close()

        slot_groups = {}
        for row in slot_rows:
            start = datetime.fromisoformat(row["start_time"])
            end = datetime.fromisoformat(row["end_time"]) if row["end_time"] else start + timedelta(minutes=60)
            date_key = start.date().isoformat()
            if date_key not in slot_groups:
                slot_groups[date_key] = {
                    "label": start.strftime("%A, %b %d"),
                    "slots": [],
                }
            slot_groups[date_key]["slots"].append(
                {
                    "id": row["id"],
                    "start": start.strftime("%I:%M %p"),
                    "end": end.strftime("%I:%M %p"),
                    "technician": row["technician_name"] or "Staff",
                    "is_booked": bool(row["is_booked"]),
                    "booked_by": row["booked_by"],
                }
            )
        slots_by_date = [slot_groups[k] for k in sorted(slot_groups.keys())]

        return render_template(
            "admin_availability.html",
            title="Availability | Auraline",
            technicians=technicians,
            slots_by_date=slots_by_date,
        )

    @app.route("/admin/gallery", methods=["GET", "POST"]) 
    @login_required
    def admin_gallery():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        # load services for scoping gallery
        from services import list_services as _list_services
        services = _list_services()
        # normalize services to (id,name)
        services = [(s[0], s[1]) for s in services]
        cursor.execute("SELECT id, name FROM technicians WHERE is_active = 1 ORDER BY name")
        technicians = cursor.fetchall()

        # service filter: 'all' | 'none' | <id>
        selected_service = request.args.get('service_id') or request.form.get('service_id') or 'all'
        if selected_service is None:
            selected_service = 'all'
        if request.method == "POST":
            action = request.form.get("action")
            if action == "upload":
                # upload gallery images (can be tied to a service)
                files = request.files.getlist("photos")
                svc_val = request.form.get('service_id') or None
                tech_raw = request.form.get('technician_id')
                try:
                    tech_val = int(tech_raw) if tech_raw else None
                except Exception:
                    tech_val = None
                # treat 'all' or 'none' as no specific service
                if svc_val in (None, 'all', 'none', 'null'):
                    svc_val = None
                else:
                    try:
                        svc_val = int(svc_val)
                    except Exception:
                        svc_val = None
                if not files:
                    flash("No files selected.", "danger")
                else:
                    import os
                    from werkzeug.utils import secure_filename

                    uploads = os.path.join(app.root_path, "static", "uploads", "gallery")
                    os.makedirs(uploads, exist_ok=True)
                    for f in files:
                        if not f or not f.filename:
                            continue
                        filename = secure_filename(f.filename)
                        save_path = os.path.join(uploads, filename)
                        f.save(save_path)
                        image_url = url_for("static", filename=f"uploads/gallery/{filename}")
                        cursor.execute(
                            "INSERT INTO service_photos (service_id, image_url, caption, technician_id) VALUES (?, ?, ?, ?)",
                            (svc_val, image_url, None, tech_val),
                        )
                    conn.commit()
                    flash("Gallery images uploaded.", "success")
            elif action == "remove_photo":
                try:
                    photo_id = int(request.form.get("photo_id"))
                except Exception:
                    photo_id = None
                if photo_id:
                    cursor.execute("SELECT image_url FROM service_photos WHERE id = ?", (photo_id,))
                    row = cursor.fetchone()
                    if row:
                        image_url = row[0]
                        # attempt to delete file from disk if under uploads
                        try:
                            import os
                            if image_url and image_url.startswith(url_for("static", filename="uploads/")):
                                rel = image_url.split('/static/')[-1]
                                path = os.path.join(app.root_path, 'static', rel)
                                if os.path.exists(path):
                                    os.remove(path)
                        except Exception:
                            pass
                    cursor.execute("DELETE FROM service_photos WHERE id = ?", (photo_id,))
                    conn.commit()
                    flash("Photo removed.", "info")
            elif action == "edit_caption":
                try:
                    photo_id = int(request.form.get("photo_id"))
                except Exception:
                    photo_id = None
                caption = request.form.get("caption", "").strip() or None
                if photo_id:
                    cursor.execute("UPDATE service_photos SET caption = ? WHERE id = ?", (caption, photo_id))
                    conn.commit()
                    flash("Caption updated.", "success")
            elif action == "update_technician":
                try:
                    photo_id = int(request.form.get("photo_id"))
                except Exception:
                    photo_id = None
                tech_raw = request.form.get("technician_id")
                try:
                    technician_id = int(tech_raw) if tech_raw else None
                except Exception:
                    technician_id = None
                if photo_id:
                    cursor.execute(
                        "UPDATE service_photos SET technician_id = ? WHERE id = ?",
                        (technician_id, photo_id),
                    )
                    conn.commit()
                    flash("Technician updated.", "success")

            elif action == "reorder":
                order_raw = request.form.get("order", "")
                svc_val = request.form.get('service_id') or 'all'
                try:
                    svc_val = int(svc_val) if svc_val and svc_val != 'none' and svc_val != 'all' else svc_val
                except Exception:
                    svc_val = 'all'
                if order_raw:
                    ids = [int(x) for x in order_raw.split(",") if x.isdigit()]
                    cursor.execute("PRAGMA table_info(service_photos)")
                    cols = {r[1] for r in cursor.fetchall()}
                    if "sort_order" not in cols:
                        try:
                            cursor.execute("ALTER TABLE service_photos ADD COLUMN sort_order INTEGER DEFAULT 0")
                        except Exception:
                            pass
                    # update sort_order for provided ids
                    for idx, pid in enumerate(reversed(ids)):
                        try:
                            cursor.execute("UPDATE service_photos SET sort_order = ? WHERE id = ?", (idx, pid))
                        except Exception:
                            pass
                    conn.commit()
                    flash("Gallery order saved.", "success")

        # determine whether sort_order column exists
        cursor.execute("PRAGMA table_info(service_photos)")
        sp_cols = {r[1] for r in cursor.fetchall()}
        has_sort = "sort_order" in sp_cols
        order_clause = "ORDER BY COALESCE(p.sort_order,0) DESC, p.id DESC" if has_sort else "ORDER BY p.id DESC"

        # load photos according to selected service filter
        if selected_service == 'all' or selected_service is None:
            cursor.execute(
                f"SELECT p.id, p.service_id, p.image_url, p.caption, p.technician_id, t.name as technician_name "
                f"FROM service_photos p LEFT JOIN technicians t ON p.technician_id = t.id {order_clause}"
            )
        elif selected_service == 'none' or selected_service == 'null':
            cursor.execute(
                f"SELECT p.id, p.service_id, p.image_url, p.caption, p.technician_id, t.name as technician_name "
                f"FROM service_photos p LEFT JOIN technicians t ON p.technician_id = t.id "
                f"WHERE p.service_id IS NULL {order_clause}"
            )
        else:
            try:
                svid = int(selected_service)
                cursor.execute(
                    f"SELECT p.id, p.service_id, p.image_url, p.caption, p.technician_id, t.name as technician_name "
                    f"FROM service_photos p LEFT JOIN technicians t ON p.technician_id = t.id "
                    f"WHERE p.service_id = ? {order_clause}",
                    (svid,),
                )
            except Exception:
                cursor.execute(
                    f"SELECT p.id, p.service_id, p.image_url, p.caption, p.technician_id, t.name as technician_name "
                    f"FROM service_photos p LEFT JOIN technicians t ON p.technician_id = t.id {order_clause}"
                )
        photos = cursor.fetchall()
        conn.close()
        return render_template(
            "admin_gallery.html",
            title="Gallery manager | Auraline",
            photos=photos,
            services=services,
            technicians=technicians,
            selected_service=selected_service,
        )

    @app.route("/admin/reviews", methods=["GET", "POST"]) 
    @login_required
    def admin_reviews():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "delete":
                try:
                    review_id = int(request.form.get("review_id"))
                except Exception:
                    review_id = None
                if review_id:
                    cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
                    conn.commit()
                    flash("Review deleted.", "info")
            elif action == "feature":
                try:
                    review_id = int(request.form.get("review_id"))
                except Exception:
                    review_id = None
                if review_id:
                    # copy into featured_reviews (name, role, quote)
                    cursor.execute("SELECT username, comment FROM reviews WHERE id = ?", (review_id,))
                    row = cursor.fetchone()
                    if row:
                        name = row[0] or "Guest"
                        quote = row[1] or ""
                        cursor.execute("INSERT INTO featured_reviews (name, role, quote, sort_order, is_active) VALUES (?, ?, ?, ?, ?)", (name, None, quote, 0, 1))
                        conn.commit()
                        flash("Review added to featured reviews.", "success")

        cursor.execute("SELECT id, service_id, username, rating, comment, created_at FROM reviews ORDER BY created_at DESC")
        reviews = cursor.fetchall()
        conn.close()
        return render_template("admin_reviews.html", title="Manage reviews | Auraline", reviews=reviews)

    @app.route("/admin/waitlist", methods=["GET", "POST"])
    @login_required
    def admin_waitlist():
        if not session.get("is_admin"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        if request.method == "POST":
            action = request.form.get("action")
            try:
                wait_id = int(request.form.get("wait_id"))
            except Exception:
                wait_id = None
            if wait_id and action in ("contacted", "booked", "closed"):
                cursor.execute(
                    "UPDATE waitlist_requests SET status = ? WHERE id = ?",
                    (action, wait_id),
                )
                conn.commit()
                flash("Waitlist status updated.", "success")
            elif wait_id and action == "remove":
                cursor.execute("DELETE FROM waitlist_requests WHERE id = ?", (wait_id,))
                conn.commit()
                flash("Waitlist entry removed.", "info")

        cursor.execute(
            """
            SELECT w.id, w.name, w.email, w.phone, w.preferred_date, w.preferred_time, w.notes, w.status,
                   s.name as service_name, t.name as technician_name
            FROM waitlist_requests w
            LEFT JOIN services s ON w.service_id = s.id
            LEFT JOIN technicians t ON w.technician_id = t.id
            ORDER BY w.created_at DESC
            """
        )
        waitlist = cursor.fetchall()
        conn.close()
        return render_template("admin_waitlist.html", title="Waitlist | Auraline", waitlist=waitlist)

    @app.route("/service/<int:service_id>", methods=["GET", "POST"])
    def service_detail(service_id: int):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, price, image_url, duration, description, includes_text, aftercare_text FROM services WHERE id = ?",
            (service_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            flash("Service not found.", "danger")
            return redirect(url_for("index"))
        service = {
            "id": row[0],
            "name": row[1],
            "price": row[2],
            "image_url": row[3],
            "duration": row[4],
            "description": row[5],
            "includes_text": row[6],
            "aftercare_text": row[7],
        }
        if request.method == "POST":
            if not session.get("username"):
                flash("Please log in to review.", "warning")
                return redirect(url_for("login"))
            action = request.form.get("action")
            if action == "add_review":
                rating = int(request.form.get("rating", "5"))
                comment = request.form.get("comment", "").strip()
                cursor.execute("INSERT INTO reviews (service_id, username, rating, comment) VALUES (?, ?, ?, ?)", (service_id, session.get("username"), rating, comment))
                conn.commit()
                flash("Review submitted.", "success")
        cursor.execute(
            "SELECT p.image_url, p.caption, t.name as technician_name "
            "FROM service_photos p LEFT JOIN technicians t ON p.technician_id = t.id "
            "WHERE p.service_id = ?",
            (service_id,),
        )
        photos = cursor.fetchall()
        cursor.execute("SELECT username, rating, comment, created_at FROM reviews WHERE service_id = ? ORDER BY created_at DESC", (service_id,))
        reviews = cursor.fetchall()
        cursor.execute(
            "SELECT id, name, title, photo_url, specialties, bio FROM technicians WHERE is_active = 1 ORDER BY name"
        )
        stylists = cursor.fetchall()
        conn.close()
        avg_rating = None
        if reviews:
            avg_rating = round(sum([r[1] or 0 for r in reviews]) / len(reviews), 1)
        return render_template(
            "service.html",
            service=service,
            photos=photos,
            reviews=reviews,
            avg_rating=avg_rating,
            review_count=len(reviews),
            stylists=stylists,
        )

    @app.route("/services")
    def services_page():
        services_list = list_services()
        # list_services returns tuples (id, name, price, image_url, duration)
        services = [
            {
                "id": s[0],
                "name": s[1],
                "price": s[2],
                "image_url": s[3],
                "duration": s[4],
                "description": s[5],
                "includes_text": s[6],
                "aftercare_text": s[7],
            }
            for s in services_list
        ]
        return render_template("services.html", title="Services | Auraline", services=services)

    @app.route("/stylists")
    def stylists_page():
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, title, photo_url, specialties, bio FROM technicians WHERE is_active = 1 ORDER BY name"
        )
        stylists = cursor.fetchall()
        conn.close()
        return render_template("stylists.html", title="Stylists | Auraline", stylists=stylists)

    @app.route("/stylist/<int:technician_id>")
    def stylist_profile(technician_id: int):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, title, photo_url, specialties, bio, email, phone FROM technicians WHERE id = ? AND is_active = 1",
            (technician_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            flash("Stylist not found.", "warning")
            return redirect(url_for("stylists_page"))
        stylist = {
            "id": row[0],
            "name": row[1],
            "title": row[2],
            "photo_url": row[3],
            "specialties": row[4],
            "bio": row[5],
            "email": row[6],
            "phone": row[7],
        }
        return render_template("stylist.html", title=f"{stylist['name']} | Auraline", stylist=stylist)

    @app.route("/about")
    def about_page():
        settings = load_site_settings()
        return render_template("about.html", title="About | Auraline", settings=settings)

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            # Basic contact form handling (no email configured)
            name = (request.form.get("first_name", "") + " " + request.form.get("last_name", "")).strip()
            flash("Thanks, {} — we received your message.".format(name or "Guest"), "success")
            return redirect(url_for("contact"))
        settings = load_site_settings()
        return render_template("contact.html", title="Contact | Auraline", site_settings=settings)

    @app.route("/message_technician", methods=["POST"])
    @login_required
    def message_technician():
        tech_raw = request.form.get("technician_id")
        message = request.form.get("message", "").strip()
        if not tech_raw or not message:
            flash("Message and technician required.", "danger")
            return redirect(url_for("dashboard"))
        try:
            tech_id = int(tech_raw)
        except Exception:
            flash("Invalid technician.", "danger")
            return redirect(url_for("dashboard"))

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT name, email, phone FROM technicians WHERE id = ?", (tech_id,))
        tech = cursor.fetchone()
        cursor.execute("INSERT INTO messages (technician_id, username, message) VALUES (?, ?, ?)", (tech_id, session.get("username"), message))
        conn.commit()
        conn.close()

        # Try to send email if configured
        tech_email = tech[1] if tech else None
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_port = int(os.environ.get("SMTP_PORT", "0") or 0)
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")
        from_addr = os.environ.get("FROM_EMAIL", "no-reply@example.com")
        sent = False
        if tech_email and smtp_host and smtp_port and smtp_user and smtp_pass:
            try:
                import smtplib
                from email.message import EmailMessage

                msg = EmailMessage()
                msg["Subject"] = f"New message from {session.get('username')}"
                msg["From"] = from_addr
                msg["To"] = tech_email
                msg.set_content(f"Message from {session.get('username')}:\n\n{message}")
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                    s.send_message(msg)
                sent = True
            except Exception:
                sent = False

        flash("Message queued" + (" and emailed." if sent else "."), "success")
        return redirect(url_for("dashboard"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)