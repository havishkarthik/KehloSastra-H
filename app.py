"""
Kehlosastra - Campus Sports Coordination Platform
Full-featured Flask app with auth, game management, and smart time logic.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, g, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "kehlosastra-secret-2024-upgrade")

# ─────────────────────────────────────────────────────────
# Database Setup
# ─────────────────────────────────────────────────────────

DATABASE = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    """Create tables if they don't exist; migrate existing tables."""
    db = get_db()

    # Users — with password_hash for auth
    db.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL DEFAULT ''
        )
    """)

    # Games — now with start_time AND end_time
    db.execute("""
        CREATE TABLE IF NOT EXISTS Games (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sport           TEXT NOT NULL,
            date            TEXT NOT NULL,
            start_time      TEXT NOT NULL,
            end_time        TEXT NOT NULL,
            gender          TEXT NOT NULL,
            total_players   INTEGER NOT NULL,
            location        TEXT NOT NULL,
            created_by      INTEGER NOT NULL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES Users(id)
        )
    """)

    # GamePlayers
    db.execute("""
        CREATE TABLE IF NOT EXISTS GamePlayers (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(game_id, user_id),
            FOREIGN KEY (game_id) REFERENCES Games(id),
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    """)

    # Bookings table for court booking
    db.execute("""
        CREATE TABLE IF NOT EXISTS Bookings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL,
            sport       TEXT NOT NULL,
            date        TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)

    db.commit()

    # ── Migrations: add columns that may not exist in old DB ────────────
    _add_column_if_missing(db, "Games", "end_time", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(db, "Users", "password_hash", "TEXT NOT NULL DEFAULT ''")


def _add_column_if_missing(db, table, column, definition):
    """Add a column to a table if it doesn't already exist."""
    cols = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        db.commit()


# ─────────────────────────────────────────────────────────
# Auth Helpers
# ─────────────────────────────────────────────────────────

ALLOWED_DOMAIN = "@sastra.ac.in"


def is_sastra_email(email: str) -> bool:
    return email.strip().lower().endswith(ALLOWED_DOMAIN)


def login_required(f):
    """Decorator: redirect to login if user is not in session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def current_user():
    """Return the logged-in user row, or None."""
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM Users WHERE id = ?", (uid,)).fetchone()


# ─────────────────────────────────────────────────────────
# Time / Game Helpers
# ─────────────────────────────────────────────────────────

def now_dt():
    return datetime.now()


def parse_game_dt(game, key="start_time"):
    """Parse game date + time into a datetime. Returns None on error."""
    try:
        return datetime.strptime(f"{game['date']} {game[key]}", "%Y-%m-%d %H:%M")
    except Exception:
        return None


def enrich_game(game):
    """Attach computed fields: player_count, is_full, remaining,
    is_expired, starting_soon."""
    g_dict = dict(game)
    db = get_db()

    count = db.execute(
        "SELECT COUNT(*) as c FROM GamePlayers WHERE game_id = ? AND user_id > 0",
        (g_dict["id"],)
    ).fetchone()["c"]
    g_dict["player_count"] = count
    g_dict["is_full"] = count >= g_dict["total_players"]
    g_dict["remaining"] = max(0, g_dict["total_players"] - count)

    now = now_dt()
    end_dt = parse_game_dt(g_dict, "end_time") or parse_game_dt(g_dict, "start_time")
    start_dt = parse_game_dt(g_dict, "start_time")

    g_dict["is_expired"] = bool(end_dt and end_dt < now)
    g_dict["starting_soon"] = bool(
        start_dt and not g_dict["is_expired"]
        and timedelta(0) <= (start_dt - now) <= timedelta(minutes=30)
    )
    return g_dict


def enrich_games(games):
    return [enrich_game(g) for g in games]


def get_player_count(game_id: int) -> int:
    row = get_db().execute(
        "SELECT COUNT(*) as c FROM GamePlayers WHERE game_id = ? AND user_id > 0",
        (game_id,)
    ).fetchone()
    return row["c"] if row else 0


# ─────────────────────────────────────────────────────────
# Context processor — inject user into all templates
# ─────────────────────────────────────────────────────────

@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ─────────────────────────────────────────────────────────
# Routes: Auth
# ─────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        name  = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pwd   = request.form.get("password", "")
        pwd2  = request.form.get("password2", "")

        # Validation
        if not all([name, email, pwd, pwd2]):
            flash("All fields are required.", "error")
            return redirect(url_for("register"))
        if not is_sastra_email(email):
            flash("Only @sastra.ac.in email addresses are allowed.", "error")
            return redirect(url_for("register"))
        if pwd != pwd2:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))
        if len(pwd) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        db = get_db()
        existing = db.execute("SELECT id FROM Users WHERE email = ?", (email,)).fetchone()
        if existing:
            flash("An account with this email already exists. Please log in.", "error")
            return redirect(url_for("login"))

        pw_hash = generate_password_hash(pwd)
        db.execute(
            "INSERT INTO Users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, pw_hash)
        )
        db.commit()
        user = db.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        flash(f"Welcome to Kehlosastra, {name}! 🎉", "success")
        return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pwd   = request.form.get("password", "")

        if not email or not pwd:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("login"))

        db = get_db()
        user = db.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()

        if not user or not check_password_hash(user["password_hash"], pwd):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "info")
    return redirect(url_for("landing"))


# ─────────────────────────────────────────────────────────
# Routes: Landing + Games
# ─────────────────────────────────────────────────────────

@app.route("/")
def landing():
    """Marketing landing page."""
    db = get_db()
    total_games = db.execute("SELECT COUNT(*) as c FROM Games").fetchone()["c"]
    games_raw   = db.execute("SELECT id, total_players, date, end_time, start_time FROM Games").fetchall()
    now = now_dt()
    open_games = 0
    for gr in games_raw:
        end_dt = parse_game_dt(gr, "end_time") or parse_game_dt(gr, "start_time")
        if end_dt and end_dt >= now and get_player_count(gr["id"]) < gr["total_players"]:
            open_games += 1
    return render_template("landing.html", total_games=total_games, open_games=open_games)


@app.route("/matches")
def index():
    """Matches listing — only active (non-expired) games."""
    db = get_db()
    games = db.execute("""
        SELECT g.*, u.name AS creator_name
        FROM Games g
        JOIN Users u ON g.created_by = u.id
        ORDER BY g.date ASC, g.start_time ASC
    """).fetchall()

    now = now_dt()
    enriched = [enrich_game(g) for g in games]
    # Filter out expired games on the listing page
    active = [g for g in enriched if not g["is_expired"]]

    today = now.strftime("%Y-%m-%d")
    return render_template("index.html", games=active, today=today, now=now)


@app.route("/create", methods=["GET"])
@login_required
def create():
    return render_template("create_game.html")


@app.route("/create_game", methods=["POST"])
@login_required
def create_game():
    uid   = session["user_id"]
    sport = request.form.get("sport", "").strip()
    date  = request.form.get("date", "").strip()
    start = request.form.get("start_time", "").strip()
    end   = request.form.get("end_time", "").strip()
    gender = request.form.get("gender", "").strip()
    total  = request.form.get("total_players", "").strip()
    loc    = request.form.get("location", "").strip()
    with_creator = request.form.get("players_with_creator", "0").strip()

    if not all([sport, date, start, end, gender, total, loc]):
        flash("All fields are required.", "error")
        return redirect(url_for("create"))

    if not total.isdigit() or int(total) < 2:
        flash("Total players must be at least 2.", "error")
        return redirect(url_for("create"))

    with_creator_int = int(with_creator) if with_creator.isdigit() else 0
    total_int = int(total)

    if with_creator_int >= total_int:
        flash("Players with you cannot exceed or equal the total limit.", "error")
        return redirect(url_for("create"))

    # Validate end_time > start_time
    try:
        start_dt = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
        end_dt   = datetime.strptime(f"{date} {end}",   "%Y-%m-%d %H:%M")
        if end_dt <= start_dt:
            flash("End time must be after start time.", "error")
            return redirect(url_for("create"))
    except ValueError:
        flash("Invalid date or time format.", "error")
        return redirect(url_for("create"))

    db = get_db()
    created_at = now_dt().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.execute(
        """INSERT INTO Games
           (sport, date, start_time, end_time, gender, total_players, location, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (sport, date, start, end, gender, total_int, loc, uid, created_at)
    )
    db.commit()
    game_id = cursor.lastrowid

    # Auto-join creator
    db.execute("INSERT OR IGNORE INTO GamePlayers (game_id, user_id) VALUES (?, ?)",
               (game_id, uid))

    # Placeholder slots for people already with creator
    for i in range(with_creator_int):
        fake_id = -(game_id * 1000 + i + 1)
        db.execute("INSERT OR IGNORE INTO GamePlayers (game_id, user_id) VALUES (?, ?)",
                   (game_id, fake_id))
    db.commit()

    flash("Match created! 🎉", "success")
    return redirect(url_for("game_details", game_id=game_id))


@app.route("/game/<int:game_id>")
def game_details(game_id):
    db = get_db()
    game = db.execute("""
        SELECT g.*, u.name AS creator_name, u.email AS creator_email
        FROM Games g JOIN Users u ON g.created_by = u.id
        WHERE g.id = ?
    """, (game_id,)).fetchone()

    if not game:
        flash("Game not found.", "error")
        return redirect(url_for("index"))

    game = enrich_game(game)

    players = db.execute("""
        SELECT u.name, u.email FROM GamePlayers gp
        JOIN Users u ON gp.user_id = u.id
        WHERE gp.game_id = ? AND gp.user_id > 0
        ORDER BY gp.id ASC
    """, (game_id,)).fetchall()

    anon_count = game["player_count"] - len(players)
    return render_template("game_details.html",
                           game=game, players=players, anon_count=anon_count)


@app.route("/join/<int:game_id>", methods=["POST"])
@login_required
def join_game(game_id):
    uid = session["user_id"]
    db  = get_db()

    game = db.execute("SELECT * FROM Games WHERE id = ?", (game_id,)).fetchone()
    if not game:
        flash("Game not found.", "error")
        return redirect(url_for("index"))

    game = enrich_game(game)

    if game["is_expired"]:
        flash("This game has already ended.", "error")
        return redirect(url_for("game_details", game_id=game_id))

    if game["is_full"]:
        flash("Sorry, this game is already full.", "error")
        return redirect(url_for("game_details", game_id=game_id))

    try:
        db.execute("INSERT INTO GamePlayers (game_id, user_id) VALUES (?, ?)", (game_id, uid))
        db.commit()
        flash("You've joined the match! 🏃", "success")
    except sqlite3.IntegrityError:
        flash("You're already in this match.", "info")

    return redirect(url_for("game_details", game_id=game_id))


# ─────────────────────────────────────────────────────────
# Routes: Court Booking
# ─────────────────────────────────────────────────────────

BOOKABLE_SPORTS = [
    "Badminton", "Football", "Cricket", "Basketball",
    "Volleyball", "Tennis", "Table Tennis",
]

BOOKING_SLOTS = [
    "06:00","06:30","07:00","07:30","08:00","08:30","09:00","09:30",
    "10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30",
    "14:00","14:30","15:00","15:30","16:00","16:30","17:00","17:30",
    "18:00","18:30","19:00","19:30","20:00","20:30","21:00","21:30","22:00",
]


def check_overlap(sport, date, start, end, exclude_id=None):
    """Return True if the requested slot overlaps an existing booking."""
    db = get_db()
    query = """
        SELECT id FROM Bookings
        WHERE sport = ? AND date = ?
          AND start_time < ? AND end_time > ?
    """
    params = [sport, date, end, start]
    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)
    return db.execute(query, params).fetchone() is not None


@app.route("/booking")
def booking_page():
    """Render the court booking form."""
    return render_template(
        "booking.html",
        sports=BOOKABLE_SPORTS,
        slots=BOOKING_SLOTS,
    )


@app.route("/book", methods=["POST"])
def book():
    """Create a booking with anti-overlap logic."""
    # Accept both form and JSON
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    name  = (data.get("name")  or "").strip()
    email = (data.get("email") or "").strip().lower()
    sport = (data.get("sport") or "").strip()
    date  = (data.get("date")  or "").strip()
    start = (data.get("start_time") or "").strip()
    end   = (data.get("end_time")   or "").strip()

    errors = []

    # Required fields
    if not all([name, email, sport, date, start, end]):
        errors.append("All fields are required.")

    # SASTRA email
    if email and not is_sastra_email(email):
        errors.append("Only @sastra.ac.in emails are allowed.")

    # Time validation
    if start and end:
        if end <= start:
            errors.append("End time must be after start time.")

    # Past booking check
    if date and start:
        try:
            booking_dt = datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M")
            if booking_dt < now_dt():
                errors.append("Cannot book a slot in the past.")
        except ValueError:
            errors.append("Invalid date or time format.")

    if errors:
        if request.is_json:
            return jsonify({"success": False, "errors": errors}), 400
        for e in errors:
            flash(e, "error")
        return redirect(url_for("booking_page"))

    # Anti-overlap check
    if check_overlap(sport, date, start, end):
        msg = f"This {sport} slot on {date} from {start} to {end} is already booked."
        if request.is_json:
            return jsonify({"success": False, "errors": [msg]}), 409
        flash(msg, "error")
        return redirect(url_for("booking_page"))

    # Insert
    db = get_db()
    created_at = now_dt().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """INSERT INTO Bookings (name, email, sport, date, start_time, end_time, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, email, sport, date, start, end, created_at)
    )
    db.commit()

    if request.is_json:
        return jsonify({"success": True, "message": "Court booked successfully!"}), 201

    flash(f"{sport} court booked for {date} from {start} to {end}! 🎉", "success")
    return redirect(url_for("booking_page"))


@app.route("/bookings")
def list_bookings():
    """Return all bookings — HTML or JSON."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM Bookings ORDER BY date ASC, start_time ASC"
    ).fetchall()
    bookings = [dict(r) for r in rows]

    if request.args.get("format") == "json" or request.is_json:
        return jsonify(bookings)
    return render_template("booking.html",
                           sports=BOOKABLE_SPORTS,
                           slots=BOOKING_SLOTS,
                           bookings=bookings,
                           show_bookings=True)


@app.route("/availability")
def availability():
    """Return available slots for a sport on a given date."""
    sport = request.args.get("sport", "").strip()
    date  = request.args.get("date", "").strip()

    if not sport or not date:
        return jsonify({"error": "sport and date parameters are required."}), 400

    db = get_db()
    booked = db.execute(
        "SELECT start_time, end_time FROM Bookings WHERE sport = ? AND date = ? ORDER BY start_time ASC",
        (sport, date)
    ).fetchall()

    booked_list = [{"start": r["start_time"], "end": r["end_time"]} for r in booked]

    # Build free slots from BOOKING_SLOTS by checking 30-min windows
    free_slots = []
    for i in range(len(BOOKING_SLOTS) - 1):
        s = BOOKING_SLOTS[i]
        e = BOOKING_SLOTS[i + 1]
        if not check_overlap(sport, date, s, e):
            free_slots.append({"start": s, "end": e})

    return jsonify({
        "sport": sport,
        "date": date,
        "booked": booked_list,
        "available": free_slots,
    })


@app.route("/admin/bookings")
def admin_bookings():
    """Admin endpoint — JSON list of all bookings."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM Bookings ORDER BY date DESC, start_time DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ─────────────────────────────────────────────────────────
# Boot
# ─────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
