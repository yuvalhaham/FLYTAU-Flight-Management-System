# FLYTAU - Flight Scheduling and Ticketing Management System

## Project Overview
FLYTAU is an integrated information system designed to manage the comprehensive lifecycle of airline operations, flight scheduling, and customer reservations. Developed as a final project for a Database Systems Design and Information Systems Engineering course at Tel Aviv University, the platform supports three distinct user roles: guests, registered customers, and operations managers, each with different functionality and access levels.

## Technical Specifications
* Programming Language: Python 3.11
* Backend Framework: Flask
* Database Management: MySQL 
* Data Analytics: Pandas, Matplotlib, Seaborn 

## Core Features and Business Logic

### Customer Interface (Guest and Registered)
* Search and Booking Engine: Users can locate flights based on destination and schedule, utilizing a graphical interface for real-time seat selection.
* Order Management:
  * Retrieval: Guests can access booking details using their email address and unique Order ID.
  * Cancellation Policy: The system features automated refund calculations based on the time remaining until the scheduled departure.
* Member Services: Registered users benefit from a dedicated dashboard to track flight history and manage personal profile data.

### Managerial Interface (Operations and Administration)
* Flight Lifecycle Management: Tools for creating and scheduling flights with automated validation logic.
* Operational Resource Assignment:
  * Aircraft Allocation: Logic-driven assignment based on route distance and capacity requirements.
  * Crew Coordination: Real-time validation of crew availability and geographic location to ensure staff are present at the departure airport.
  * Compliance Enforcement: Strict monitoring of flight-hour limits and specific training certifications for pilots and flight attendants.
* Executive Dashboard: Generation of high-level visual reports regarding occupancy rates, revenue streams, crew workload, and fleet utilization.

## Test Credentials

**1. Operations Manager (Administrative Access):**
* ID: `111111002`
* Password: `admin2`

**2. Registered Customer (Member Access):**
* Email: `u10@fly.com`
* Password: `pass10`

---

## Project Structure

```text
FLYTAU/
├── static/                         # Static assets for the frontend
│   ├── styles.css                  # Cascading Style Sheets (Layout and Design)
│   └── flytau_logo.jpeg            # logo
│
├── templates/                      # Jinja2 HTML templates for the user interface
│   ├── add_attendant.html          # Manager: Form to add a new flight attendant to the database
│   ├── add_flight_step1.html       # Manager: Flight creation Step 1 (Select Route & Time)
│   ├── add_flight_step2.html       # Manager: Flight creation Step 2 (Assign Plane & Crew)
│   ├── add_pilot.html              # Manager: Form to add a new pilot to the database
│   ├── add_plane.html              # Manager: Form to add new aircraft and seat configurations
│   ├── add_route.html              # Manager: Form to define new flight routes (Origin/Destination)
│   ├── book_seats.html             # Customer: Interactive seat selection map
│   ├── book_success.html           # Customer: Final booking success message with Order ID
│   ├── book_summary.html           # Customer: Pre-payment review of flight and price details
│   ├── cancel_flight.html          # Manager: Interface to cancel an entire flight
│   ├── cancel_order.html           # System: Generic order cancellation confirmation page
│   ├── cancel_success.html         # System: Success message after cancelling an order or flight
│   ├── crew.html                   # Manager: Dashboard to view and filter crew availability
│   ├── flight_confirmation.html    # Manager: Success summary after scheduling a new flight
│   ├── flights.html                # Main: Search engine, flight results list, and filters
│   ├── guest_my_order.html         # Guest: Login page to retrieve an existing order
│   ├── guest_order_details.html    # Guest: View specific order details and status
│   ├── login_manager.html          # Manager: Authentication portal for admin access
│   ├── login_registered.html       # Customer: Authentication portal for registered members
│   ├── message.html                # System: Generic error or success feedback page
│   ├── order_summary.html          # Customer: Summary view of a specific order
│   ├── passenger_details.html      # Customer: Form for entering passenger contact info
│   ├── register.html               # New Customer: Account registration form
│   ├── registered_my_orders.html   # Member: List of personal booking history and actions
│   ├── reports.html                # Manager: Business Intelligence (BI) charts and analytics
│   └── welcome.html                # General: Main application landing/home page
│
├── FLYTAU_CREATE.sql               # Database setup scripts: Creates tables and relationships
├── FLYTAU_INSERT_NEW.sql           # Data Entry
├── main.py                         # Primary Flask application server and routing
└── utils.py                        # Core business logic and SQL database engine
```
