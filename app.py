
from flask import Flask, render_template, redirect, url_for, flash
import sqlite3
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = "smart-parking-secret"

DATABASE = "parking.db"


# Database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Initialize database
def initialize_database():

    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS parking_slots (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            event_time TEXT NOT NULL
        )
    """)

    for slot_id in range(1, 7):

        conn.execute("""
            INSERT OR IGNORE INTO parking_slots (id, status)
            VALUES (?, 'Available')
        """, (slot_id,))

    conn.commit()
    conn.close()


# Record activity
def record_activity(conn, slot_id, action):

    event_time = datetime.now().strftime("%d-%m-%Y %I:%M:%S %p")

    conn.execute("""
        INSERT INTO activity_history
        (slot_id, action, event_time)
        VALUES (?, ?, ?)
    """, (slot_id, action, event_time))


# Dashboard
@app.route("/")
def home():

    conn = get_db_connection()

    parking_slots = conn.execute(
        "SELECT * FROM parking_slots ORDER BY id"
    ).fetchall()

    total_slots = len(parking_slots)

    available_slots = sum(
        1 for slot in parking_slots
        if slot["status"] == "Available"
    )

    occupied_slots = total_slots - available_slots

    activities = conn.execute("""
        SELECT * FROM activity_history
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        parking_slots=parking_slots,
        total_slots=total_slots,
        available_slots=available_slots,
        occupied_slots=occupied_slots,
        activities=activities
    )


# Manual vehicle entry and exit
@app.route("/toggle/<int:slot_id>", methods=["POST"])
def toggle_slot(slot_id):

    conn = get_db_connection()

    slot = conn.execute(
        "SELECT status FROM parking_slots WHERE id = ?",
        (slot_id,)
    ).fetchone()

    if slot:

        if slot["status"] == "Available":

            new_status = "Occupied"
            action = "Vehicle Entry"

        else:

            new_status = "Available"
            action = "Vehicle Exit"

        conn.execute(
            "UPDATE parking_slots SET status = ? WHERE id = ?",
            (new_status, slot_id)
        )

        record_activity(conn, slot_id, action)

        conn.commit()

    conn.close()

    return redirect(url_for("home"))


# Virtual sensor simulation
@app.route("/simulate", methods=["POST"])
def simulate_sensor():

    conn = get_db_connection()

    slots = conn.execute(
        "SELECT * FROM parking_slots"
    ).fetchall()

    if slots:

        selected_slot = random.choice(slots)

        slot_id = selected_slot["id"]

        if selected_slot["status"] == "Available":

            new_status = "Occupied"
            action = "Vehicle Entry"

        else:

            new_status = "Available"
            action = "Vehicle Exit"

        conn.execute(
            "UPDATE parking_slots SET status = ? WHERE id = ?",
            (new_status, slot_id)
        )

        record_activity(conn, slot_id, action)

        conn.commit()

        flash(
            f"Virtual sensor: {action} detected at Slot {slot_id}."
        )

    conn.close()

    return redirect(url_for("home"))


if __name__ == "__main__":

    initialize_database()

    app.run(debug=True)
