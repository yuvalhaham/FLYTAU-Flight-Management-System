from flask import Flask, render_template, request, redirect, session, flash, jsonify
from datetime import timedelta, datetime, date
import utils


app = Flask(__name__)

# ==========================================
# 1. CONFIGURATION & SESSION MANAGEMENT
# ==========================================

# Set secret key and session lifetime (30 minutes)
app.secret_key = "CHANGE_ME_TO_SOMETHING_RANDOM"
app.permanent_session_lifetime = timedelta(minutes=30)


@app.before_request
def keep_session_alive():
    """Refreshes the session lifetime on every request to keep the user logged in."""
    session.permanent = True


# ==========================================
# 2. GENERAL & AUTHENTICATION (Login/Logout)
# ==========================================

@app.route("/")
def welcome():
    """Renders the main welcome/landing page."""
    return render_template("welcome.html")

@app.route("/guest")
def guest():
    """Initializes a guest session and redirects to the flights page."""
    session.clear()
    session["user_type"] = "guest"
    return redirect("/flights")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles the registration process (Multi-step to allow dynamic phone count)."""

    # GET Request: Show Step 1 (Basic Info + Phone Count)
    if request.method == "GET":
        return render_template("register.html")

    # POST Request: Check which step we are coming from
    step = request.form.get("step")

    # --- STEP 1 SUBMITTED: Move to Phone Entry ---
    if step == "1":
        # Collect basic info to pass to next page (so we don't lose it)
        user_data = {
            "email": request.form.get("email", "").strip(),
            "password": request.form.get("password", "").strip(),
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "passport_number": request.form.get("passport_number", "").strip(),
            "birth_date": request.form.get("birth_date", "").strip(),
            "phone_count": int(request.form.get("phone_count", 1))  # Default to 1 if missing
        }

        # Render Step 2 HTML with the count and data
        return render_template("register_step2.html", data=user_data)

    # --- STEP 2 SUBMITTED: Final Registration ---
    elif step == "2":
        # 1. Extract basic info (Passed as hidden fields from Step 2)
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        passport_number = request.form.get("passport_number", "").strip()
        birth_date = request.form.get("birth_date", "").strip()

        # 2. Collect Validated Phones
        raw_phones = request.form.getlist("phones")
        phones = [p.strip() for p in raw_phones if p and p.strip()]

        if not phones:
            # Should not happen if HTML required=True is set, but good safety net
            # If error, we send them back to Step 1 to restart
            return render_template("register.html", error="At least one phone number is required.")

        # 3. Save to Database
        ok, msg = utils.register_registered_customer(
            email=email, password=password, first_name=first_name,
            last_name=last_name, passport_number=passport_number,
            birth_date=birth_date, phones=phones
        )

        if not ok:
            # If DB error, go back to Step 1 so they can fix data
            return render_template("register.html", error=msg)

        # 4. Success
        session.clear()
        session["user_type"] = "registered"
        session["email"] = email

        return redirect("/flights")

    # Fallback
    return redirect("/register")

@app.route("/login_registered", methods=["GET", "POST"])
def login_registered():
    """Authenticates a registered customer using email and password."""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if utils.check_registered_login(email, password):
            session.clear()
            session["user_type"] = "registered"
            session["email"] = email
            return redirect("/flights")

        return render_template("login_registered.html", error="Email or Password are incorrect")

    return render_template("login_registered.html")

@app.route("/login_manager", methods=["GET", "POST"])
def login_manager():
    """Authenticates a manager using Manager ID and password."""
    if request.method == "POST":
        manager_id = request.form.get("manager_id", "").strip()
        password = request.form.get("password", "").strip()

        ok = utils.check_manager_login(manager_id, password)
        if ok:
            session.clear()
            session["user_type"] = "manager"
            session["manager_id"] = manager_id
            return redirect("/flights")

        return render_template("login_manager.html", error="ManagerID or Password are incorrect")

    return render_template("login_manager.html")

@app.route("/logout")
def logout():
    """Clears the session and redirects the user to the home page."""
    session.clear()
    return redirect("/")

# ==========================================
# 3. FLIGHT BROWSING (Main Screen)
# ==========================================

@app.route("/flights", methods=["GET"])
def flights():
    """Displays the list of flights with filtering options."""
    if "user_type" not in session:
        return redirect("/")

    # --- NEW: Trigger auto-update for past flights ---
    utils.update_past_flights_to_landed()
    # -----------------------------------------------------------------------

    user_type = session.get("user_type")

    # Retrieve existing parameters from the search filters
    flight_id = request.args.get("flight_id", "").strip()
    status = request.args.get("status", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    # Retrieve new filters
    plane_id = request.args.get("plane_id", "").strip()
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()
    arrival_date = request.args.get("arrival_date", "").strip()

    if user_type != "manager":
        # Non-managers (Registered/Guests) only see Scheduled flights
        status = "Scheduled"
        # Hide Plane ID filtering from regular users
        plane_id = None

    # Fetching filtered list from database
    flights_list = utils.get_flights_filtered(
        flight_id=flight_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        plane_id=plane_id,
        source=source,
        destination=destination,
        arrival_date=arrival_date
    )

    # --- Logic: Calculate 72-hour cancellation window ---
    now = datetime.now()

    for f in flights_list:
        # 1. Normalize DepartureTime (Handling potential timedelta from MySQL)
        d_time = f['DepartureTime']
        if isinstance(d_time, timedelta):
            d_time = (datetime.min + d_time).time()

        # 2. Combine Date and Time into a single datetime object
        flight_dt = datetime.combine(f['DepartureDate'], d_time)

        # 3. Check if current time is more than 72 hours before departure
        time_diff = flight_dt - now
        f['allow_cancel'] = time_diff > timedelta(hours=72)
    # --------------------------------------------------------

    my_orders = []
    if user_type == "registered":
        my_orders = utils.get_orders_by_email(session.get("email"))

    return render_template(
        "flights.html",
        flights=flights_list,
        my_orders=my_orders,
        user_type=user_type,
        email=session.get("email", "")
    )

# ==========================================
# 4. BOOKING PROCESS (The Funnel)
# ==========================================

@app.route("/book", methods=["GET", "POST"])
def book():
    """Step 1: Displays the seat map and handles seat selection."""
    if "user_type" not in session:
        return redirect("/")
    if session["user_type"] not in ("registered", "guest"):
        return redirect("/flights")

    # ---------- GET: seat selection ----------
    if request.method == "GET":
        flight_id = request.args.get("flight_id", "").strip()
        if not flight_id:
            return redirect("/flights")

        seatmap = utils.get_flight_seatmap(flight_id)
        if not seatmap:
            return render_template("message.html", title="Error", message="No seat map for this flight.",
                                   back_href="/flights")

        occupied = utils.get_occupied_seats_by_flight(flight_id)
        flight_info = utils.get_flight_info_for_summary(flight_id)

        session["booking"] = {
            "flight_id": flight_id
        }

        return render_template(
            "book_seats.html",
            flight_id=flight_id,
            seatmap=seatmap,
            occupied=occupied,
            flight_info=flight_info,
            user_type=session.get("user_type")
        )

    # ---------- POST: seats chosen ----------
    selected = request.form.getlist("seat_choice")
    booking = session.get("booking")

    if not booking:
        return redirect("/flights")

    if not selected:
        seatmap = utils.get_flight_seatmap(booking["flight_id"])
        flight_info = utils.get_flight_info_for_summary(booking["flight_id"])
        return render_template(
            "book_seats.html",
            flight_id=booking["flight_id"],
            seatmap=seatmap,
            flight_info=flight_info,
            error="Please select at least 1 seat."
        )

    # Validate seats are available
    flight_id = booking.get("flight_id")
    ok, msg = utils.validate_seats_available(flight_id, selected)

    if not ok:
        seatmap = utils.get_flight_seatmap(flight_id)
        occupied = utils.get_occupied_seats_by_flight(flight_id)
        flight_info = utils.get_flight_info_for_summary(flight_id)
        return render_template(
            "book_seats.html",
            flight_id=flight_id,
            seatmap=seatmap,
            occupied=occupied,
            flight_info=flight_info,
            user_type=session.get("user_type"),
            error=msg
        )

    # Update session with selected seats
    booking["selected_seats"] = selected
    session["booking"] = booking
    return redirect("/book_details")


@app.route("/book_details", methods=["GET", "POST"])
def book_details():
    """Step 2: Collects passenger contact details (auto-filled for registered users)."""
    # 1. Access security check
    if "user_type" not in session:
        return redirect("/")

    if session.get("user_type") == "manager":
        return redirect("/flights")

    booking = session.get("booking")
    if not booking or "flight_id" not in booking:
        return redirect("/flights")

    # PRE-FETCH: Get customer profile from DB
    customer_data = None
    if session["user_type"] == "registered":
        customer_data = utils.get_registered_customer_profile(session.get("email"))

    if request.method == "POST":

        if session.get("user_type") == "registered" and customer_data:
            first_name = customer_data["FirstName"]
            last_name = customer_data["LastName"]
            email = session.get("email")

            form_phone = request.form.get("phone", "").strip()
            phone = form_phone if form_phone else (customer_data["Phones"][0] if customer_data["Phones"] else "")

        else:
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
        # ------------------------

        # 3. Guest Identity Validation (Only for guests)
        if session["user_type"] == "guest":
            # --- CRITICAL FIX: VALIDATE ONLY, DO NOT SAVE TO DB YET ---
            # We use 'validate_guest_identity' which does SELECT only.
            # No INSERT happens here.
            is_valid, msg = utils.validate_guest_identity(email, first_name, last_name)

            if not is_valid:
                return render_template(
                    "passenger_details.html",
                    flight_id=booking["flight_id"],
                    order=booking,
                    error=msg,
                    user_type=session.get("user_type"),
                    customer=customer_data,
                    prev_data=request.form
                )

        # 4. Success: Save details into session ONLY (RAM), not DB yet.
        booking["customer"] = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phones": [phone] if phone else []
        }
        session["booking"] = booking
        return redirect("/book_summary")

    # GET method: Render the form
    return render_template(
        "passenger_details.html",
        flight_id=booking["flight_id"],
        order=booking,
        user_type=session.get("user_type"),
        customer=customer_data
    )


@app.route("/book_summary", methods=["GET", "POST"])
def book_summary():
    """Step 3: Displays final order summary and processes the payment/booking creation."""
    if "user_type" not in session:
        return redirect("/")

    if session.get("user_type") == "manager":
        return redirect("/flights")

    b = session.get("booking", {})
    flight_id = b.get("flight_id")
    selected = b.get("selected_seats")
    customer = b.get("customer")

    if not flight_id or not selected or not customer:
        return redirect("/flights")

    flight_info = utils.get_flight_info_for_summary(flight_id)
    seat_items, total_cost = utils.compute_selected_seats_cost(flight_id, selected)

    if request.method == "GET":
        return render_template(
            "book_summary.html",
            user_type=session.get("user_type"),
            flight=flight_info,
            customer=customer,
            seats=seat_items,
            total_cost=total_cost
        )

    # --- POST: FINALIZING ORDER ---

    # --- CRITICAL FIX: SAVE TO DB NOW ---
    # This is the moment the user clicked "Confirm".
    # Now we insert the guest into the database.
    if session["user_type"] == "guest":
        # Extract phone from the list in session
        phone_to_save = customer["phones"][0] if customer["phones"] else ""

        # NOW we call the function that does INSERT
        status, reg_msg = utils.register_guest_if_not_exists(
            customer["email"],
            customer["first_name"],
            customer["last_name"],
            phone_to_save
        )

        if status != "success":
            # If DB saving fails, stay on summary page and show error
            return render_template(
                "book_summary.html",
                user_type=session.get("user_type"),
                flight=flight_info,
                customer=customer,
                seats=seat_items,
                total_cost=total_cost,
                error="Registration failed: " + reg_msg
            )

    # Proceed to create the order (The guest is now guaranteed to be in the DB)
    ok, msg = utils.create_order_with_selected_seats(
        flight_id=flight_id,
        customer_type=("Registered" if session["user_type"] == "registered" else "Guest"),
        customer_email=customer["email"],
        first_name=customer["first_name"],
        last_name=customer["last_name"],
        phones=customer.get("phones", []),
        selected_seats=selected
    )

    if ok:
        try:
            order_id = ''.join(filter(str.isdigit, msg))
        except:
            order_id = "N/A"

        session.pop("booking", None)

        return render_template("book_success.html", order_id=order_id, flight_id=flight_id)

    else:
        return render_template("message.html", title="Error", message=msg, back_href="/flights")

# ==========================================
# 5. USER ORDER MANAGEMENT (My Orders & Cancel)
# ==========================================

@app.route("/my_orders", methods=["GET"])
def my_orders():
    """Displays orders for the currently logged-in registered user."""
    if session.get("user_type") != "registered":
        return redirect("/")

    email = session.get("email")

    # Get status from query string (e.g., ?status=Confirmed)
    status_filter = request.args.get("status", "").strip()

    # Pass the filter to the utility function
    orders = utils.get_registered_orders_with_flight(email, status_filter)

    for o in orders:
        o["can_cancel"] = utils.can_cancel_order_36h(o)

    return render_template(
        "registered_my_orders.html",
        orders=orders,
        email=email,
        current_status=status_filter # Pass back to template to keep dropdown selected
    )

@app.route("/registered_cancel_order", methods=["POST"])
def registered_cancel_order():
    """Handles order cancellation for registered users."""
    if session.get("user_type") != "registered":
        return redirect("/")

    email = session.get("email")
    order_id = request.form.get("order_id", "").strip()

    order = utils.get_registered_order_details(email, order_id)
    if not order:
        orders = utils.get_registered_orders_with_flight(email)
        for o in orders:
            o["can_cancel"] = utils.can_cancel_order_36h(o)
        return render_template("registered_my_orders.html", orders=orders, email=email, error="Order not found.")

    if not utils.can_cancel_order_36h(order):
        orders = utils.get_registered_orders_with_flight(email)
        for o in orders:
            o["can_cancel"] = utils.can_cancel_order_36h(o)
        return render_template("registered_my_orders.html", orders=orders, email=email,
                               error="Cancellation not allowed.")

    ok, msg = utils.cancel_registered_order_with_penalty(order_id, email)
    orders = utils.get_registered_orders_with_flight(email)
    for o in orders:
        o["can_cancel"] = utils.can_cancel_order_36h(o)

    if not ok:
        return render_template("registered_my_orders.html", orders=orders, email=email, error=msg)

    return render_template("registered_my_orders.html", orders=orders, email=email,
                           success="Cancellation completed successfully.")

@app.route("/guest_my_order", methods=["GET", "POST"])
def guest_my_order():
    """Allows guests to look up a specific order using email and order ID."""
    if session.get("user_type") != "guest":
        return redirect("/")

    if request.method == "GET":
        return render_template("guest_my_order.html")

    email = request.form.get("email", "").strip()
    order_id = request.form.get("order_id", "").strip()

    order = utils.get_guest_order_details(email, order_id)
    if not order:
        return render_template("guest_my_order.html", error="Order not found for this email.")

    seats = utils.get_order_seats(order_id)
    can_cancel = utils.can_cancel_order_36h(order)

    return render_template(
        "guest_order_details.html",
        order=order,
        seats=seats,
        can_cancel=can_cancel
    )

@app.route("/guest_cancel_order", methods=["POST"])
def guest_cancel_order():
    """Handles order cancellation for guests (checks 36h rule and applies penalty)."""
    if session.get("user_type") != "guest":
        return redirect("/")

    email = request.form.get("email", "").strip()
    order_id = request.form.get("order_id", "").strip()

    order = utils.get_guest_order_details(email, order_id)
    if not order:
        return render_template("message.html", title="Error", message="Order not found.", back_href="/guest_my_order")

    if not utils.can_cancel_order_36h(order):
        return render_template(
            "guest_order_details.html",
            order=order,
            seats=utils.get_order_seats(order_id),
            can_cancel=False,
            error_msg="Cancellation not allowed."
        )

    ok, msg = utils.cancel_guest_order_with_penalty(order_id, email)
    updated = utils.get_guest_order_details(email, order_id)
    seats = utils.get_order_seats(order_id)
    can_cancel = utils.can_cancel_order_36h(updated)

    return render_template(
        "guest_order_details.html",
        order=updated,
        seats=seats,
        can_cancel=can_cancel,
        success_msg="Cancellation completed successfully."
    )


# ==========================================
# 6. MANAGER DASHBOARD & RESOURCE MGMT
# ==========================================

@app.route("/add_plane", methods=["GET", "POST"])
def add_plane():
    """Handles adding a new aircraft with specific Economy/Business configurations."""
    if session.get("user_type") != "manager":
        return redirect("/")

    if request.method == "POST":
        # Basic Plane Info
        plane_id = request.form.get("plane_id", "").strip()
        plane_size = request.form.get("plane_size", "").strip()  # "Small" or "Large"
        manufacturer = request.form.get("manufacturer", "").strip()
        purchase_date = request.form.get("purchase_date", "").strip()

        # Seating Config
        class_config = []

        try:
            # 1. Economy (Always required)
            eco_rows = int(request.form.get("eco_rows") or 0)
            eco_cols = int(request.form.get("eco_cols") or 0)

            if eco_rows <= 0 or eco_cols <= 0:
                raise ValueError("Economy rows and columns must be greater than 0.")

            class_config.append({'type': 'Economy', 'rows': eco_rows, 'cols': eco_cols})

            # 2. Handle Business Class Inputs
            bus_rows = int(request.form.get("bus_rows") or 0)
            bus_cols = int(request.form.get("bus_cols") or 0)

            # --- Validation Logic ---

            if plane_size == "Small":
                if bus_rows > 0 or bus_cols > 0:
                    raise ValueError("Error: Small planes can ONLY have Economy class. Please clear Business fields.")

            elif plane_size == "Large":
                if bus_rows <= 0 or bus_cols <= 0:
                    raise ValueError("Error: Large planes MUST have Business class seats.")

                class_config.append({'type': 'Business', 'rows': bus_rows, 'cols': bus_cols})

        except ValueError as e:
            return render_template("add_plane.html", error=str(e))

        # Call utility function
        ok, msg = utils.add_new_plane(plane_id, plane_size, manufacturer, purchase_date, class_config)

        if ok:
            flash("Plane added successfully!", "success")
            return redirect("/flights")
        else:
            return render_template("add_plane.html", error=msg)

    return render_template("add_plane.html")

@app.route("/add_pilot", methods=["GET", "POST"])
def add_pilot():
    """Adds a new pilot to the system."""

    # Security check: Ensure only managers can access
    if session.get("user_type") != "manager":
        return redirect("/")

    if request.method == "POST":
        # Extract form data
        pilot_id = request.form.get("pilot_id", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        street = request.form.get("street", "").strip()
        house_number = request.form.get("house_number", "").strip()

        # TrainingPassed comes as "1" or "0" from the HTML select
        training_passed = request.form.get("training_passed", "0")

        # Call utility function
        ok, msg = utils.add_new_pilot(
            pilot_id, phone, first_name, last_name,
            city, street, house_number, training_passed
        )

        if ok:
            # Flash success message and redirect to flights list
            flash("Pilot added successfully!", "success")
            return redirect("/flights")
        else:
            # Stay on page and show error
            return render_template("add_pilot.html", error=msg)

    # GET request: Show the form
    return render_template("add_pilot.html")

@app.route("/add_attendant", methods=["GET", "POST"])
def add_attendant():
    """Adds a new flight attendant to the system."""

    # Security check
    if session.get("user_type") != "manager":
        return redirect("/")

    if request.method == "POST":
        # Extract form data
        attendant_id = request.form.get("attendant_id", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        street = request.form.get("street", "").strip()
        house_number = request.form.get("house_number", "").strip()
        training_passed = request.form.get("training_passed", "0")

        # Call utility function
        ok, msg = utils.add_new_attendant(
            attendant_id, phone, first_name, last_name,
            city, street, house_number, training_passed
        )

        if ok:
            flash("Flight Attendant added successfully!", "success")
            return redirect("/flights")
        else:
            return render_template("add_attendant.html", error=msg)

    return render_template("add_attendant.html")

@app.route("/crew", methods=["GET"])
def crew():
    """Displays list of all crew members with filtering capabilities."""
    if session.get("user_type") != "manager":
        return redirect("/")

    # Get filters
    role = request.args.get("role", "").strip()
    training = request.args.get("training", "").strip() # "1" or "0"
    status = request.args.get("status", "").strip()     # "Available" or "Busy"

    # Convert training to int if present
    training_val = int(training) if training in ("0", "1") else None

    # Fetch data (passing status_filter as well)
    crew_list = utils.get_all_crew(role_filter=role, training_filter=training_val, status_filter=status)

    return render_template("crew.html", crew=crew_list)

@app.route('/add_route', methods=['GET', 'POST'])
def admin_add_route():
    """Adds a new flight route (Origin -> Destination) with duration."""

    message = None
    if request.method == 'POST':
        origin = request.form.get('origin')
        destination = request.form.get('destination')
        duration = request.form.get('duration')

        # Saving to DB
        success, msg = utils.add_route_safe(origin, destination, duration)

        if success:
            # Send a success message to the next page
            flash("Success: Route added successfully!", "success")
            return redirect('/flights')
        else:
            # If failed (duplicate), stay on page and show error
            message = msg

    return render_template('add_route.html', message=message)

# ==========================================
# 7. MANAGER - FLIGHT OPERATIONS
# ==========================================

@app.route("/add_flight", methods=["GET", "POST"])
def add_flight():
    """Multi-step wizard for scheduling a new flight (Step 1: Time, Step 2: Resources)."""

    if session.get("user_type") != "manager":
        return redirect("/login_manager")

    step = request.args.get('step', '1')
    today_str = date.today().isoformat()

    if step == '1':
        routes = utils.get_all_routes()

        if request.method == "POST":
            dep_date = request.form.get("dep_date")
            dep_time = request.form.get("dep_time")

            # Validation logic
            try:
                selected_dt = datetime.strptime(f"{dep_date} {dep_time}", "%Y-%m-%d %H:%M")

                if selected_dt < datetime.now():
                    # NO REDIRECT: We render the same template with the error message
                    return render_template("add_flight_step1.html",
                                           routes=routes,
                                           min_date=today_str,
                                           error="Flight time cannot be in the past. Please select a future time.")

                # If valid, proceed to save in session and show step 2
                session['temp_flight'] = {
                    'route_id': request.form.get("route_id"),
                    'dep_date': dep_date,
                    'dep_time': dep_time
                }
                return show_step_2_template()

            except ValueError:
                return render_template("add_flight_step1.html",
                                       routes=routes,
                                       min_date=today_str,
                                       error="Invalid date or time format.")

        return render_template("add_flight_step1.html", routes=routes, min_date=today_str)

    if step == '2':
        return show_step_2_template()

def show_step_2_template(error_msg=None):
    # 1. Retrieve temp flight data from session
    temp = session.get('temp_flight')
    if not temp:
        # If session expired or direct access, go back to step 1
        return render_template("add_flight_step1.html", routes=utils.get_all_routes())

    # 2. Get route info and determine flight classification
    route_info = utils.get_route_details(temp['route_id'])
    is_long_haul = route_info['DurationHours'] > 6.0
    flight_type = "Long" if is_long_haul else "Short"

    # [CRITICAL] Extract the source airport (Where the crew AND PLANE need to be)
    source_airport = route_info['SourceAirport']

    # 3. Calculate timestamps for resource availability check
    from datetime import datetime, timedelta
    dep_dt = datetime.strptime(f"{temp['dep_date']} {temp['dep_time']}", "%Y-%m-%d %H:%M")
    arr_dt = dep_dt + timedelta(minutes=route_info['DurationMinutes'])

    # 4. Fetch available resources (Filtered by Schedule AND Location)

    eligible_planes = utils.get_eligible_planes(temp['route_id'], dep_dt, arr_dt, source_airport)

    eligible_pilots = utils.get_eligible_pilots(is_long_haul, dep_dt, arr_dt, source_airport)
    eligible_attendants = utils.get_eligible_attendants(is_long_haul, dep_dt, arr_dt, source_airport)

    context = {
        'planes': eligible_planes,
        'pilots': eligible_pilots,
        'attendants': eligible_attendants,
        'route_info': route_info,
        'flight_type': flight_type,
        'error': error_msg
    }

    # 5. Handle Form Submission (POST)
    if request.method == "POST" and request.args.get('step') == '2':

        # --- A. Validate ticket prices ---
        try:
            p_eco = float(request.form.get("price_eco", 0))
            p_bus = float(request.form.get("price_bus", 0))
            if p_eco < 0 or p_bus < 0: raise ValueError()
        except ValueError:
            context['error'] = "Please enter valid positive prices."
            return render_template("add_flight_step2.html", **context)

        # --- B. Collect plane info and its size ---
        plane_id = request.form.get("plane_id")

        # Find the full plane object from the eligible list to know its size
        selected_plane = next((p for p in eligible_planes if p['PlaneID'] == plane_id), None)

        # Guard clause: If plane is not in eligible list (e.g. hacking or stale page)
        if not selected_plane:
            context['error'] = "Selected plane is not valid or available at this location."
            return render_template("add_flight_step2.html", **context)

        plane_size = selected_plane['PlaneSize']

        # --- C. Collect submitted crew IDs ---
        selected_pilots = [request.form.get(f"pilot_{i}") for i in range(1, 4) if request.form.get(f"pilot_{i}")]
        selected_attendants = [request.form.get(f"attendant_{i}") for i in range(1, 7) if
                               request.form.get(f"attendant_{i}")]

        # --- D. Strict Validation: Crew count vs Plane Size ---
        if plane_size == 'Small':
            if len(selected_pilots) > 2 or len(selected_attendants) > 3:
                context[
                    'error'] = "For a Small plane, please assign only 2 pilots and 3 attendants. Leave extra fields empty."
                return render_template("add_flight_step2.html", **context)
            if len(selected_pilots) < 2 or len(selected_attendants) < 3:
                context['error'] = "Small planes require at least 2 pilots and 3 attendants."
                return render_template("add_flight_step2.html", **context)
        else:  # Large Plane
            if len(selected_pilots) < 3 or len(selected_attendants) < 6:
                context['error'] = "Large planes require exactly 3 pilots and 6 attendants."
                return render_template("add_flight_step2.html", **context)

        # --- E. Prevent duplicate assignments ---
        if len(selected_pilots) != len(set(selected_pilots)):
            context['error'] = "Error: You cannot assign the same pilot twice."
            return render_template("add_flight_step2.html", **context)

        if len(selected_attendants) != len(set(selected_attendants)):
            context['error'] = "Error: You cannot assign the same attendant twice."
            return render_template("add_flight_step2.html", **context)

        # --- F. Final Database/Rule validation ---
        valid, msg = utils.validate_flight_assignment(plane_id, route_info['DurationHours'], selected_pilots,
                                                      selected_attendants)
        if not valid:
            context['error'] = msg
            return render_template("add_flight_step2.html", **context)

        # --- G. Finalize and Save ---
        f_id = utils.generate_auto_flight_id()
        flight_data = {
            'flight_id': f_id, 'plane_id': plane_id, 'route_id': temp['route_id'],
            'manager_id': session.get("manager_id"), 'dep_date': dep_dt.date(),
            'dep_time': dep_dt.time(), 'arr_date': arr_dt.date(),
            'arr_time': arr_dt.time(), 'type': flight_type
        }

        ok, db_msg = utils.create_flight_full_process(flight_data, {"Economy": p_eco, "Business": p_bus},
                                                      selected_pilots, selected_attendants)

        if ok:
            session.pop('temp_flight', None)
            return render_template("flight_confirmation.html", flight=utils.get_flight_details_for_confirmation(f_id))
        else:
            context['error'] = db_msg
            return render_template("add_flight_step2.html", **context)

    return render_template("add_flight_step2.html", **context)


@app.route("/cancel_flight", methods=["GET", "POST"])
def cancel_flight():
    if session.get("user_type") != "manager":
        return redirect("/")

    # קבלת ה-ID (בין אם זה GET או POST)
    flight_id = request.args.get("flight_id", "").strip() or request.form.get("flight_id", "").strip()

    # --- התיקון: בדיקה מקדימה לפני שמציגים משהו ---
    is_eligible, msg = utils.check_cancellation_eligibility(flight_id)

    if not is_eligible:
        # אם הטיסה לא ניתנת לביטול (עבר הזמן/כבר בוטלה), נציג שגיאה ולא את דף הביטול
        return render_template("message.html", title="Cannot Cancel", message=msg, back_href="/flights")
    # -----------------------------------------------

    if request.method == "GET":
        # אם הכל תקין, מציגים את דף האישור
        return render_template("cancel_flight.html", flight_id=flight_id)

    # לוגיקה של ביצוע הביטול בפועל (POST)
    ok, cancel_msg = utils.cancel_flight_cascade(flight_id)

    if ok:
        return render_template("cancel_success.html", flight_id=flight_id)
    else:
        return render_template("message.html", title="Error", message=cancel_msg, back_href="/flights")


@app.route("/flight_confirmation/<flight_id>")
def flight_confirmation(flight_id):
    """Displays success details for a newly created flight."""
    if session.get("user_type") != "manager":
        return redirect("/login_manager")

    flight_details = utils.get_flight_details_for_confirmation(flight_id)

    if not flight_details:
        return "Flight not found", 404

    return render_template("flight_confirmation.html", flight=flight_details)

# ==========================================
# 8. ANALYTICS & REPORTS
# ==========================================

@app.route('/reports', methods=['GET', 'POST'])
def reports_page():
    """Generates and displays various statistical charts."""
    chart_image = None
    error_message = None
    selected_report = None

    if request.method == 'POST':
        selected_report = request.form.get('report_type')

        if selected_report == 'occupancy':
            chart_image, error_message = utils.generate_occupancy_chart_image()
        elif selected_report == 'revenue':
            chart_image, error_message = utils.generate_revenue_chart_image()
        elif selected_report == 'crew_hours':
            chart_image, error_message = utils.generate_crew_hours_chart_image()
        elif selected_report == 'cancellations':
            chart_image, error_message = utils.generate_cancellation_chart_image()
        elif selected_report == 'fleet_activity':
            chart_image, error_message = utils.generate_fleet_activity_chart_image()
        else:
            error_message = "Please select a valid report type."

    return render_template('reports.html',
                           chart_image=chart_image,
                           error=error_message,
                           selected_report=selected_report)


if __name__ == "__main__":
    app.run(debug=True, port=5001)