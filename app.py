"""
Kehlosastra - Campus Sports Coordination Platform
Flask backend with SQLite database
"""

import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, g

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "kehlosastra-secret-2024")

# ─────────────────────────────────────────────
# Database Configuration
# ─────────────────────────────────────────────

DATABASE = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    """Get a database connection, creating one if it doesn't exist in the request context."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row  # Access columns by name
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Close the database connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database schema if tables don't exist."""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS Games (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sport         TEXT NOT NULL,
            date          TEXT NOT NULL,
            time          TEXT NOT NULL,
            gender        TEXT NOT NULL,
            total_players INTEGER NOT NULL,
            location      TEXT NOT NULL,
            created_by    INTEGER NOT NULL,
            created_at    TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES Users(id)
        )
    """)
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
    db.commit()


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────

ALLOWED_EMAIL_DOMAIN = "@sastra.ac.in"


def is_valid_sastra_email(email: str) -> bool:
    """Validate that the email belongs to the SASTRA domain."""
    return email.strip().lower().endswith(ALLOWED_EMAIL_DOMAIN)


def get_or_create_user(name: str, email: str):
    """
    Fetch an existing user by email, or create a new one.
    Returns the user row, or None if the email is invalid.
    """
    email = email.strip().lower()
    if not is_valid_sastra_email(email):
        return None

    db = get_db()
    user = db.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
    if user is None:
        db.execute("INSERT INTO Users (name, email) VALUES (?, ?)", (name.strip(), email))
        db.commit()
        user = db.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
    return user


def get_game_player_count(game_id: int) -> int:
    """Return the current number of players who have joined a game."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM GamePlayers WHERE game_id = ?", (game_id,)
    ).fetchone()
    return row["cnt"] if row else 0


def enrich_games(games):
    """Attach player_count and is_full flags to each game row."""
    enriched = []
    for g_row in games:
        game = dict(g_row)
        count = get_game_player_count(game["id"])
        game["player_count"] = count
        game["is_full"] = count >= game["total_players"]
        enriched.append(game)
    return enriched


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Home page – list all games with their current player counts."""
    db = get_db()
    games = db.execute("""
        SELECT g.*, u.name AS creator_name
        FROM Games g
        JOIN Users u ON g.created_by = u.id
        ORDER BY g.date ASC, g.time ASC
    """).fetchall()
    games = enrich_games(games)

    # Pass today's date so the template can mark past games
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("index.html", games=games, today=today)


@app.route("/create", methods=["GET"])
def create():
    """Show the create-game form."""
    return render_template("create_game.html")


@app.route("/create_game", methods=["POST"])
def create_game():
    """Handle the POST request to create a new game."""
    # ── Collect form data ──────────────────────────────────────────────
    name          = request.form.get("name", "").strip()
    email         = request.form.get("email", "").strip().lower()
    sport         = request.form.get("sport", "").strip()
    date          = request.form.get("date", "").strip()
    time          = request.form.get("time", "").strip()
    gender        = request.form.get("gender", "").strip()
    total_players = request.form.get("total_players", "").strip()
    location      = request.form.get("location", "").strip()
    players_with_creator = request.form.get("players_with_creator", "0").strip()

    # ── Validation ────────────────────────────────────────────────────
    errors = []
    if not all([name, email, sport, date, time, gender, total_players, location]):
        errors.append("All fields are required.")
    if not is_valid_sastra_email(email):
        errors.append("Only @sastra.ac.in email addresses are allowed.")
    if total_players and not total_players.isdigit():
        errors.append("Total players must be a positive number.")
    if players_with_creator and not players_with_creator.isdigit():
        errors.append("Players with creator must be a non-negative number.")

    if errors:
        for err in errors:
            flash(err, "error")
        return redirect(url_for("create"))

    total_players_int        = int(total_players)
    players_with_creator_int = int(players_with_creator)

    # Ensure creator's group doesn't already exceed the limit
    if players_with_creator_int >= total_players_int:
        flash("Players already with creator cannot exceed (or equal) the total player limit.", "error")
        return redirect(url_for("create"))

    # ── Get or create the creator user ────────────────────────────────
    user = get_or_create_user(name, email)
    if user is None:
        flash("Invalid email. Only @sastra.ac.in addresses are allowed.", "error")
        return redirect(url_for("create"))

    # ── Insert the game ───────────────────────────────────────────────
    db = get_db()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.execute("""
        INSERT INTO Games (sport, date, time, gender, total_players, location, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (sport, date, time, gender, total_players_int, location, user["id"], created_at))
    db.commit()
    game_id = cursor.lastrowid

    # ── Auto-join: creator counts as 1 + players_with_creator ────────
    db.execute("INSERT OR IGNORE INTO GamePlayers (game_id, user_id) VALUES (?, ?)",
               (game_id, user["id"]))

    # Add placeholder slots for players the creator brings (anonymous slots)
    # We represent them as negative fake user IDs to keep schema valid
    for i in range(players_with_creator_int):
        # Use a synthetic user ID that won't collide: -(game_id * 1000 + i)
        fake_id = -(game_id * 1000 + i + 1)
        db.execute("INSERT OR IGNORE INTO GamePlayers (game_id, user_id) VALUES (?, ?)",
                   (game_id, fake_id))

    db.commit()

    flash("Game created successfully! 🎉", "success")
    return redirect(url_for("game_details", game_id=game_id))


@app.route("/game/<int:game_id>")
def game_details(game_id):
    """Show details for a single game including players list."""
    db = get_db()

    # Fetch the game
    game = db.execute("""
        SELECT g.*, u.name AS creator_name, u.email AS creator_email
        FROM Games g
        JOIN Users u ON g.created_by = u.id
        WHERE g.id = ?
    """, (game_id,)).fetchone()

    if game is None:
        flash("Game not found.", "error")
        return redirect(url_for("index"))

    game = dict(game)

    # Fetch real players (exclude fake/placeholder IDs)
    players = db.execute("""
        SELECT u.name, u.email
        FROM GamePlayers gp
        JOIN Users u ON gp.user_id = u.id
        WHERE gp.game_id = ? AND gp.user_id > 0
        ORDER BY gp.id ASC
    """, (game_id,)).fetchall()

    # Total slots filled (real + placeholder)
    total_joined = get_game_player_count(game_id)
    game["player_count"] = total_joined
    game["is_full"]      = total_joined >= game["total_players"]
    game["remaining"]    = max(0, game["total_players"] - total_joined)

    # Count of anonymous (placeholder) slots
    anon_count = total_joined - len(players)

    return render_template(
        "game_details.html",
        game=game,
        players=players,
        anon_count=anon_count,
    )


@app.route("/join/<int:game_id>", methods=["POST"])
def join_game(game_id):
    """Handle a student joining a game."""
    name  = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()

    # ── Validate ──────────────────────────────────────────────────────
    if not name or not email:
        flash("Please provide your name and email to join.", "error")
        return redirect(url_for("game_details", game_id=game_id))

    if not is_valid_sastra_email(email):
        flash("Only @sastra.ac.in email addresses are allowed.", "error")
        return redirect(url_for("game_details", game_id=game_id))

    # ── Check game exists ─────────────────────────────────────────────
    db = get_db()
    game = db.execute("SELECT * FROM Games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        flash("Game not found.", "error")
        return redirect(url_for("index"))

    # ── Check if game is full ─────────────────────────────────────────
    current_count = get_game_player_count(game_id)
    if current_count >= game["total_players"]:
        flash("Sorry, this game is already full!", "error")
        return redirect(url_for("game_details", game_id=game_id))

    # ── Get or create user ────────────────────────────────────────────
    user = get_or_create_user(name, email)
    if user is None:
        flash("Invalid email. Only @sastra.ac.in addresses are allowed.", "error")
        return redirect(url_for("game_details", game_id=game_id))

    # ── Insert join record (ignore if already joined) ─────────────────
    try:
        db.execute(
            "INSERT INTO GamePlayers (game_id, user_id) VALUES (?, ?)",
            (game_id, user["id"])
        )
        db.commit()
        flash(f"You've successfully joined the game! 🎉", "success")
    except sqlite3.IntegrityError:
        flash("You've already joined this game.", "info")

    return redirect(url_for("game_details", game_id=game_id))


# ─────────────────────────────────────────────
# Application Entry Point
# ─────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    # For local development only; gunicorn is used in production
    app.run(debug=True, host="0.0.0.0", port=5000)
