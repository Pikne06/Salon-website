
# Salon Booking Website

A Flask-based appointment booking web application for a nail, hairstylist, or barber salon. It handles client-facing booking and account management, plus a full admin panel for running the business side of the salon. Ships pre-configured as a demo salon ("Auraline Salon") — the business name, contact info, colors, and fonts are all editable from the admin panel without touching code.

## Features

**For clients**
- Browse services (`/services`, `/service/<id>`), stylists/technicians (`/stylists`, `/stylist/<id>`), and a photo gallery (`/gallery`)
- Book an appointment (`/book`) with a specific technician, on 15-minute increments within business hours, with conflict checking against the technician's schedule, working hours, and vacation days
- Register, log in, log out, edit profile, and view a personal dashboard of appointments (`/register`, `/login`, `/logout`, `/profile`, `/dashboard`)
- Leave a review on a service, and message a technician directly from the dashboard
- Contact form (`/contact`) and FAQ page (`/faq`)

**For admins** (all under `/admin/...`)
- `services` — manage services: pricing, duration, description, images, aftercare info
- `technicians` — manage stylist profiles
- `availability` — set weekday schedules and vacation blocks per technician
- `appearance` — site colors, fonts, and layout toggles (services/FAQs/reviews sections on/off)
- `settings` — business name, address, hours, social links, cancellation policy
- `gallery` — manage gallery photos
- `reviews` — manage/moderate reviews
- `waitlist` — view and manage waitlist requests
- `reports` — booking reports, with CSV export (`/admin/export.csv`)

**Under the hood**
- CSRF protection on all state-changing requests (session-bound token, validated in `before_request`)
- Security headers set on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and a Content-Security-Policy
- Passwords hashed with PBKDF2 (via Werkzeug); legacy SHA-256 hashes are auto-upgraded on login
- Automatic, non-destructive SQLite schema migrations on startup (new columns get added if missing, existing data preserved)
- Optional SMTP email: a welcome email on account creation, and email delivery for technician messages, both skipped silently if not configured

## Tech stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Frontend:** HTML/CSS/JS (Jinja2 templates)

## Getting started

**1. Clone the repo**
```
git clone https://github.com/Pikne06/Salon-website.git
cd Salon-website
```

**2. Create and activate a virtual environment**
```
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS/Linux
```

**3. Install dependencies**
```
pip install -r requirements.txt
```

**4. Initialize the database**
```
python init_db.py
```
This creates `users.db` and seeds a default admin account (see note below) plus demo services, FAQs, and reviews.

**5. Run the app**
```
python app.py
```

## Configuration

All configuration is via environment variables — nothing needs to be hardcoded.

| Variable | Purpose | Required? |
|---|---|---|
| `FLASK_SECRET_KEY` | Flask session signing key | Falls back to an insecure dev default — **set this in any real deployment** |
| `FORCE_HTTPS` | Set to force the session cookie `Secure` flag | Optional |
| `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_USE_SSL` | SMTP settings for the account-creation welcome email | Optional — skipped if `MAIL_HOST` isn't set |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `FROM_EMAIL` | SMTP settings for technician messaging | Optional — skipped if not fully set |

Note: welcome emails and technician-message emails currently use two separate sets of SMTP variable names (`MAIL_*` vs `SMTP_*`) rather than one shared config — worth unifying if you extend this further.

Create a `.env` file in the project root for these (never commit it).

## Default admin account

On first run, an admin account is seeded automatically:
- Username: `admin`
- Password: `ChangeMe123!`

**Change this password immediately after your first login**, especially if the app is deployed anywhere reachable outside your own machine.

## Notes

- `users.db`, `.venv/`, `__pycache__/`, and `static/uploads/` are intentionally excluded from version control — see `.gitignore`.
- This was built as a personal/portfolio project to practice full-stack web development (auth, scheduling logic, admin tooling, CSRF/security headers) rather than as a production deployment.

## License

MIT — see [LICENSE](LICENSE).
