import mysql.connector
from datetime import date, datetime, timedelta, time
from mysql.connector import Error
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import io
import base64
from matplotlib import ticker


# DB_CONFIG = {
#     "host": "sofige22.mysql.pythonanywhere-services.com",
#     "user": "sofige22",
#     "password": "root123456",
#     "database": "sofige22$FLYTAU"
# }

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "FLYTAU"
}

def get_conn():
    """Establishes and returns a connection to the MySQL database."""
    return mysql.connector.connect(**DB_CONFIG)

# ==========================================
# 1. AUTHENTICATION & USER MANAGEMENT
# ==========================================
def check_registered_login(email: str, password: str) -> bool:
    """Verifies login credentials for a registered customer."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM RegisteredCustomers WHERE RegEmail=%s AND R_Password=%s", (email, password))
    ok = cur.fetchone() is not None
    cur.close()
    conn.close()
    return ok

def verify_registered_customer(email, password):
    """Verifies registered customer and returns their details object."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM RegisteredCustomers WHERE RegEmail = %s AND R_Password = %s", (email, password))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def check_manager_login(manager_id: str, password: str) -> bool:
    """Verifies login credentials for a manager."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM Managers WHERE ManagerID=%s AND M_Password=%s", (manager_id, password))
    ok = cur.fetchone() is not None
    cur.close()
    conn.close()
    return ok

def register_registered_customer(email, password, first_name, last_name, passport_number, birth_date, phones):
    """
    Registers a new customer and saves their associated phone numbers in a separate table.
    Ensures data is split between RegisteredCustomers and RegisteredPhones as per DB schema.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Check if email exists
        cur.execute("SELECT 1 FROM RegisteredCustomers WHERE RegEmail = %s", (email,))
        if cur.fetchone():
            return False, "This email address is already registered. Please log in or use a different email."
        cur.fetchall()  # Clear buffer

        # 1. Insert basic profile
        cur.execute(
            """INSERT INTO RegisteredCustomers 
               (RegEmail, FirstName, LastName, RegistrationDate, PassportNumber, R_Password, BirthDate) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (email, first_name, last_name, date.today(), passport_number, password, birth_date)
        )

        # 2. Insert multiple phone numbers
        if phones:
            for phone in phones:
                cur.execute(
                    "INSERT INTO RegisteredPhones (RegEmail, PhoneNumber) VALUES (%s, %s)",
                    (email, phone.strip())
                )

        conn.commit()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, "System Error: " + str(e)
    finally:
        cur.close()
        conn.close()

def get_registered_customer_profile(email: str):
    """
    Retrieves personal details and joins phone numbers from the RegisteredPhones table.
    Returns a dictionary formatted for the user profile page.
    """
    if not email:
        return None
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # Fetch basic info
        cur.execute("""
            SELECT RegEmail, FirstName, LastName
            FROM RegisteredCustomers
            WHERE RegEmail=%s
            LIMIT 1
        """, (email,))
        c = cur.fetchone()
        if not c:
            return None

        # Fetch associated phones from the phones table
        cur.execute("""
            SELECT PhoneNumber
            FROM RegisteredPhones
            WHERE RegEmail=%s
            ORDER BY PhoneNumber
        """, (email,))
        phones = [r["PhoneNumber"] for r in (cur.fetchall() or [])]

        return {
            "Email": c["RegEmail"],
            "FirstName": c["FirstName"],
            "LastName": c["LastName"],
            "Phones": phones
        }
    finally:
        cur.close()
        conn.close()


def register_guest_if_not_exists(email, first_name, last_name, phone):
    """
    Validates the guest's identity. If existing guest provides a new phone number, adds it. If new guest, creates records.
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # 1. Check if the email belongs to a registered member
        cur.execute("SELECT RegEmail, FirstName, LastName FROM RegisteredCustomers WHERE RegEmail = %s", (email,))
        reg_user = cur.fetchone()
        cur.fetchall()  # Clear buffer

        if reg_user:
            # Validation: Enforce strict name matching
            db_first = reg_user['FirstName'].strip().lower()
            db_last = reg_user['LastName'].strip().lower()
            in_first = first_name.strip().lower()
            in_last = last_name.strip().lower()

            if db_first != in_first or db_last != in_last:
                return "details_mismatch", "This email is registered to a member with a different name."

            return "success", "Member proceeding as guest."

        # 2. Check if the email belongs to an existing guest
        cur.execute("SELECT GuestEmail, FirstName, LastName FROM GuestCustomers WHERE GuestEmail = %s", (email,))
        guest_user = cur.fetchone()
        cur.fetchall()  # Clear buffer

        if guest_user:
            # Validation: Ensure the provided name matches the existing guest record
            db_first = guest_user['FirstName'].strip().lower()
            db_last = guest_user['LastName'].strip().lower()
            in_first = first_name.strip().lower()
            in_last = last_name.strip().lower()

            if db_first != in_first or db_last != in_last:
                return "details_mismatch", "This email was previously used with a different name."

            # --- UPDATE: Logic to handle additional phone numbers for returning guests ---
            if phone:
                # Check if this specific phone number is already linked to the guest
                cur.execute("SELECT 1 FROM GuestPhones WHERE GuestEmail = %s AND PhoneNumber = %s", (email, phone))
                phone_exists = cur.fetchone()
                cur.fetchall()  # Clear buffer

                if not phone_exists:
                    # Register the new phone number for the existing guest
                    cur.execute("INSERT INTO GuestPhones (GuestEmail, PhoneNumber) VALUES (%s, %s)", (email, phone))
                    conn.commit()
            # -----------------------------------------------------------------------------

            return "success", "Existing guest found."

        # 3. New Guest Registration: Split into two queries

        # A. Insert basic info
        cur.execute("""
            INSERT INTO GuestCustomers (GuestEmail, FirstName, LastName)
            VALUES (%s, %s, %s)
        """, (email, first_name, last_name))

        # B. Insert phone number
        if phone:
            cur.execute("""
                INSERT INTO GuestPhones (GuestEmail, PhoneNumber)
                VALUES (%s, %s)
            """, (email, phone))

        conn.commit()
        return "success", "New guest registered."

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"DB Error in register_guest: {e}")
        return "error", str(e)
    finally:
        cur.close()
        conn.close()


def validate_guest_identity(email, first_name, last_name):
    """
    Checks if the email is already taken by a different name (Registered or Guest).
    Does NOT save anything to the database.
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # 1. Check Registered Users
        cur.execute("SELECT FirstName, LastName FROM RegisteredCustomers WHERE RegEmail = %s", (email,))
        reg_user = cur.fetchone()
        cur.fetchall()

        if reg_user:
            db_first = reg_user['FirstName'].strip().lower()
            db_last = reg_user['LastName'].strip().lower()
            if db_first != first_name.strip().lower() or db_last != last_name.strip().lower():
                return False, "Email belongs to a registered member with a different name."
            return True, "OK"

        # 2. Check Existing Guests
        cur.execute("SELECT FirstName, LastName FROM GuestCustomers WHERE GuestEmail = %s", (email,))
        guest_user = cur.fetchone()
        cur.fetchall()

        if guest_user:
            db_first = guest_user['FirstName'].strip().lower()
            db_last = guest_user['LastName'].strip().lower()
            if db_first != first_name.strip().lower() or db_last != last_name.strip().lower():
                return False, "Email belongs to a guest with a different name."
            return True, "OK"

        # 3. Email is new - totally fine
        return True, "OK"

    finally:
        cur.close()
        conn.close()

# ==========================================
# 2. FLIGHT BROWSING & INFO
# ==========================================

def get_flights_filtered(flight_id=None, status=None, date_from=None, date_to=None,
                         plane_id=None, source=None, destination=None, arrival_date=None):
    """Fetches a list of flights filtered by various criteria, joining with Route and Plane details."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    q = """
        SELECT f.*, p.PlaneSize, p.Manufacturer, r.SourceAirport, r.DestinationAirport 
        FROM Flights f 
        JOIN Plane p ON f.PlaneID = p.PlaneID 
        JOIN Routes r ON f.RouteID = r.RouteID 
        WHERE 1=1
    """
    params = []

    if flight_id:
        q += " AND f.FlightID LIKE %s"
        params.append(f"%{flight_id}%")

    if status:
        q += " AND f.FlightStatus = %s"
        params.append(status)

    if date_from:
        q += " AND f.DepartureDate >= %s"
        params.append(date_from)

    if date_to:
        q += " AND f.DepartureDate <= %s"
        params.append(date_to)

    if plane_id:
        q += " AND f.PlaneID = %s"
        params.append(plane_id)

    if source:
        q += " AND r.SourceAirport LIKE %s"
        params.append(f"%{source}%")

    if destination:
        q += " AND r.DestinationAirport LIKE %s"
        params.append(f"%{destination}%")

    if arrival_date:
        q += " AND f.ArrivalDate = %s"
        params.append(arrival_date)

    q += " ORDER BY f.DepartureDate DESC, f.DepartureTime DESC"

    cur.execute(q, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_flight_info_for_summary(flight_id):
    """Retrieves specific flight details including source and destination airports."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT f.*, r.SourceAirport, r.DestinationAirport 
            FROM Flights f 
            JOIN Routes r ON f.RouteID = r.RouteID 
            WHERE f.FlightID = %s
        """, (flight_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def get_flight_seatmap(flight_id):
    """Fetches the seating configuration and pricing for a specific flight, calculating row offsets."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # Step 1: Find the PlaneID associated with the given FlightID
        cur.execute("SELECT PlaneID FROM Flights WHERE FlightID=%s", (flight_id,))
        plane = cur.fetchone()
        if not plane:
            return None

        # Step 2: Fetch cabin class configurations.
        # Ordered by Business first to maintain standard aviation seating logic.
        cur.execute("""
            SELECT c.ClassType, c.NumRows, c.NumCols, fc.TicketPrice
            FROM Class c
            JOIN FlightClasses fc ON c.PlaneID = fc.PlaneID AND c.ClassType = fc.ClassType
            WHERE fc.FlightID = %s AND c.PlaneID = %s
            ORDER BY CASE WHEN c.ClassType = 'Business' THEN 1 ELSE 2 END
        """, (flight_id, plane['PlaneID']))

        classes = cur.fetchall()

        # Step 3: Calculate the RowOffset for each class.
        # This prevents duplicate row numbers (e.g., 'Row 1' in both Business and Economy)
        # and ensures that Economy rows start immediately after Business rows.
        current_offset = 0
        for cls in classes:
            cls['RowOffset'] = current_offset
            current_offset += cls['NumRows']

        return classes
    finally:
        cur.close()
        conn.close()

def get_occupied_seats_by_flight(flight_id):
    """Returns a set of strings representing occupied seats (e.g., 'Economy:5-2') for a flight."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # Get offsets to translate global rows back to local rows
        seatmap = get_flight_seatmap(flight_id)
        if not seatmap:
            return set()
        offsets = {cls['ClassType']: cls['RowOffset'] for cls in seatmap}

        cur.execute("""
            SELECT s.ClassType, s.RowNumber, s.ColNumber 
            FROM Seats s 
            JOIN Orders o ON s.OrderID = o.OrderID 
            WHERE o.FlightID = %s AND o.OrderStatus != 'CancelledBySystem'
        """, (flight_id,))

        results = cur.fetchall()

        # Convert Global Row back to Local Row: (Global 6 - Offset 5) = Local Row 1
        occupied_set = {
            f"{r['ClassType']}:{int(r['RowNumber']) - offsets.get(r['ClassType'], 0)}-{int(r['ColNumber'])}"
            for r in results
        }

        return occupied_set
    finally:
        cur.close()
        conn.close()

def get_all_routes():
    """Fetches all available flight routes."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    # Select specific columns to prevent origin errors
    cur.execute("SELECT RouteID, SourceAirport, DestinationAirport, DurationHours FROM Routes")
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

def get_route_details(route_id):
    """Fetches details of a single route and calculates duration in minutes."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT SourceAirport, DestinationAirport, DurationHours FROM Routes WHERE RouteID = %s", (route_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    if res:
        # Convert duration hours to minutes for landing calculations
        res['DurationMinutes'] = int(res['DurationHours'] * 60)
        return res
    return None

# ==========================================
# 3. BOOKING LOGIC
# ==========================================

def parse_seat_id(seat_id: str):
    """Parses a seat string (e.g., 'Business:1-2') into class, row, and column components."""
    try:
        # Splits 'Business:1-2' into ['Business', '1-2']
        class_type, position = seat_id.split(':')
        row_str, col_str = position.split('-')
        # Converts strings to integers and returns the tuple
        return class_type, int(row_str), int(col_str)

    except (ValueError, AttributeError, IndexError) as e:
        # Logs the error to console for easier debugging
        print(f"Error parsing seat_id '{seat_id}': {e}")
        return None, None, None

def validate_seats_available(flight_id: str, selected_seat_ids: list):
    """Checks if the selected seats are currently available on the flight."""
    occupied = get_occupied_seats_by_flight(flight_id)

    for sid in selected_seat_ids:
        #  Check for direct string match.
        if sid in occupied:
            # If taken, parse the ID to create a user-friendly error message
            ct, r, c = parse_seat_id(sid)
            return False, f"Seat {r}-{c} in {ct} class is already taken."

    #  If the loop completes, all selected seats are available
    return True, "OK"

def compute_selected_seats_cost(flight_id: str, selected_seat_ids: list):
    """Calculates the total cost for a list of selected seats based on class pricing."""
    seatmap = get_flight_seatmap(flight_id)
    prices = {c['ClassType']: float(c['TicketPrice']) for c in seatmap}

    seat_items = []
    total_cost = 0.0

    for sid in selected_seat_ids:
        ct, r, c = parse_seat_id(sid)
        price = prices.get(ct, 0.0)
        seat_items.append({
            "seat_id": sid,
            "ClassType": ct,
            "RowNumber": r,
            "ColNumber": c,
            "Price": price
        })
        total_cost += price

    return seat_items, round(total_cost, 2)

def create_order_with_selected_seats(flight_id, customer_type, customer_email, first_name, last_name, phones,
                                     selected_seats):
    """Creates a new order, reserves seats, and updates flight status to 'Fully Booked' if capacity is reached."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        # 1. Handle Guest logic
        if customer_type == "Guest":
            status, msg = register_guest_if_not_exists(customer_email, first_name, last_name,
                                                       phones[0] if phones else "")
            if status == "details_mismatch":
                raise Exception(msg)

        # 2. Get PlaneID
        cur.execute("SELECT PlaneID FROM Flights WHERE FlightID=%s", (flight_id,))
        res = cur.fetchone()
        if not res:
            raise Exception("Flight not found")
        plane_id = res[0]

        # 3. Calculate total cost and get seatmap for RowOffsets
        seat_items, total_cost = compute_selected_seats_cost(flight_id, selected_seats)
        seatmap = get_flight_seatmap(flight_id)
        offsets = {cls['ClassType']: cls['RowOffset'] for cls in seatmap}

        # 4. Generate Order ID
        cur.execute("SELECT COALESCE(MAX(OrderID), 1000) + 1 FROM Orders")
        order_id = cur.fetchone()[0]

        # 5. Insert main Order record
        cur.execute("""
            INSERT INTO Orders (OrderID, CustomerEmail, CustomerType, FlightID, OrderStatus, OrderDate, TotalCost)
            VALUES (%s, %s, %s, %s, 'Confirmed', %s, %s)
        """, (order_id, customer_email, customer_type, flight_id, datetime.now().date(), total_cost))

        # 6. Insert individual seats
        for sid in selected_seats:
            ct, r, c = parse_seat_id(sid)
            global_row = r + offsets.get(ct, 0)

            cur.execute("""
                INSERT INTO Seats (RowNumber, ColNumber, OrderID, PlaneID, ClassType)
                VALUES (%s, %s, %s, %s, %s)
            """, (global_row, c, order_id, plane_id, ct))

        # --- קטע חדש: בדיקה אם הטיסה התמלאה ---

        # א. חישוב קיבולת המטוס (סך כל המושבים)
        cur.execute("SELECT SUM(NumRows * NumCols) FROM Class WHERE PlaneID = %s", (plane_id,))
        total_capacity = cur.fetchone()[0]

        # ב. חישוב כמה מושבים תפוסים כרגע (כולל מה שהרגע הוספנו)
        cur.execute("""
            SELECT COUNT(*) 
            FROM Seats s
            JOIN Orders o ON s.OrderID = o.OrderID
            WHERE o.FlightID = %s AND o.OrderStatus NOT IN ('CancelledBySystem', 'Client Cancelled')
        """, (flight_id,))
        total_occupied = cur.fetchone()[0]

        # ג. אם מלא -> עדכון סטטוס
        if total_occupied >= total_capacity:
            cur.execute("UPDATE Flights SET FlightStatus = 'Fully Booked' WHERE FlightID = %s", (flight_id,))

        # ----------------------------------------

        conn.commit()
        return True, f"Order {order_id} confirmed successfully!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def generate_auto_flight_id():
    """Generates the next sequential Flight ID (e.g., 'FL105')."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT FlightID FROM Flights WHERE FlightID LIKE 'FL%'")
        rows = cur.fetchall()
        if not rows:
            return "FL001"

        max_num = 0
        for (f_id,) in rows:
            try:
                # Strip 'FL' prefix before converting numeric part to integer
                num_part = int(f_id[2:])
                if num_part > max_num:
                    max_num = num_part
            except (ValueError, IndexError):
                continue

        return f"FL{str(max_num + 1).zfill(3)}"
    finally:
        cur.close()
        conn.close()

# ==========================================
# 4. ORDER MANAGEMENT (User Side)
# ==========================================

def get_registered_orders_with_flight(email: str, status_filter=None):
    """Fetches flight orders for a registered customer, optionally filtered by status."""

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        # Base query
        q = """
            SELECT 
                o.OrderID, o.CustomerEmail, o.CustomerType, o.FlightID,
                o.OrderStatus, o.OrderDate, o.TotalCost,
                f.DepartureDate, f.DepartureTime
            FROM Orders o
            JOIN Flights f ON f.FlightID = o.FlightID
            WHERE o.CustomerEmail=%s AND o.CustomerType='Registered'
        """
        params = [email]

        # Apply status filter if provided
        if status_filter:
            q += " AND o.OrderStatus = %s"
            params.append(status_filter)

        q += " ORDER BY o.OrderDate DESC, o.OrderID DESC"

        cur.execute(q, tuple(params))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def get_registered_order_details(email: str, order_id: str):
    """Fetches details of a single order for a registered customer."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                o.OrderID, o.CustomerEmail, o.CustomerType, o.FlightID,
                o.OrderStatus, o.OrderDate, o.TotalCost,
                f.DepartureDate, f.DepartureTime
            FROM Orders o
            JOIN Flights f ON f.FlightID = o.FlightID
            WHERE o.OrderID=%s AND o.CustomerEmail=%s AND o.CustomerType='Registered'
            LIMIT 1
        """, (order_id, email))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def get_orders_by_email(email):
    """Simple fetch of all orders associated with an email address."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT OrderID, FlightID, OrderStatus, OrderDate, TotalCost 
            FROM Orders 
            WHERE CustomerEmail = %s
        """, (email,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def get_all_orders(limit=200):
    """Fetches a list of all orders in the system, sorted by date."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Orders ORDER BY OrderDate DESC LIMIT %s", (limit,))
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

def get_order_seats(order_id: str):
    """Retrieves the seats associated with a specific order ID."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT ClassType, RowNumber, ColNumber
            FROM Seats
            WHERE OrderID = %s
        """, (order_id,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

def get_guest_order_details(email: str, order_id: str):
    """Fetches order details for a guest, ensuring the flight is valid and future-dated."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                o.OrderID, o.CustomerEmail, o.CustomerType, o.FlightID,
                o.OrderStatus, o.OrderDate, o.TotalCost,
                f.DepartureDate, f.DepartureTime
            FROM Orders o
            JOIN Flights f ON f.FlightID = o.FlightID
            WHERE o.OrderID=%s AND o.CustomerEmail=%s AND o.CustomerType='Guest' AND o.OrderStatus = 'Confirmed'
            AND f.FlightStatus IN ('Scheduled', 'Fully Booked')
              AND TIMESTAMP(f.DepartureDate, f.DepartureTime) > NOW()
            LIMIT 1
        """, (order_id, email))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def cancel_registered_order_with_penalty(order_id: str, email: str):
    """Cancels a registered user's order, charges a 5% penalty, and releases the seats."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute("""
            SELECT TotalCost, FlightID FROM Orders
            WHERE OrderID=%s AND CustomerEmail=%s AND CustomerType='Registered'
            LIMIT 1
        """, (order_id, email))
        r = cur.fetchone()
        if not r:
            conn.rollback()
            return False, "Order not found."

        original_cost = float(r[0]) if r[0] is not None else 0.0
        flight_id = r[1]
        new_cost = round(original_cost * 0.05, 2)

        cur.execute("DELETE FROM Seats WHERE OrderID=%s", (order_id,))

        cur.execute("""
            UPDATE Orders
            SET OrderStatus='Client Cancelled', TotalCost=%s
            WHERE OrderID=%s AND CustomerEmail=%s AND CustomerType='Registered'
        """, (new_cost, order_id, email))

        cur.execute("""
            UPDATE Flights 
            SET FlightStatus = 'Scheduled' 
            WHERE FlightID = %s AND FlightStatus = 'Fully Booked'
        """, (flight_id,))

        conn.commit()
        return True, "Order cancelled successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def cancel_guest_order_with_penalty(order_id: str, email: str):
    """Cancels a guest's order, charges a 5% penalty, and releases the seats."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()

        cur.execute("""
            SELECT TotalCost, FlightID FROM Orders
            WHERE OrderID=%s AND CustomerEmail=%s AND CustomerType='Guest'
            LIMIT 1
        """, (order_id, email))
        r = cur.fetchone()
        if not r:
            conn.rollback()
            return False, "Order not found."

        original_cost = float(r[0]) if r[0] is not None else 0.0
        flight_id = r[1]
        new_cost = round(original_cost * 0.05, 2)

        cur.execute("DELETE FROM Seats WHERE OrderID=%s", (order_id,))

        cur.execute("""
            UPDATE Orders
            SET OrderStatus='Client Cancelled', TotalCost=%s
            WHERE OrderID=%s AND CustomerEmail=%s AND CustomerType='Guest'
        """, (new_cost, order_id, email))

        cur.execute("""
            UPDATE Flights 
            SET FlightStatus = 'Scheduled' 
            WHERE FlightID = %s AND FlightStatus = 'Fully Booked'
        """, (flight_id,))

        conn.commit()
        return True, "Order cancelled successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def can_cancel_order_36h(order_row: dict) -> bool:
    """Checks if the order allows cancellation (must be at least 36 hours before departure)."""
    if not order_row: return False
    if order_row.get("OrderStatus") in ("Client Cancelled", "CancelledBySystem"):
        return False

    dep_date = order_row.get("DepartureDate")
    dep_time = order_row.get("DepartureTime")
    if dep_date is None or dep_time is None: return False

    if isinstance(dep_time, timedelta):
        dep_time = (datetime.min + dep_time).time()

    dep_dt = datetime.combine(dep_date, dep_time)
    return (dep_dt - datetime.now()) >= timedelta(hours=36)


# ==========================================
# 5. MANAGER - RESOURCE MANAGEMENT
# ==========================================

def add_route_safe(origin, destination, duration):
    """Adds a new flight route if it doesn't already exist."""
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # Check for duplicates
        check_query = "SELECT RouteID FROM Routes WHERE SourceAirport = %s AND DestinationAirport = %s"
        cursor.execute(check_query, (origin, destination))

        if cursor.fetchone():
            return False, "Error: This route already exists."

        # Insert new route
        insert_query = "INSERT INTO Routes (SourceAirport, DestinationAirport, DurationHours) VALUES (%s, %s, %s)"
        cursor.execute(insert_query, (origin, destination, duration))
        conn.commit()

        return True, "Route added"
    except Error as e:
        return False, f"Database error: {str(e)}"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def add_new_pilot(pilot_id, phone, first_name, last_name, city, street, house_number, training_passed):
    """Inserts a new pilot record into the database."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Validate inputs slightly
        if not pilot_id or not first_name or not last_name:
            return False, "Missing required fields."

        # --- Check if ID already exists in other roles ---

        # 1. Check against Managers table
        cur.execute("SELECT 1 FROM Managers WHERE ManagerID = %s", (pilot_id,))
        if cur.fetchone():
            return False, "Error: This ID already belongs to a Manager. An employee cannot hold multiple roles."

        # 2. Check against FlightAttendants table
        cur.execute("SELECT 1 FROM FlightAttendants WHERE AttendantID = %s", (pilot_id,))
        if cur.fetchone():
            return False, "Error: This ID already belongs to a Flight Attendant. An employee cannot hold multiple roles."

        # -------------------------------------------------------

        cur.execute("""
            INSERT INTO Pilots 
            (PilotID, StartDate, Phone, FirstName, LastName, City, Street, HouseNumber, TrainingPassed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (pilot_id, date.today(), phone, first_name, last_name, city, street, house_number, int(training_passed)))

        conn.commit()
        return True, "Pilot added successfully."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Error: Pilot ID already exists."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def add_new_attendant(attendant_id, phone, first_name, last_name, city, street, house_number, training_passed):
    """Inserts a new flight attendant record into the database."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        if not attendant_id or not first_name or not last_name:
            return False, "Missing required fields."

        # --- Check if ID already exists in other roles ---

        # 1. Check against Managers table
        cur.execute("SELECT 1 FROM Managers WHERE ManagerID = %s", (attendant_id,))
        if cur.fetchone():
            return False, "Error: This ID already belongs to a Manager. An employee cannot hold multiple roles."

        # 2. Check against Pilots table
        cur.execute("SELECT 1 FROM Pilots WHERE PilotID = %s", (attendant_id,))
        if cur.fetchone():
            return False, "Error: This ID already belongs to a Pilot. An employee cannot hold multiple roles."

        # -------------------------------------------------------

        cur.execute("""
            INSERT INTO FlightAttendants 
            (AttendantID, StartDate, Phone, FirstName, LastName, City, Street, HouseNumber, TrainingPassed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (attendant_id, date.today(), phone, first_name, last_name, city, street, house_number, int(training_passed)))

        conn.commit()
        return True, "Flight Attendant added successfully."
    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, "Error: Attendant ID already exists."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()


def get_all_crew(role_filter=None, training_filter=None, status_filter=None):
    """Fetches crew members and determines their real-time availability based on current flight assignments."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # Capture the exact current time from Python
    now_time = datetime.now()

    # 1. Fetch all crew (Pilots & Attendants) and calculate Real-Time Data
    query = """
    SELECT 
        ID, FirstName, LastName, Role, TrainingPassed,

        -- Check Real-Time Availability
        CASE 
            WHEN EXISTS (
                SELECT 1 FROM Flights f
                JOIN (
                    SELECT FlightID, PilotID AS CrewID FROM PilotsInFlights
                    UNION ALL
                    SELECT FlightID, AttendantID AS CrewID FROM FlightAttendantsInFlights
                ) AS CrewActivity ON f.FlightID = CrewActivity.FlightID
                WHERE CrewActivity.CrewID = AllCrew.ID
                AND f.FlightStatus != 'Cancelled'
                AND %s BETWEEN TIMESTAMP(f.DepartureDate, f.DepartureTime) 
                           AND TIMESTAMP(f.ArrivalDate, f.ArrivalTime)
            ) THEN 'Busy'
            ELSE 'Available'
        END AS Status,

        -- Determine Current Location
        COALESCE(
            (
                SELECT r.DestinationAirport
                FROM Flights f
                JOIN Routes r ON f.RouteID = r.RouteID
                JOIN (
                    SELECT FlightID, PilotID AS CrewID FROM PilotsInFlights
                    UNION ALL
                    SELECT FlightID, AttendantID AS CrewID FROM FlightAttendantsInFlights
                ) AS CrewHistory ON f.FlightID = CrewHistory.FlightID
                WHERE CrewHistory.CrewID = AllCrew.ID
                AND f.FlightStatus != 'Cancelled'
                AND TIMESTAMP(f.ArrivalDate, f.ArrivalTime) <= %s 
                ORDER BY f.ArrivalDate DESC, f.ArrivalTime DESC
                LIMIT 1
            ), 
            'TLV'
        ) AS CurrentLocation

    FROM (
        -- Combine Pilots and Attendants into one list
        SELECT PilotID AS ID, FirstName, LastName, 'Pilot' AS Role, TrainingPassed FROM Pilots
        UNION ALL
        SELECT AttendantID AS ID, FirstName, LastName, 'Attendant' AS Role, TrainingPassed FROM FlightAttendants
    ) AS AllCrew
    """

    # Pass 'now_time' twice: once for Status, once for Location
    cur.execute(query, (now_time, now_time))
    results = cur.fetchall()
    conn.close()

    # 4. Apply Filters on the fetched list
    filtered_crew = []
    for member in results:
        # Filter by Role (Pilot / Attendant)
        if role_filter and member['Role'] != role_filter:
            continue

        # Filter by Training
        if training_filter is not None and member['TrainingPassed'] != training_filter:
            continue

        # Filter by Status (Available / Busy)
        if status_filter and member['Status'] != status_filter:
            continue

        filtered_crew.append(member)

    return filtered_crew

def add_new_plane(plane_id, plane_size, manufacturer, purchase_date, class_config):
    """Inserts a new plane and its seating configuration into the database."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()

        # 1. Insert into Plane table
        if not plane_id or not manufacturer or not purchase_date:
            raise Exception("Missing required fields.")

        cur.execute("""
            INSERT INTO Plane (PlaneID, PlaneSize, Manufacturer, PurchaseDate)
            VALUES (%s, %s, %s, %s)
        """, (plane_id, plane_size, manufacturer, purchase_date))

        # 2. Insert into Class table (Dynamic based on config)
        for c in class_config:
            cur.execute("""
                INSERT INTO Class (PlaneID, ClassType, NumRows, NumCols)
                VALUES (%s, %s, %s, %s)
            """, (plane_id, c['type'], c['rows'], c['cols']))

        conn.commit()
        return True, "Plane and seating configuration added successfully."

    except mysql.connector.IntegrityError:
        conn.rollback()
        return False, f"Error: Plane ID '{plane_id}' already exists."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

# ==========================================
# 6. MANAGER - FLIGHT SCHEDULING (Complex Logic)
# ==========================================

def get_eligible_planes(route_id, dep_dt, arr_dt, source_airport):
    """Finds planes that match the route requirements, are available, and are currently at the source airport."""
    route = get_route_details(route_id)
    duration = route.get('DurationHours', 0) if route else 0

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # 1. Check Availability & Size
    query = """
        SELECT PlaneID, Manufacturer, PlaneSize FROM Plane 
        WHERE (%s <= 6.0 OR PlaneSize = 'Large')
        AND PlaneID NOT IN (
            SELECT PlaneID FROM Flights 
            WHERE FlightStatus != 'Cancelled'
            AND (%s < TIMESTAMP(ArrivalDate, ArrivalTime)) 
            AND (%s > TIMESTAMP(DepartureDate, DepartureTime))
        )
    """
    cur.execute(query, (duration, dep_dt, arr_dt))
    candidates = cur.fetchall()
    cur.close()
    conn.close()

    # 2. Filter by Location
    eligible_final = []
    for p in candidates:
        loc = get_last_plane_location(p['PlaneID'], dep_dt)
        if loc == source_airport or loc is None:
            eligible_final.append(p)

    return eligible_final

def get_eligible_pilots(is_long_haul, dep_dt, arr_dt, source_airport):
    """Finds pilots who are qualified, available, and at the correct location."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # 1. Check Training & Schedule
    query = """
        SELECT PilotID, FirstName, LastName FROM Pilots 
        WHERE (%s = 0 OR TrainingPassed = 1)
        AND PilotID NOT IN (
            SELECT pif.PilotID FROM PilotsInFlights pif
            JOIN Flights f ON pif.FlightID = f.FlightID
            WHERE f.FlightStatus != 'Cancelled'
            AND (%s < TIMESTAMP(f.ArrivalDate, f.ArrivalTime)) 
            AND (%s > TIMESTAMP(f.DepartureDate, f.DepartureTime))
        )
    """
    cur.execute(query, (1 if is_long_haul else 0, dep_dt, arr_dt))
    candidates = cur.fetchall()
    cur.close()
    conn.close()

    # 2. Filter by Location
    eligible_final = []
    for p in candidates:
        loc = get_last_crew_location(p['PilotID'], 'Pilot', dep_dt)
        if loc == source_airport or loc is None:
            eligible_final.append(p)

    return eligible_final

def get_eligible_attendants(is_long_haul, dep_dt, arr_dt, source_airport):
    """Finds flight attendants who are qualified, available, and at the correct location."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    # 1. Check Training & Schedule
    query = """
        SELECT AttendantID, FirstName, LastName FROM FlightAttendants 
        WHERE (%s = 0 OR TrainingPassed = 1)
        AND AttendantID NOT IN (
            SELECT faif.AttendantID FROM FlightAttendantsInFlights faif
            JOIN Flights f ON faif.FlightID = f.FlightID
            WHERE f.FlightStatus != 'Cancelled'
            AND (%s < TIMESTAMP(f.ArrivalDate, f.ArrivalTime)) 
            AND (%s > TIMESTAMP(f.DepartureDate, f.DepartureTime))
        )
    """
    cur.execute(query, (1 if is_long_haul else 0, dep_dt, arr_dt))
    candidates = cur.fetchall()
    cur.close()
    conn.close()

    # 2. Filter by Location
    eligible_final = []
    for a in candidates:
        loc = get_last_crew_location(a['AttendantID'], 'Attendant', dep_dt)
        if loc == source_airport or loc is None:
            eligible_final.append(a)

    return eligible_final

def get_last_crew_location(member_id, member_type, check_time):
    """Determines the last airport a crew member arrived at before a specific time."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        if member_type == 'Pilot':
            join_table = "PilotsInFlights"
            id_col = "PilotID"
        else:
            join_table = "FlightAttendantsInFlights"
            id_col = "AttendantID"

        query = f"""
            SELECT r.DestinationAirport
            FROM Flights f
            JOIN Routes r ON f.RouteID = r.RouteID
            JOIN {join_table} j ON f.FlightID = j.FlightID
            WHERE j.{id_col} = %s
              AND f.FlightStatus != 'Cancelled'
              AND TIMESTAMP(f.ArrivalDate, f.ArrivalTime) <= %s
            ORDER BY f.ArrivalDate DESC, f.ArrivalTime DESC
            LIMIT 1
        """
        cur.execute(query, (member_id, check_time))
        result = cur.fetchone()

        return result['DestinationAirport'] if result else None
    finally:
        cur.close()
        conn.close()

def get_last_plane_location(plane_id, check_time):
    """Determines the last airport a plane arrived at before a specific time."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT r.DestinationAirport
            FROM Flights f
            JOIN Routes r ON f.RouteID = r.RouteID
            WHERE f.PlaneID = %s
              AND f.FlightStatus != 'Cancelled'
              AND TIMESTAMP(f.ArrivalDate, f.ArrivalTime) <= %s
            ORDER BY f.ArrivalDate DESC, f.ArrivalTime DESC
            LIMIT 1
        """
        cur.execute(query, (plane_id, check_time))
        result = cur.fetchone()
        return result['DestinationAirport'] if result else None
    finally:
        cur.close()
        conn.close()

def validate_flight_assignment(plane_id, duration_hours, pilot_ids, attendant_ids):
    """Validates that crew size matches plane size and that crew members have required training for long flights."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT PlaneSize FROM Plane WHERE PlaneID = %s", (plane_id,))
    plane = cur.fetchone()
    plane_size = plane['PlaneSize'] if plane else 'Small'

    is_long_flight = duration_hours > 6.0

    # Validate required crew counts based on aircraft size
    if plane_size == 'Large':
        if len(pilot_ids) < 3: return False, "Large planes require 3 pilots."
        if len(attendant_ids) < 6: return False, "Large planes require 6 attendants."
    else:
        if len(pilot_ids) < 2: return False, "Small planes require 2 pilots."
        if len(attendant_ids) < 3: return False, "Small planes require 3 attendants."

    # Verify long-haul training for flights exceeding 6 hours
    if is_long_flight:
        for p_id in pilot_ids:
            cur.execute("SELECT TrainingPassed FROM Pilots WHERE PilotID = %s", (p_id,))
            p = cur.fetchone()
            if not p or not p['TrainingPassed']:
                return False, f"Pilot {p_id} must have training for long flights."

        for a_id in attendant_ids:
            cur.execute("SELECT TrainingPassed FROM FlightAttendants WHERE AttendantID = %s", (a_id,))
            a = cur.fetchone()
            if not a or not a['TrainingPassed']:
                return False, f"Attendant {a_id} must have training for long flights."

    cur.close()
    conn.close()
    return True, "OK"

def create_flight_full_process(data, prices, pilot_ids, attendant_ids):
    """Creates a flight, assigns crew, and sets ticket prices in a single transaction."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        conn.start_transaction()

        # 1. Insert primary flight record
        cur.execute("""
            INSERT INTO Flights (FlightID, PlaneID, RouteID, ManagerID, DepartureDate, 
                               DepartureTime, ArrivalDate, ArrivalTime, FlightType, FlightStatus)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Scheduled')
        """, (data['flight_id'], data['plane_id'], data['route_id'], data['manager_id'],
              data['dep_date'], data['dep_time'], data['arr_date'], data['arr_time'], data['type']))

        # 2. Insert crew assignments into relationship tables
        for p_id in pilot_ids:
            cur.execute("INSERT INTO PilotsInFlights (FlightID, PilotID) VALUES (%s, %s)", (data['flight_id'], p_id))
        for a_id in attendant_ids:
            cur.execute("INSERT INTO FlightAttendantsInFlights (FlightID, AttendantID) VALUES (%s, %s)",
                        (data['flight_id'], a_id))

        # 3. Fetch allowed classes for this specific plane to prevent foreign key errors
        cur.execute("SELECT ClassType FROM Class WHERE PlaneID = %s", (data['plane_id'],))
        allowed_classes = [row[0] for row in cur.fetchall()]

        # 4. Insert class-specific pricing records ONLY if the class exists for this plane
        for class_type, price in prices.items():
            if class_type in allowed_classes and price is not None:
                cur.execute("""
                    INSERT INTO FlightClasses (FlightID, PlaneID, ClassType, TicketPrice) 
                    VALUES (%s, %s, %s, %s)
                """, (data['flight_id'], data['plane_id'], class_type, price))

        conn.commit()
        return True, "Success"

    except Exception as e:
        conn.rollback()
        # Returns the exact error message if the transaction fails
        return False, str(e)
    finally:
        cur.close()
        conn.close()

# ==========================================
# 7. MANAGER - OPERATIONS
# ==========================================

def cancel_flight_cascade(flight_id):
    """Cancels a flight, deletes associated orders and assignments, and notifies system (72h rule applied)."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()

        # 1. Fetch flight details (added Date and Time)
        cur.execute("SELECT FlightStatus, DepartureDate, DepartureTime FROM Flights WHERE FlightID = %s", (flight_id,))
        flight = cur.fetchone()

        if not flight:
            return False, "Flight not found."

        # 2. Check status
        if flight['FlightStatus'] not in ['Scheduled', 'Fully Booked']:
            return False, f"Cannot cancel flight in status {flight['FlightStatus']}."

        # 3. Simple Time Check (72 hours before)
        # Combine date and time to one object
        dep_dt = datetime.combine(flight['DepartureDate'], (datetime.min + flight['DepartureTime']).time())

        if dep_dt - datetime.now() < timedelta(hours=72):
            return False, "Cancellation is only allowed up to 72 hours before departure."

        # 4. Perform cancellation - Main Flight & Orders
        cur.execute("UPDATE Flights SET FlightStatus = 'Cancelled' WHERE FlightID = %s", (flight_id,))
        cur.execute("UPDATE Orders SET OrderStatus = 'CancelledBySystem', TotalCost = 0 WHERE FlightID = %s",
                    (flight_id,))
        cur.execute("""
            DELETE FROM Seats WHERE OrderID IN (
                SELECT OrderID FROM Orders WHERE FlightID = %s
            )
        """, (flight_id,))

        cur.execute("DELETE FROM PilotsInFlights WHERE FlightID = %s", (flight_id,))
        cur.execute("DELETE FROM FlightAttendantsInFlights WHERE FlightID = %s", (flight_id,))

        conn.commit()
        return True, f"Flight {flight_id} cancelled successfully."

    except Exception as e:
        conn.rollback()
        return False, f"Database Error: {str(e)}"
    finally:
        cur.close()
        conn.close()

def check_cancellation_eligibility(flight_id):
    """Verifies flight cancellation eligibility based on status and the 72-hour departure window."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT FlightStatus, DepartureDate, DepartureTime FROM Flights WHERE FlightID = %s", (flight_id,))
        flight = cur.fetchone()

        if not flight:
            return False, "Flight not found."

        if flight['FlightStatus'] not in ['Scheduled', 'Fully Booked']:
            return False, f"Cannot cancel flight in status '{flight['FlightStatus']}'."

        dep_time = flight['DepartureTime']
        if isinstance(dep_time, timedelta):
            dep_time = (datetime.min + dep_time).time()

        dep_dt = datetime.combine(flight['DepartureDate'], dep_time)

        if dep_dt - datetime.now() < timedelta(hours=72):
            return False, "Cancellation is only allowed up to 72 hours before departure."

        return True, "OK"

    finally:
        cur.close()
        conn.close()

def update_past_flights_to_landed():
    """Auto-updates the status of flights that have passed their arrival time to 'Landed'."""
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # Get current time for comparison
        now = datetime.now()

        # SQL query combining ArrivalDate and ArrivalTime to check against 'now'
        #
        query = """
            UPDATE Flights 
            SET FlightStatus = 'Landed' 
            WHERE FlightStatus IN ('Scheduled', 'Fully Booked')
            AND TIMESTAMP(ArrivalDate, ArrivalTime) <= %s
        """
        cursor.execute(query, (now,))
        conn.commit()
    except Error as e:
        print(f"Error auto-updating flight statuses: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_flight_details_for_confirmation(flight_id):
    """Fetches flight details specifically for the confirmation screen."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    query = """
        SELECT f.FlightID, f.DepartureDate, f.DepartureTime, f.FlightType,
               r.SourceAirport, r.DestinationAirport
        FROM Flights f
        JOIN Routes r ON f.RouteID = r.RouteID
        WHERE f.FlightID = %s
    """

    cur.execute(query, (flight_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

# ==========================================
# 8. ANALYTICS & REPORTS
# ==========================================
def generate_occupancy_chart_image():
    """Report 1: Occupancy (Donut)"""
    # Calculates fleet-wide average occupancy by comparing sold seats to total plane capacity
    con = None
    try:
        con = get_conn()
        query = """
            SELECT 
        AVG(
            (IFNULL(Occupied.SeatsSold, 0) / PlaneCapacity.TotalSeats) * 100
        ) AS Average_Occupancy_Percentage
    FROM 
        Flights F
    JOIN (
        SELECT PlaneID, SUM(NumRows * NumCols) AS TotalSeats
        FROM Class
        GROUP BY PlaneID
    ) AS PlaneCapacity ON F.PlaneID = PlaneCapacity.PlaneID
    LEFT JOIN (
        SELECT O.FlightID, COUNT(*) AS SeatsSold
        FROM Orders O
        JOIN Seats S ON O.OrderID = S.OrderID
        WHERE O.OrderStatus IN ('Completed') 
        GROUP BY O.FlightID
    ) AS Occupied ON F.FlightID = Occupied.FlightID
    WHERE 
        F.FlightStatus = 'Landed';
        """
        df = pd.read_sql_query(query, con)

        if df.empty or pd.isna(df.iloc[0]['Average_Occupancy_Percentage']):
            return None, "No data found."

        occupancy_rate = float(df.iloc[0]['Average_Occupancy_Percentage'])
        empty_rate = max(0, 100 - occupancy_rate)

        labels = ['Occupied', 'Empty']
        sizes = [occupancy_rate, empty_rate]
        colors = ['#31688e', '#e0e0e0']

        # Generates a donut chart representing the ratio of occupied vs empty seats
        plt.figure(figsize=(8, 8))
        plt.pie(sizes, labels=None, colors=colors, startangle=90, counterclock=False,
                wedgeprops={'width': 0.3, 'edgecolor': 'white'})
        plt.text(0, 0, f"{occupancy_rate:.1f}%", ha='center', va='center', fontsize=35, weight='bold', color='#31688e')
        plt.text(0, -0.15, "Average Occupancy", ha='center', va='center', fontsize=12, color='gray')
        plt.title("Fleet Average Occupancy Rate", fontsize=16, weight='bold', pad=20)
        plt.legend(['Occupied Seats', 'Empty Seats'], loc='lower right')
        plt.tight_layout()

        return _fig_to_base64()
    except Exception as e:
        return None, str(e)
    finally:
        _close_conn(con)

def generate_revenue_chart_image():
    """Report 2: Revenue"""
    # Analyzes total revenue distributed across plane manufacturers and seat classes
    con = None
    try:
        con = get_conn()
        query = """
        WITH seats_per_order_class AS (
          SELECT s.OrderID, s.ClassType, COUNT(*) AS seats_in_class
          FROM Seats AS s
          GROUP BY s.OrderID, s.ClassType),
        seats_per_order AS (
          SELECT OrderID, SUM(seats_in_class) AS total_seats
          FROM seats_per_order_class
          GROUP BY OrderID)
        SELECT p.PlaneSize AS PlaneSize, p.Manufacturer AS Manufacturer, soc.ClassType AS ClassType,
        ROUND(SUM(
            CASE 
              WHEN spo.total_seats > 0 THEN o.TotalCost * (soc.seats_in_class / spo.total_seats)
              ELSE o.TotalCost
            END
          ), 2) AS TotalRevenue

        FROM Orders AS o
        JOIN Flights AS f ON f.FlightID = o.FlightID
        JOIN Plane AS p ON p.PlaneID = f.PlaneID
        LEFT JOIN seats_per_order_class AS soc ON soc.OrderID = o.OrderID
        LEFT JOIN seats_per_order AS spo ON spo.OrderID = o.OrderID

        WHERE TRIM(o.OrderStatus) IN ('Confirmed', 'Completed', 'Client Cancelled', 'CancelledByClient')
        GROUP BY p.PlaneSize, p.Manufacturer, soc.ClassType
        ORDER BY p.PlaneSize, p.Manufacturer, soc.ClassType;
        """
        df = pd.read_sql_query(query, con)
        if df.empty: return None, "No revenue data found."

        for c in ["PlaneSize", "Manufacturer", "ClassType"]: df[c] = df[c].astype(str).str.strip()
        df["TotalRevenue"] = pd.to_numeric(df["TotalRevenue"], errors="coerce")
        df = df.dropna(subset=["TotalRevenue"])

        # Creates a grouped bar chart faceted by plane size to visualize revenue streams
        sns.set_theme(style="whitegrid", font_scale=0.9)
        plt.figure()
        g = sns.catplot(data=df, kind="bar", y="Manufacturer", x="TotalRevenue", hue="ClassType",
                        col="PlaneSize", col_wrap=1, height=3.5, aspect=2.4, palette="viridis", errorbar=None,
                        legend=False)

        g.set_titles("Plane Size: {col_name}", size=12, weight="bold")
        for ax in g.axes.flatten(): ax.xaxis.set_major_formatter(ticker.StrMethodFormatter("{x:,.0f}"))
        g.fig.set_size_inches(10, 8)

        handles, labels = g.axes[0].get_legend_handles_labels()
        if handles: g.fig.legend(handles, labels, title="Seat Class", loc="center left", bbox_to_anchor=(0.86, 0.5))
        g.fig.suptitle("Revenue Analysis by Manufacturer & Class", y=0.99, fontsize=16, weight="bold")
        g.fig.subplots_adjust(right=0.82, top=0.90, hspace=0.35)

        return _fig_to_base64_catplot(g)
    except Exception as e:
        return None, str(e)
    finally:
        _close_conn(con)

def generate_crew_hours_chart_image():
    """Report 3: Team Hours"""
    # Tracks total flight hours for top 15 crew members (pilots and attendants)
    con = None
    try:
        con = get_conn()
        query = """
          SELECT EmployeeID, FirstName, LastName, Role, FlightType, SUM(DurationHours) AS Total_Flight_Hours
        FROM (
            SELECT p.PilotID AS EmployeeID, p.FirstName, p.LastName, 'Pilot' AS Role, f.FlightType, r.DurationHours
            FROM Pilots p
            JOIN PilotsInFlights AS pif ON p.PilotID = pif.PilotID
            JOIN Flights AS f ON pif.FlightID = f.FlightID
            JOIN Routes AS r ON f.RouteID = r.RouteID
            WHERE f.FlightStatus = 'Landed'

            UNION ALL

            SELECT fa.AttendantID AS EmployeeID, fa.FirstName, fa.LastName, 'Flight Attendant' AS Role, f.FlightType, r.DurationHours
            FROM FlightAttendants AS fa
            JOIN FlightAttendantsInFlights AS faif ON fa.AttendantID = faif.AttendantID
            JOIN Flights AS f ON faif.FlightID = f.FlightID
            JOIN Routes AS r ON f.RouteID = r.RouteID
            WHERE f.FlightStatus = 'Landed'
        ) AS CombinedStaff
        GROUP BY EmployeeID, FirstName, LastName, Role, FlightType
        ORDER BY Role, EmployeeID, FlightType;
        """
        df = pd.read_sql_query(query, con)
        if df.empty: return None, "No crew data found."

        df["Total_Flight_Hours"] = pd.to_numeric(df["Total_Flight_Hours"], errors="coerce")

        # --- SMART FIX FOR HEBREW/ENGLISH MIX ---
        # Define a helper to detect Hebrew characters
        def fix_text(text):
            if not text: return ""
            text = str(text)
            # Check if string contains Hebrew characters (Unicode range \u0590-\u05FF)
            if any("\u0590" <= c <= "\u05FF" for c in text):
                return text[::-1] # Reverse only if Hebrew
            return text # Keep English as is

        # Apply the smart fix
        df["FirstName"] = df["FirstName"].apply(fix_text)
        df["LastName"] = df["LastName"].apply(fix_text)
        # ------------------------------------------------------------

        df["FullName"] = df["FirstName"] + " " + df["LastName"] + " (" + df["Role"].map(
            {'Pilot': 'P', 'Flight Attendant': 'FA'}) + ")"

        top_ids = df.groupby("EmployeeID")["Total_Flight_Hours"].sum().nlargest(15).index
        df = df[df["EmployeeID"].isin(top_ids)]

        # Displays a horizontal bar chart of employee workload categorized by flight type
        sns.set_theme(style="whitegrid")
        plt.figure(figsize=(10, 6))
        ax = sns.barplot(data=df, y="FullName", x="Total_Flight_Hours", hue="FlightType", palette="viridis")
        plt.title("Top 15 Employees: Flight Hours", fontsize=16, weight='bold')
        for container in ax.containers: ax.bar_label(container, fmt='%.1f', padding=3, fontsize=9)
        plt.legend(title="Flight Type", loc="upper left", bbox_to_anchor=(1.02, 1))
        plt.tight_layout()

        return _fig_to_base64()
    except Exception as e:
        return None, str(e)
    finally:
        _close_conn(con)

def generate_cancellation_chart_image():
    """Report 4: Cancellations"""
    # Computes monthly cancellation rates based on customer order history
    con = None
    try:
        con = get_conn()
        query = """
        SELECT 
            YEAR(OrderDate) AS OrderYear,
            MONTH(OrderDate) AS OrderMonth,
            AVG(OrderStatus IN ('Client Cancelled')) * 100 AS Cancellation_Rate
        FROM Orders
        GROUP BY OrderYear, OrderMonth
        ORDER BY OrderYear DESC, OrderMonth DESC;
            """
        df = pd.read_sql_query(query, con)
        if df.empty: return None, "No data."

        display_df = df.copy()

        display_df["Cancellation_Rate"] = display_df["Cancellation_Rate"].apply(lambda x: f"{x:.2f}%")

        display_df.columns = ["Year", "Month", "Cancellation Rate"]

        num_rows = len(display_df)
        row_height = 0.5
        header_space = 2
        fig_height = (num_rows * row_height) + header_space

        # Formats and renders a styled table to display cancellation metrics over time
        fig, ax = plt.subplots(figsize=(8, max(4, fig_height)))

        ax.axis('tight')
        ax.axis('off')

        plt.title("Monthly Cancellation Rate Report", fontsize=16, weight='bold', pad=20, color='#31688e')

        table = ax.table(cellText=display_df.values, colLabels=display_df.columns, loc='center', cellLoc='center')

        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 1.8)

        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#31688e')
                cell.set_edgecolor('white')
            else:
                cell.set_edgecolor('#dddddd')
                if row % 2 == 0:
                    cell.set_facecolor('#f8f9fa')

        plt.tight_layout()
        return _fig_to_base64()

    except Exception as e:
        return None, str(e)
    finally:
        _close_conn(con)

def generate_fleet_activity_chart_image():
    """Report 5: Fleet Activity"""
    # aggregates aircraft usage, monthly utilization, and identifies the most frequent routes
    con = None
    try:
        con = get_conn()
        query = """
        SELECT 
            F.PlaneID,
            YEAR(F.DepartureDate) AS Year,
            MONTH(F.DepartureDate) AS Month,
            SUM(F.FlightStatus = 'Landed') AS Flights_Performed,
            SUM(F.FlightStatus = 'Cancelled') AS Flights_Cancelled,
            ROUND(SUM(IF(F.FlightStatus = 'Landed', R.DurationHours, 0)) / 720 * 100, 2) AS Utilization_Rate_Percent,

            (   SELECT CONCAT(R2.SourceAirport, '-', R2.DestinationAirport)
                FROM Flights AS F2 
                JOIN Routes AS R2 ON F2.RouteID = R2.RouteID
                WHERE F2.PlaneID = F.PlaneID 
                  AND YEAR(F2.DepartureDate) = YEAR(ANY_VALUE(F.DepartureDate))
                  AND MONTH(F2.DepartureDate) = MONTH(ANY_VALUE(F.DepartureDate))
                  AND F2.FlightStatus = 'Landed'
                GROUP BY R2.SourceAirport, R2.DestinationAirport
                ORDER BY COUNT(*) DESC
                LIMIT 1) AS Dominant_Route

        FROM Flights AS F JOIN Routes AS R ON F.RouteID = R.RouteID
        WHERE F.FlightStatus IN ('Landed', 'Cancelled')
        GROUP BY F.PlaneID, YEAR(F.DepartureDate), MONTH(F.DepartureDate)
        ORDER BY Year DESC, Month DESC, F.PlaneID;

        """
        df = pd.read_sql_query(query, con)
        if df.empty: return None, "No fleet data."

        display_df = df.copy()
        display_df.columns = ["Plane ID", "Year", "Month", "Flights (OK)", "Cancelled", "Utilization (%)",
                              "Dominant Route"]

        display_df["Dominant Route"] = display_df["Dominant Route"].fillna("-")

        num_rows = len(display_df)
        row_height = 0.4
        header_space = 2
        fig_height = (num_rows * row_height) + header_space

        # Renders a comprehensive summary table for fleet performance tracking
        fig, ax = plt.subplots(figsize=(12, max(5, fig_height)))

        ax.axis('tight')
        ax.axis('off')

        plt.title("Full Fleet Activity Report", fontsize=16, weight='bold', pad=20, color='#31688e')

        table = ax.table(cellText=display_df.values, colLabels=display_df.columns, loc='center', cellLoc='center')

        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.8)

        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(weight='bold', color='white')
                cell.set_facecolor('#31688e')
                cell.set_edgecolor('white')
            else:
                cell.set_edgecolor('#dddddd')
                if row % 2 == 0:
                    cell.set_facecolor('#f8f9fa')

        plt.tight_layout()
        return _fig_to_base64()

    except Exception as e:
        return None, str(e)
    finally:
        _close_conn(con)

# ==========================================
# 9. HELPERS
# ==========================================

def _fig_to_base64():
    """Converts the current Matplotlib figure to a base64 string."""
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    data = base64.b64encode(img.getvalue()).decode()
    plt.close('all')
    return data, None

def _fig_to_base64_catplot(g):
    """Converts a Seaborn FacetGrid object to a base64 string."""
    img = io.BytesIO()
    g.fig.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    data = base64.b64encode(img.getvalue()).decode()
    plt.close('all')
    return data, None

def _close_conn(con):
    """Safely closes the database connection if it is open."""
    if con and con.is_connected(): con.close()

