
from flask import Flask, render_template, redirect, url_for, flash, request

import sqlite3
import random
import math

from datetime import datetime


# Flask application
app = Flask(__name__)

app.secret_key = "smart-parking-secret"


# Configuration
DATABASE = "parking.db"
PARKING_RATE = 20


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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_number TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            slot_id INTEGER NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            duration_minutes INTEGER,
            fee REAL,
            status TEXT NOT NULL DEFAULT 'Parked'
        )
    """)

    # Create six parking slots if they do not exist
    for slot_id in range(1, 7):

        conn.execute("""
            INSERT OR IGNORE INTO parking_slots (id, status)
            VALUES (?, 'Available')
        """, (slot_id,))

    conn.commit()
    conn.close()


# Current timestamp
def current_time():

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Record parking activity
def record_activity(conn, slot_id, action):

    event_time = datetime.now().strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )

    conn.execute("""
        INSERT INTO activity_history
        (slot_id, action, event_time)
        VALUES (?, ?, ?)
    """, (slot_id, action, event_time))


# Calculate parking fee
def calculate_parking_fee(entry_time, exit_datetime):

    entry_datetime = datetime.strptime(
        entry_time,
        "%Y-%m-%d %H:%M:%S"
    )

    duration_seconds = (
        exit_datetime - entry_datetime
    ).total_seconds()

    duration_minutes = max(
        1,
        math.ceil(duration_seconds / 60)
    )

    billable_hours = max(
        1,
        math.ceil(duration_seconds / 3600)
    )

    fee = billable_hours * PARKING_RATE

    return duration_minutes, fee


# Register a vehicle
@app.route("/register", methods=["POST"])
def register_vehicle():

    vehicle_number = request.form.get(
        "vehicle_number", ""
    ).strip().upper()

    vehicle_type = request.form.get(
        "vehicle_type", ""
    ).strip()

    allowed_types = ["Car", "Bike", "EV"]

    if not vehicle_number:

        flash("Please enter a vehicle registration number.")

        return redirect(url_for("home"))

    if vehicle_type not in allowed_types:

        flash("Please select a valid vehicle type.")

        return redirect(url_for("home"))

    conn = get_db_connection()

    # Prevent duplicate active vehicle registration
    existing_vehicle = conn.execute("""
        SELECT id FROM vehicles
        WHERE vehicle_number = ?
        AND status = 'Parked'
    """, (vehicle_number,)).fetchone()

    if existing_vehicle:

        flash(
            "This vehicle is already registered as parked."
        )

        conn.close()

        return redirect(url_for("home"))

    # Find an available slot
    available_slot = conn.execute("""
        SELECT id FROM parking_slots
        WHERE status = 'Available'
        ORDER BY id
        LIMIT 1
    """).fetchone()

    # Parking full validation
    if not available_slot:

        flash(
            "PARKING FULL! All parking slots are occupied. "
            "Please wait until a slot becomes available."
        )

        conn.close()

        return redirect(url_for("home"))

    slot_id = available_slot["id"]

    entry_time = current_time()

    # Register vehicle
    conn.execute("""
        INSERT INTO vehicles
        (
            vehicle_number,
            vehicle_type,
            slot_id,
            entry_time,
            status
        )
        VALUES (?, ?, ?, ?, 'Parked')
    """, (
        vehicle_number,
        vehicle_type,
        slot_id,
        entry_time
    ))

    # Mark slot occupied
    conn.execute("""
        UPDATE parking_slots
        SET status = 'Occupied'
        WHERE id = ?
    """, (slot_id,))

    # Record entry
    record_activity(
        conn,
        slot_id,
        f"Vehicle Entry - {vehicle_number} ({vehicle_type})"
    )

    conn.commit()
    conn.close()

    flash(
        f"Vehicle {vehicle_number} registered successfully. "
        f"Assigned Slot {slot_id}."
    )

    return redirect(url_for("home"))


# Vehicle exit
@app.route("/vehicle-exit/<int:vehicle_id>", methods=["POST"])
def vehicle_exit(vehicle_id):

    conn = get_db_connection()

    vehicle = conn.execute("""
        SELECT * FROM vehicles
        WHERE id = ?
        AND status = 'Parked'
    """, (vehicle_id,)).fetchone()

    if not vehicle:

        flash("Active vehicle record not found.")

        conn.close()

        return redirect(url_for("home"))

    exit_datetime = datetime.now()

    duration_minutes, fee = calculate_parking_fee(
        vehicle["entry_time"],
        exit_datetime
    )

    exit_time = exit_datetime.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    slot_id = vehicle["slot_id"]

    # Update vehicle record
    conn.execute("""
        UPDATE vehicles
        SET exit_time = ?,
            duration_minutes = ?,
            fee = ?,
            status = 'Completed'
        WHERE id = ?
    """, (
        exit_time,
        duration_minutes,
        fee,
        vehicle_id
    ))

    # Free the parking slot
    conn.execute("""
        UPDATE parking_slots
        SET status = 'Available'
        WHERE id = ?
    """, (slot_id,))

    # Record exit
    record_activity(
        conn,
        slot_id,
        f"Vehicle Exit - {vehicle['vehicle_number']} - Fee: ₹{fee}"
    )

    conn.commit()
    conn.close()

    flash(
        f"Vehicle {vehicle['vehicle_number']} exited successfully. "
        f"Duration: {duration_minutes} minutes. "
        f"Parking Fee: ₹{fee}"
    )

    return redirect(url_for("home"))


# Dashboard
@app.route("/")
def home():

    conn = get_db_connection()

    parking_slots = conn.execute("""
        SELECT * FROM parking_slots
        ORDER BY id
    """).fetchall()

    total_slots = len(parking_slots)

    available_slots = sum(
        1 for slot in parking_slots
        if slot["status"] == "Available"
    )

    occupied_slots = total_slots - available_slots

    # Active vehicles
    active_vehicles = conn.execute("""
        SELECT * FROM vehicles
        WHERE status = 'Parked'
        ORDER BY id DESC
    """).fetchall()

    # Completed vehicle history
    vehicle_history = conn.execute("""
        SELECT * FROM vehicles
        WHERE status = 'Completed'
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    # Recent parking activity
    activities = conn.execute("""
        SELECT * FROM activity_history
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    # Total revenue
    total_revenue = conn.execute("""
        SELECT COALESCE(SUM(fee), 0)
        FROM vehicles
        WHERE status = 'Completed'
    """).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        parking_slots=parking_slots,
        total_slots=total_slots,
        available_slots=available_slots,
        occupied_slots=occupied_slots,
        active_vehicles=active_vehicles,
        vehicle_history=vehicle_history,
        activities=activities,
        total_revenue=total_revenue
    )


# Manual slot toggle
@app.route("/toggle/<int:slot_id>", methods=["POST"])
def toggle_slot(slot_id):

    conn = get_db_connection()

    slot = conn.execute("""
        SELECT status FROM parking_slots
        WHERE id = ?
    """, (slot_id,)).fetchone()

    if not slot:

        flash("Parking slot not found.")

        conn.close()

        return redirect(url_for("home"))

    if slot["status"] == "Available":

        flash(
            "Please register a vehicle using the "
            "Vehicle Registration form."
        )

    else:

        active_vehicle = conn.execute("""
            SELECT id FROM vehicles
            WHERE slot_id = ?
            AND status = 'Parked'
            ORDER BY id DESC
            LIMIT 1
        """, (slot_id,)).fetchone()

        if active_vehicle:

            flash(
                "Use the Vehicle Management section "
                "to record the vehicle exit."
            )

        else:

            # Release an old occupied slot that has no vehicle record
            conn.execute("""
                UPDATE parking_slots
                SET status = 'Available'
                WHERE id = ?
            """, (slot_id,))

            record_activity(
                conn,
                slot_id,
                "Manual Slot Release"
            )

            conn.commit()

            flash(
                f"Slot {slot_id} marked as available."
            )

    conn.close()

    return redirect(url_for("home"))


# Virtual sensor simulation
@app.route("/simulate", methods=["POST"])
def simulate_sensor():

    conn = get_db_connection()

    available_slots = conn.execute("""
        SELECT id FROM parking_slots
        WHERE status = 'Available'
        ORDER BY id
    """).fetchall()

    occupied_slots = conn.execute("""
        SELECT id FROM parking_slots
        WHERE status = 'Occupied'
        ORDER BY id
    """).fetchall()

    # IMPORTANT:
    # If all slots are full, do not randomly simulate an exit.
    # Show a clear parking-full message instead.

    if not available_slots:

        flash(
            "PARKING FULL! All parking slots are occupied. "
            "A vehicle must exit before another vehicle can enter."
        )

        conn.close()

        return redirect(url_for("home"))

    # Select possible simulation actions
    possible_actions = ["Entry"]

    if occupied_slots:
        possible_actions.append("Exit")

    action_type = random.choice(possible_actions)

    # Simulate vehicle entry
    if action_type == "Entry":

        selected_slot = random.choice(available_slots)

        slot_id = selected_slot["id"]

        vehicle_number = f"SIM{random.randint(1000, 9999)}"

        vehicle_type = random.choice(
            ["Car", "Bike", "EV"]
        )

        conn.execute("""
            INSERT INTO vehicles
            (
                vehicle_number,
                vehicle_type,
                slot_id,
                entry_time,
                status
            )
            VALUES (?, ?, ?, ?, 'Parked')
        """, (
            vehicle_number,
            vehicle_type,
            slot_id,
            current_time()
        ))

        conn.execute("""
            UPDATE parking_slots
            SET status = 'Occupied'
            WHERE id = ?
        """, (slot_id,))

        record_activity(
            conn,
            slot_id,
            f"Virtual Entry - {vehicle_number}"
        )

        flash(
            f"Virtual sensor detected {vehicle_number} "
            f"entering Slot {slot_id}."
        )

    # Simulate vehicle exit
    else:

        selected_slot = random.choice(occupied_slots)

        slot_id = selected_slot["id"]

        vehicle = conn.execute("""
            SELECT * FROM vehicles
            WHERE slot_id = ?
            AND status = 'Parked'
            ORDER BY id DESC
            LIMIT 1
        """, (slot_id,)).fetchone()

        if vehicle:

            exit_datetime = datetime.now()

            duration_minutes, fee = calculate_parking_fee(
                vehicle["entry_time"],
                exit_datetime
            )

            exit_time = exit_datetime.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            conn.execute("""
                UPDATE vehicles
                SET exit_time = ?,
                    duration_minutes = ?,
                    fee = ?,
                    status = 'Completed'
                WHERE id = ?
            """, (
                exit_time,
                duration_minutes,
                fee,
                vehicle["id"]
            ))

            record_activity(
                conn,
                slot_id,
                f"Virtual Exit - {vehicle['vehicle_number']} - Fee: ₹{fee}"
            )

            flash(
                f"Virtual vehicle {vehicle['vehicle_number']} "
                f"exited Slot {slot_id}. "
                f"Parking Fee: ₹{fee}"
            )

        else:

            record_activity(
                conn,
                slot_id,
                "Virtual Sensor - Slot Released"
            )

            flash(
                f"Virtual sensor released Slot {slot_id}."
            )

        # Make the slot available
        conn.execute("""
            UPDATE parking_slots
            SET status = 'Available'
            WHERE id = ?
        """, (slot_id,))

    conn.commit()
    conn.close()

    return redirect(url_for("home"))


# Run application
if __name__ == "__main__":

    initialize_database()

    app.run(debug=True)
