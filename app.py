from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import timedelta
from datetime import datetime,date
import qrcode
import io
import base64
import mysql.connector
import re
import os
import json
def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="car_rentals"
    )
    return conn

# Image Upload Configuration
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
BASE_DIR = os.getcwd()

PROFILE_PICTURE_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'profile_pictures')
LICENSE_IMAGE_FOLDER = 'static/uploads/license_images'
VEHICLE_PICTURE_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'vehicles')

# Ensure the directories exist
os.makedirs(PROFILE_PICTURE_FOLDER, exist_ok=True)
os.makedirs(LICENSE_IMAGE_FOLDER, exist_ok=True)
os.makedirs(VEHICLE_PICTURE_FOLDER, exist_ok=True)

def load_locations():
    with open(JSON_FILE_PATH, "r", encoding="utf-8") as file:
        locations = json.load(file)

    sorted_locations = {}
    for region_code, region in locations.items():
        sorted_provinces = sorted(region["province_list"].keys())
        sorted_province_list = {}
        for province in sorted_provinces:
            sorted_cities = sorted(region["province_list"][province]["municipality_list"].keys())
            sorted_municipality_list = {
                city: {
                    "barangay_list": sorted(region["province_list"][province]["municipality_list"][city]["barangay_list"])
                }
                for city in sorted_cities
            }
            sorted_province_list[province] = {"municipality_list": sorted_municipality_list}

        sorted_locations[region_code] = {
            "region_name": region["region_name"],
            "province_list": sorted_province_list
        }

    return sorted_locations

app = Flask(__name__)
app.secret_key = 'your_secret_key'
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'vehicles')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

JSON_FILE_PATH = os.path.join(os.getcwd(), "static", "js", "data", "philippine_provinces_cities.json")

app.secret_key = 'your_secret_key'
connected_admins = set()
def is_admin_online(admin_id):
    return admin_id in connected_admins
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
socketio = SocketIO(app)
app.secret_key = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/get_locations', methods=['GET'])
def get_locations():
    locations = load_locations()
    return jsonify(locations)

@app.route('/list_routes', methods=['GET'])
def list_routes():
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        line = urllib.parse.unquote(f"{rule.endpoint}: {rule} ({methods})")
        output.append(line)
    return "<br>".join(sorted(output))

#Admin login
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template('admin_login.html')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM admin WHERE email = %s', (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin and admin.get('password_hash'):
            try:
                if check_password_hash(admin['password_hash'].strip(), password):
                    session['admin_id'] = admin['id']
                    session['admin_name'] = admin['username']
                    session['admin_email'] = admin['email']
                    flash("Admin logged in successfully.", "success")
                    return redirect(url_for('dashboard'))
            except ValueError as e:
                flash(f"Error verifying password: {e}", "error")

        flash("Invalid email or password.", "error")

    return render_template('admin_login.html')


@app.route('/dashboard')
def dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total users
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    # Total brands
    cursor.execute("SELECT COUNT(*) AS total_brands FROM vehicle_brands")
    total_brands = cursor.fetchone()["total_brands"]

    # Total cars
    cursor.execute("SELECT COUNT(*) AS total_cars FROM vehicles")
    total_cars = cursor.fetchone()["total_cars"]

    # Available cars
    cursor.execute("SELECT COUNT(*) AS available_cars FROM vehicles WHERE status = 'available'")
    available_cars = cursor.fetchone()["available_cars"]

    # Not available cars (exclude 'booked' cars)
    cursor.execute("SELECT COUNT(*) AS not_available_cars FROM vehicles WHERE status != 'available' AND status != 'booked'")
    not_available_cars = cursor.fetchone()["not_available_cars"]

    # Booked cars
    cursor.execute("SELECT COUNT(DISTINCT model_id) AS booked_cars FROM bookings WHERE status = 'booked'")
    booked_cars = cursor.fetchone()["booked_cars"]

    # Pending bookings
    cursor.execute("SELECT COUNT(*) AS pending_bookings FROM bookings WHERE status = 'pending'")
    pending_bookings = cursor.fetchone()["pending_bookings"]

    cursor.close()
    conn.close()

    return render_template('dashboard.html', 
                           total_users=total_users,
                           total_brands=total_brands,
                           total_cars=total_cars,
                           available_cars=available_cars,
                           not_available_cars=not_available_cars,
                           booked_cars=booked_cars,
                           pending_bookings=pending_bookings)

@app.route('/manage_brands')
def manage_brands():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, brand_name FROM vehicle_brands") 
    brands = cursor.fetchall()
    cursor.close()
    return render_template("manage_brands.html", brands=brands)

@app.route('/add_brand', methods=['POST'])
def add_brand():
    brand_name = request.form['brand_name'].strip()
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Check if brand already exists
    cursor.execute("SELECT * FROM vehicle_brands WHERE brand_name = %s", (brand_name,))
    existing_brand = cursor.fetchone()

    if existing_brand:
        flash("Brand already exists!", "danger")
    else:
        # Insert brand into database (without image_url)
        cursor.execute("INSERT INTO vehicle_brands (brand_name) VALUES (%s)", (brand_name,))
        db.commit()
        flash("Brand added successfully!", "success")

    cursor.close()
    db.close()
    return redirect(url_for('manage_brands'))
@app.route('/delete_brand/<int:brand_id>', methods=['POST'])
def delete_brand(brand_id):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Delete all bookings using this brand
        cursor.execute("DELETE FROM bookings WHERE brand_id = %s", (brand_id,))
        
        # Now delete the brand
        cursor.execute("DELETE FROM vehicle_brands WHERE id = %s", (brand_id,))
        db.commit()
        flash("Brand and related bookings deleted successfully!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for('manage_brands'))


@app.route('/post_vehicle')
def post_vehicle():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT vehicles.*, vehicle_brands.brand_name 
        FROM vehicles
        JOIN vehicle_brands ON vehicles.brand_id = vehicle_brands.id
    """)
    vehicles = cursor.fetchall()
    cursor.execute('SELECT * FROM vehicle_brands') 
    brands = cursor.fetchall()
    db.close()

    return render_template('post_vehicle.html', vehicles=vehicles, brands=brands)

@app.route('/manage_vehicles')
def manage_vehicles():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""SELECT vehicles.*, vehicle_brands.brand_name FROM vehicles
        JOIN vehicle_brands ON vehicles.brand_id = vehicle_brands.id """)
    vehicles = cursor.fetchall()
    cursor.execute('SELECT * FROM vehicle_brands') 
    brands = cursor.fetchall()
    db.close()

    return render_template('manage_vehicles.html', vehicles=vehicles, brands=brands)
@app.route('/add_vehicle', methods=['GET', 'POST'])
def add_vehicle():
    if request.method == 'POST':
        brand_id = request.form.get('brand_id', '').strip()
        model = request.form.get('model', '').strip()
        transmission = request.form.get('transmission', '').strip()
        people = int(request.form.get('people', 0))  # Ensure integer
        gas = request.form.get('gas', '').strip()
        price_per_day = float(request.form.get('price_per_day', 0))  # Ensure float
        status = request.form.get('status', 'Available').strip()  # Default to 'Available'
        plate_number = request.form.get('plate_number', '').strip()
        mileage = request.form.get('mileage', '18')  # Default as number
        mileage = f"{mileage} km/l" if not mileage.endswith("km/l") else mileage

        image = request.files.get('image')
        image_filename = secure_filename(image.filename) if image else 'default.jpg'

        if image:
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vehicles (brand_id, model, transmission, people, gas, price_per_day, status, plate_number, image_url, mileage)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
            (brand_id, model, transmission, people, gas, price_per_day, status, plate_number, image_filename, mileage))

        conn.commit()
        cursor.close()
        conn.close()

        flash('Vehicle added successfully!', 'success')
        return redirect(url_for('manage_vehicles'))

    return render_template('add_vehicle.html')
@app.route('/update_vehicle/<int:vehicle_id>', methods=['POST'])
def update_vehicle(vehicle_id):
    db = get_db_connection()
    cursor = db.cursor()

    # Fetch existing data
    cursor.execute("SELECT brand_id, model, transmission, people, gas, price_per_day, status, image_url, mileage FROM vehicles WHERE id = %s", 
                   (vehicle_id,))
    existing_vehicle = cursor.fetchone()

    if not existing_vehicle:
        flash('Vehicle not found!', 'error')
        return redirect(url_for('manage_vehicles'))

    (existing_brand_id, existing_model, existing_transmission, existing_people, existing_gas,
     existing_price_per_day, existing_status, existing_image_url, existing_mileage) = existing_vehicle

    # Get new values, ensuring proper data types
    brand_id = request.form.get('brand_id', '').strip() or existing_brand_id
    model = request.form.get('model', '').strip() or existing_model
    transmission = request.form.get('transmission', '').strip() or existing_transmission
    people = int(request.form.get('people', existing_people)) if request.form.get('people') else existing_people
    gas = request.form.get('gas', '').strip() or existing_gas
    price_per_day = float(request.form.get('price_per_day', existing_price_per_day)) if request.form.get('price_per_day') else existing_price_per_day
    status = request.form.get('status', 'Available').strip() or existing_status
    mileage = request.form.get('mileage', str(existing_mileage)).strip()
    mileage = f"{mileage} km/l" if not mileage.endswith("km/l") else mileage

    valid_statuses = ['Available', 'Not Available', 'Booked','Pending']
    if status not in valid_statuses:
        flash('Invalid status!', 'error')
        return redirect(url_for('manage_vehicles'))

    new_image = request.files.get('image')
    if new_image and new_image.filename.strip():
        if existing_image_url:
            old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], existing_image_url)
            if os.path.exists(old_image_path):
                os.remove(old_image_path)  # Delete old image safely

        image_filename = secure_filename(new_image.filename)
        new_image.save(os.path.join(app.config['UPLOAD_FOLDER'], image_filename))
    else:
        image_filename = existing_image_url  # Retain old image

    cursor.execute(""" 
        UPDATE vehicles 
        SET brand_id=%s, model=%s, transmission=%s, people=%s, gas=%s, price_per_day=%s, 
            status=%s, image_url=%s, mileage=%s 
        WHERE id=%s
    """, (brand_id, model, transmission, people, gas, price_per_day, status, image_filename, mileage, vehicle_id))

    db.commit()
    cursor.close()
    db.close()

    flash('Vehicle details updated successfully!', 'success')
    return redirect(url_for('manage_vehicles'))

@app.route('/delete_vehicle/<int:vehicle_id>', methods=['POST'])
def delete_vehicle(vehicle_id):
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("SELECT image_url FROM vehicles WHERE id = %s", (vehicle_id,))
    vehicle = cursor.fetchone()

    if not vehicle:
        flash('Vehicle not found!', 'error')
        return redirect(url_for('manage_vehicles'))
    
    cursor.execute("DELETE FROM vehicles WHERE id = %s", (vehicle_id,))
    db.commit()

    image_url = vehicle[0] if isinstance(vehicle, tuple) else vehicle.get('image_url')
    if image_url:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_url)
        if os.path.exists(image_path):
            os.remove(image_path)

    cursor.close()
    db.close()
    flash('Vehicle deleted successfully!', 'success')
    return redirect(url_for('manage_vehicles'))
@app.route('/manage_bookings')
def manage_bookings():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Step 1: Auto-update bookings with return_date in the past
        cursor.execute("SELECT id, return_date, model_id FROM bookings WHERE status = 'approved'")
        approved_bookings = cursor.fetchall()

        for booking in approved_bookings:
            if booking['return_date'] and datetime.strptime(str(booking['return_date']), '%Y-%m-%d') < datetime.now():
                # Update booking to completed
                cursor.execute("UPDATE bookings SET status = 'completed' WHERE id = %s", (booking['id'],))
                # Update vehicle to available
                cursor.execute("UPDATE vehicles SET status = 'Available', availability = 'yes' WHERE id = %s", (booking['model_id'],))

        db.commit()

        cursor.execute("""SELECT bookings.id, bookings.status, bookings.start_date, bookings.return_date,bookings.price_per_day, 
        bookings.discount_percentage, bookings.discounted_price,bookings.payment_method,bookings.payment_status,bookings.payment_date,
        users.lastname, users.email, users.phone, users.province, users.city, users.barangay, vehicle_brands.brand_name, vehicles.model AS model_name
        FROM bookings
        JOIN users ON bookings.user_id = users.id
        JOIN vehicle_brands ON bookings.brand_id = vehicle_brands.id
        JOIN vehicles ON bookings.model_id = vehicles.id; """)
        bookings = cursor.fetchall()

    except Exception as e:
        db.rollback()
        flash(f"Error during auto-update: {e}", "danger")
        bookings = []

    finally:
        cursor.close()
        db.close()

    return render_template('manage_bookings.html', bookings=bookings)
@app.route('/fill_up_booking/<int:vehicles_id>', methods=['GET', 'POST'])
def fill_up_booking(vehicles_id):
    if 'user_id' not in session:
        flash("Please login first.", "error")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Retrieve vehicle details
    cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vehicles_id,))
    vehicle = cursor.fetchone()

    # Retrieve user details
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()

    if not vehicle or not user:
        flash("Invalid vehicle or user.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('deals'))

    # Retrieve the user's discount percentage
    discount_percentage = user.get('discount_percentage', 0)

    # Calculate the discounted price
    price_per_day = int(vehicle['price_per_day'])
    discounted_price = price_per_day - (price_per_day * discount_percentage // 100)

    cursor.close()
    conn.close()

    return render_template(
        "booking_fillup.html", 
        vehicle=vehicle, 
        user=user, 
        date=date, 
        discount_percentage=discount_percentage,  
        discounted_price=discounted_price
    )

@app.route('/process_booking_payment/<int:vehicles_id>', methods=['POST'])
def process_booking_payment(vehicles_id):
    if 'user_id' not in session:
        flash("Please log in to process payment.", "danger")
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        today = date.today()
        last_day_of_month = today.replace(day=28) + timedelta(days=4)
        last_day_of_month -= timedelta(days=last_day_of_month.day)

        # Get vehicle
        cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vehicles_id,))
        vehicle = cursor.fetchone()
        if not vehicle:
            flash("Vehicle not found!", "danger")
            return redirect(url_for('deals'))

        # Get user discount
        cursor.execute("SELECT discount_percentage FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        discount = int(user['discount_percentage']) if user and user['discount_percentage'] else 0

        price_per_day = int(vehicle['price_per_day'])
        discounted_price = price_per_day - (price_per_day * discount // 100)

        # Insert booking
        cursor.execute("""
            INSERT INTO bookings (
                user_id, brand_id, model_id, status, start_date, return_date,
                price_per_day, discount_percentage, discounted_price,
                payment_method, payment_status, payment_date
            )
            VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (
            user_id, vehicle['brand_id'], vehicles_id,
            today, last_day_of_month,
            price_per_day, discount, discounted_price,
            'gcash', 'paid'
        ))
        booking_id = cursor.lastrowid  # Get the ID of the new booking

        # Update vehicle status
        cursor.execute("""
            UPDATE vehicles 
            SET status = 'booked', availability = 'no' 
            WHERE id = %s
        """, (vehicles_id,))

        conn.commit()

        flash("Booking successful and payment processed! Your vehicle is now booked.", "success")
        return redirect(url_for('booking_confirmation', booking_id=booking_id))

    except Exception as e:
        print(f"Error while processing booking and payment: {e}")
        flash("An error occurred. Please try again later.", "danger")
        return redirect(url_for('deals'))

    finally:
        cursor.close()
        conn.close()
@app.route('/booking_confirmation/<int:booking_id>')
def booking_confirmation(booking_id):
    if 'user_id' not in session:
        flash("Please log in to view your booking confirmation.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get booking and vehicle info
        cursor.execute("""
            SELECT b.*, v.model AS vehicle_name, v.brand_id
            FROM bookings b
            JOIN vehicles v ON b.model_id = v.id
            WHERE b.id = %s AND b.user_id = %s
        """, (booking_id, session['user_id']))
        booking = cursor.fetchone()

        if not booking:
            flash("Booking not found.", "danger")
            return redirect(url_for('deals'))

        # QR code content (can be simplified or expanded)
        qr_data = f"""
        Booking ID: {booking['id']}
        Vehicle: {booking['vehicle_name']}
        Start Date: {booking['start_date']}
        Return Date: {booking['return_date']}
        Discounted Price: ₱{booking['discounted_price']}
        Discount: {booking['discount_percentage']}%
        """

        # Generate QR code
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(qr_data.strip())
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Pass to template
        qr_info = {
            'vehicle': booking['vehicle_name'],
            'start_date': booking['start_date'],
            'return_date': booking['return_date'],
            'discounted_price': booking['discounted_price'],
            'discount': booking['discount_percentage'],
            'qr_code': img_b64
        }

        return render_template("booking_confirmation.html", qr=qr_info)

    except Exception as e:
        print("Error loading confirmation:", e)
        flash("Error displaying booking confirmation.", "danger")
        return redirect(url_for('deals'))

    finally:
        cursor.close()
        conn.close()

@app.route('/add_booking/<int:vehicles_id>', methods=['GET', 'POST'])
def add_booking(vehicles_id):
    if 'user_id' not in session:
        flash("Please login to book a vehicle.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session['user_id']
        today = date.today()
        last_day_of_month = today.replace(day=28) + timedelta(days=4)
        last_day_of_month -= timedelta(days=last_day_of_month.day)

        # Get user's discount
        cursor.execute("SELECT discount_percentage FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        discount = int(user['discount_percentage']) if user and user['discount_percentage'] else 0

        # Get vehicle details
        cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vehicles_id,))
        vehicles = cursor.fetchone()

        if not vehicles:
            flash("Vehicle not found!", "danger")
            return redirect(url_for('deals'))

        price_per_day = int(vehicles['price_per_day'])
        discounted_price = price_per_day - (price_per_day * discount // 100)

        # Check for existing booking
        cursor.execute("""
            SELECT * FROM bookings 
            WHERE user_id = %s AND model_id = %s AND status IN ('pending', 'booked')
            ORDER BY id DESC LIMIT 1
        """, (user_id, vehicles_id))
        booking = cursor.fetchone()

        show_early_return = False
        show_cancel_booking = False

        if booking:
            if booking['status'] == 'booked':
                show_early_return = True
            elif booking['status'] == 'pending':
                show_cancel_booking = True

            if request.method == 'POST':
                if 'early_return_date' in request.form and show_early_return:
                    new_return_date = request.form['early_return_date']
                    new_return_date_obj = datetime.strptime(new_return_date, '%Y-%m-%d').date()

                    if today <= new_return_date_obj < booking['return_date']:
                        cursor.execute("""
                            UPDATE bookings 
                            SET return_date = %s, status = 'returned' 
                            WHERE id = %s
                        """, (new_return_date, booking['id']))
                        cursor.execute("""
                            UPDATE vehicles 
                            SET status = 'available', availability = 'yes' 
                            WHERE id = %s
                        """, (vehicles_id,))
                        conn.commit()
                        flash(f"Your vehicle has been returned early! New return date is {new_return_date}.", "success")
                        return redirect(url_for('deals'))
                    else:
                        flash("The early return date must be earlier than the original return date.", "danger")

                elif 'cancel_booking' in request.form and show_cancel_booking:
                    cursor.execute("""
                        UPDATE bookings 
                        SET status = 'cancelled' 
                        WHERE id = %s
                    """, (booking['id'],))
                    cursor.execute("""
                        UPDATE vehicles 
                        SET status = 'available', availability = 'yes' 
                        WHERE id = %s
                    """, (vehicles_id,))
                    conn.commit()
                    flash("Your pending booking has been cancelled.", "success")
                    return redirect(url_for('add_booking', vehicles_id=vehicles_id))

        # Handle new booking request (only allowed if no existing active booking)
        if request.method == 'POST' and 'start_date' in request.form and not booking:
            start_date = request.form['start_date']
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()

            if start_date_obj < today or start_date_obj > last_day_of_month:
                flash("Start date must be within this month.", "danger")
                return redirect(url_for('add_booking', vehicles_id=vehicles_id))

            # Adjust return date to the next day based on the start date
            return_date_obj = start_date_obj + timedelta(days=1)

            if return_date_obj > last_day_of_month:
                flash("Return date exceeds the allowed range.", "danger")
                return redirect(url_for('add_booking', vehicles_id=vehicles_id))

            return_date = return_date_obj.strftime('%Y-%m-%d')

            cursor.execute("""
                INSERT INTO bookings 
                (user_id, brand_id, model_id, status, start_date, return_date, 
                 price_per_day, discount_percentage, discounted_price, 
                 payment_method, payment_status, payment_date)
                VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                user_id, vehicles['brand_id'], vehicles_id,
                start_date, return_date,
                price_per_day, discount, discounted_price,
                'cash on cashier', 'pending'
            ))

            cursor.execute("""
                UPDATE vehicles 
                SET status = 'pending', availability = 'no' 
                WHERE id = %s
            """, (vehicles_id,))

            conn.commit()
            flash(f"Booking successful! Return is due on {return_date}. Discounted price: ₱{discounted_price}", "success")
            return redirect(url_for('deals'))

        return render_template("add_booking.html",
                               vehicles=vehicles,
                               today=today,
                               last_day_of_month=last_day_of_month,
                               booking=booking,
                               discount=discount,
                               price_per_day=price_per_day,
                               discounted_price=discounted_price,
                               show_early_return=show_early_return,
                               show_cancel_booking=show_cancel_booking)

    except Exception as e:
        app.logger.error(f"Error in add_booking: {e}")
        flash("An unexpected error occurred. Please try again later.", "danger")

    finally:
        cursor.close()
        conn.close()

@app.route('/cancel_pending/<int:pending_id>', methods=['POST'])
def cancel_pending(pending_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get the form data
        return_date = request.form.get('return_date')
        
        # If a return date is provided, update the booking with it
        if return_date:
            cursor.execute("""
                UPDATE bookings 
                SET status = 'cancelled', 
                    return_date = %s
                WHERE id = %s
            """, (return_date, pending_id))

            # Update the vehicle status to 'available' again
            cursor.execute("""
                UPDATE vehicles 
                SET status = 'available', 
                    availability = 'yes' 
                WHERE id = (SELECT model_id FROM bookings WHERE id = %s)
            """, (pending_id,))

            conn.commit()

            flash(f"Booking cancelled successfully. Return Date: {return_date}. Vehicle is now available.", "success")
        else:
            flash("Return date is required to cancel the booking.", "danger")

    except Exception as e:
        app.logger.error(f"Error in cancel_pending: {e}")
        flash("An error occurred while processing your request. Please try again.", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('deals'))
@app.route('/early_return/<int:booking_id>', methods=['POST'])
def early_return(booking_id):
    if 'user_id' not in session:
        flash("Please login to return a vehicle.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        user_id = session['user_id']
        today = date.today()

        # Fetch the booking
        cursor.execute("""
            SELECT * FROM bookings WHERE id = %s AND user_id = %s
        """, (booking_id, user_id))
        booking = cursor.fetchone()

        if not booking:
            flash("Booking not found or you do not have permission to modify it.", "danger")
            return redirect(url_for('deals'))

        # Check if the booking status is 'booked' and can be returned early
        if booking['status'] == 'booked':
            new_return_date = request.form['new_return_date']
            new_return_date_obj = datetime.strptime(new_return_date, '%Y-%m-%d').date()

            if new_return_date_obj >= today and new_return_date_obj < booking['return_date']:
                # Update the booking with the new early return date
                cursor.execute("""
                    UPDATE bookings 
                    SET return_date = %s, status = 'returned' 
                    WHERE id = %s
                """, (new_return_date, booking['id']))

                # Update the vehicle status
                cursor.execute("""
                    UPDATE vehicles 
                    SET status = 'available', availability = 'yes' 
                    WHERE id = %s
                """, (booking['model_id'],))

                conn.commit()
                flash(f"Your vehicle has been returned early! New return date is {new_return_date}.", "success")
            else:
                flash("The early return date must be earlier than the original return date.", "danger")
        else:
            flash("Booking is not in 'booked' status.", "danger")

        return redirect(url_for('deals'))

    except Exception as e:
        app.logger.error(f"Error in early_return: {e}")
        flash("An unexpected error occurred. Please try again later.", "danger")
        return redirect(url_for('deals'))

    finally:
        cursor.close()
        conn.close()


@app.route('/update_booking/<int:booking_id>', methods=['POST'])
def update_booking(booking_id):
    # Ensure that the admin is logged in
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    # Get the new status from the form
    new_status = request.form.get('status', 'Pending')

    # Validate the new status
    valid_statuses = ['Pending', 'Booked', 'Completed', 'Cancelled']
    if new_status not in valid_statuses:
        flash('Invalid booking status!', 'error')
        return redirect(url_for('manage_bookings'))

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get the vehicle id (model_id) from the booking
        cursor.execute("SELECT model_id FROM bookings WHERE id = %s", (booking_id,))
        booking = cursor.fetchone()

        # Check if the booking exists
        if not booking:
            flash("Booking not found!", "danger")
            return redirect(url_for('manage_bookings'))

        # Update the booking status
        cursor.execute("UPDATE bookings SET status = %s WHERE id = %s", (new_status, booking_id))

        # Update the vehicle status and availability based on the new booking status
        if new_status == 'Booked':
            cursor.execute("UPDATE vehicles SET status = 'Booked', availability = 'no' WHERE id = %s", (booking['model_id'],))
        elif new_status == 'Completed':
            cursor.execute("UPDATE vehicles SET status = 'Available', availability = 'yes' WHERE id = %s", (booking['model_id'],))
        elif new_status == 'Cancelled':
            cursor.execute("UPDATE vehicles SET status = 'Available', availability = 'yes' WHERE id = %s", (booking['model_id'],))

        # Commit the changes
        conn.commit()
        flash('Booking status updated successfully!', 'success')

    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error updating booking {booking_id}: {e}")
        flash("An unexpected error occurred. Please try again later.", "danger")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('manage_bookings'))

@app.route('/approve_booking/<int:booking_id>', methods=['POST'])
def approve_booking(booking_id):
    # Ensure that the admin is logged in
    if 'admin_id' not in session:
        flash("Please log in as an admin to approve bookings.", "danger")
        return redirect(url_for('admin_login'))

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch the booking details
        cursor.execute("SELECT id, model_id FROM bookings WHERE id = %s AND status = 'Pending'", (booking_id,))
        booking = cursor.fetchone()

        # Check if the booking exists
        if not booking:
            flash("Booking not found or is not pending approval.", "danger")
            return redirect(url_for('manage_bookings'))

        # Update the booking status to 'Booked'
        cursor.execute("UPDATE bookings SET status = 'Booked' WHERE id = %s", (booking_id,))

        # Update the vehicle status to 'Booked'
        cursor.execute("UPDATE vehicles SET status = 'Booked', availability = 'no' WHERE id = %s", (booking['model_id'],))

        # Commit the changes
        conn.commit()
        flash("Booking approved successfully! The vehicle is now booked.", "success")

    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error approving booking {booking_id}: {e}")
        flash("An unexpected error occurred. Please try again later.", "danger")

    finally:
        cursor.close()
        conn.close()

    # Redirect to the manage bookings page
    return redirect(url_for('manage_bookings'))

@app.route('/update_booking_status/<int:booking_id>', methods=['POST'])
def update_booking_status(booking_id):
    # Ensure the admin is logged in
    if 'admin_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    # Parse the new status from the request
    data = request.get_json()
    new_status = data.get('status')

    # Validate the new status
    valid_statuses = ['approved', 'returned', 'pending']
    if new_status not in valid_statuses:
        return jsonify({"success": False, "message": "Invalid status"}), 400

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch the booking details
        cursor.execute("SELECT id, model_id FROM bookings WHERE id = %s", (booking_id,))
        booking = cursor.fetchone()

        # Check if the booking exists
        if not booking:
            return jsonify({"success": False, "message": "Booking not found"}), 404

        # Update the booking status
        cursor.execute("UPDATE bookings SET status = %s WHERE id = %s", (new_status.capitalize(), booking_id))

        # Update the vehicle status based on the new booking status
        if new_status == 'approved':
            cursor.execute("UPDATE vehicles SET status = 'Booked', availability = 'no' WHERE id = %s", (booking['model_id'],))
        elif new_status == 'returned':
            cursor.execute("UPDATE vehicles SET status = 'Available', availability = 'yes' WHERE id = %s", (booking['model_id'],))

        # Commit the changes
        conn.commit()
        return jsonify({"success": True, "message": f"Booking status updated to {new_status.capitalize()}."})

    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error updating booking status for booking {booking_id}: {e}")
        return jsonify({"success": False, "message": "An error occurred while updating the booking status."}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/manage_testimonials')
def manage_testimonials():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT t.*, u.lastname, 
                   COALESCE((SELECT AVG(t2.average_rating) 
                             FROM testimonials t2 
                             WHERE t2.model_id = t.model_id), 0) AS average_rating
            FROM testimonials t
            JOIN users u ON t.user_id = u.id
            ORDER BY t.id DESC
        """)

        testimonials = cursor.fetchall()
        return render_template('manage_testimonials.html', testimonials=testimonials)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('home'))

    finally:
        cursor.close()
        conn.close()
@app.route('/view_vehicle/<int:vehicle_id>', methods=['GET'])
def view_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, model, brand_id, transmission, people, gas, 
                   price_per_day, status, plate_number, mileage, image_url
            FROM vehicles WHERE id = %s
        """, (vehicle_id,))
        vehicle = cursor.fetchone()

        cursor.execute("""
            SELECT t.id, t.user_id, t.model_id, t.comment_text, t.created_at, 
                   t.average_rating, u.lastname, u.profile_picture
            FROM testimonials t
            JOIN users u ON t.user_id = u.id
            WHERE t.model_id = %s
            ORDER BY t.created_at DESC
        """, (vehicle_id,))
        testimonials = cursor.fetchall()

    except Exception as e:
        app.logger.error(f"🔥 Error fetching data: {e}")
        flash("An error occurred while fetching vehicle details.", "danger")
        return redirect(url_for('home'))

    finally:
        cursor.close()
        conn.close()

    if not vehicle:
        flash("Vehicle not found.", "danger")
        return redirect(url_for('home'))

    return render_template('view_vehicle.html', vehicle=vehicle, testimonials=testimonials)
@app.route('/add_testimonial/<int:vehicles_id>', methods=['POST'])
def add_testimonial(vehicles_id):
    if 'user_id' not in session:
        flash("Please login to leave a testimonial.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    comment_text = request.form.get('comment_text')
    rating = request.form.get('rating')

    try:
        # Debug: Confirm data received
        print("Comment:", comment_text)
        print("Rating:", rating)

        # Get vehicle details
        cursor.execute("""
            SELECT v.*, b.brand_name AS brand_name
            FROM vehicles v
            JOIN vehicle_brands b ON v.brand_id = b.id
            WHERE v.id = %s
        """, (vehicles_id,))
        vehicle = cursor.fetchone()
        if not vehicle:
            flash("Vehicle not found.", "danger")
            return redirect(url_for('home'))

        # Ensure we clear previous result
        cursor.fetchall()  # Clear any pending results

        # Check if the vehicle has been booked and returned by the user
        cursor.execute("""
            SELECT b.status, b.return_date
            FROM bookings b
            WHERE b.model_id = %s AND b.user_id = %s AND b.status = 'returned' AND b.return_date IS NOT NULL
        """, (vehicles_id, session['user_id']))
        booking = cursor.fetchone()
        
        # If no booking or the vehicle has not been returned, redirect to add_booking page
        if not booking:
            flash("You can leave a add booking only after returning the vehicle.", "danger")
            # Redirect to add_booking page, using correct parameter name
            return redirect(url_for('add_booking', vehicles_id=vehicles_id))

        # Ensure we clear previous result
        cursor.fetchall()  # Clear any pending results

        # Check if user already submitted a testimonial for this vehicle
        cursor.execute("""
            SELECT t.* 
            FROM testimonials t 
            WHERE t.user_id = %s AND t.model_id = %s
        """, (session['user_id'], vehicles_id))
        if cursor.fetchone():
            flash("You have already submitted a testimonial for this vehicle.", "danger")
            return redirect(url_for('view_vehicle', vehicle_id=vehicles_id))

        # Ensure we clear previous result
        cursor.fetchall()  # Clear any pending results

        # Get user details
        cursor.execute("SELECT lastname, discount_percentage FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()

        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('home'))

        lastname = user['lastname']
        discount = user['discount_percentage'] or 0

        # Ensure rating is numeric
        try:
            rating = float(rating) if rating else 0
        except (TypeError, ValueError):
            rating = 0

        # Insert testimonial
        cursor.execute("""
            INSERT INTO testimonials (model_id, user_id, comment_text, average_rating, created_at, lastname)
            VALUES (%s, %s, %s, %s, NOW(), %s)
        """, (vehicles_id, session['user_id'], comment_text, rating, lastname))
        conn.commit()

        flash("Testimonial submitted successfully!", "success")

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('home'))

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('view_vehicle', vehicle_id=vehicles_id))

@app.route('/edit_testimonial/<int:testimonial_id>', methods=['POST'])
def edit_testimonial(testimonial_id):
    if 'user_id' not in session:
        flash("Please login to edit your testimonial.", "danger")
        return redirect(url_for('login'))

    comment_text = request.form.get('comment_text')
    average_rating = request.form.get('average_rating')

    if not comment_text or not average_rating:
        flash("Comment and rating are required.", "danger")
        return redirect(request.referrer or url_for('home'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Check ownership
        cursor.execute("SELECT * FROM testimonials WHERE id = %s AND user_id = %s", 
                       (testimonial_id, session['user_id']))
        testimonial = cursor.fetchone()

        if not testimonial:
            flash("You don't have permission to edit this testimonial.", "danger")
            return redirect(url_for('home'))

        rating = float(average_rating)

        cursor.execute("""
            UPDATE testimonials
            SET comment_text = %s, average_rating = %s
            WHERE id = %s
        """, (comment_text, rating, testimonial_id))
        conn.commit()

        flash("Testimonial updated successfully!", "success")
        return redirect(url_for('view_vehicle', vehicle_id=testimonial['model_id']))

    except Exception as e:
        flash(f"An error occurred while updating: {str(e)}", "danger")
        return redirect(url_for('home'))

    finally:
        cursor.close()
        conn.close()
@app.route('/delete_testimonial/<int:testimonial_id>', methods=['POST'])
def delete_testimonial(testimonial_id):
    if 'user_id' not in session:
        flash("Please login to delete your testimonial.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM testimonials WHERE id = %s AND user_id = %s", 
                       (testimonial_id, session['user_id']))
        testimonial = cursor.fetchone()

        if not testimonial:
            flash("Testimonial not found or you don't have permission to delete it.", "danger")
            return redirect(url_for('home'))

        cursor.execute("DELETE FROM testimonials WHERE id = %s", (testimonial_id,))
        conn.commit()

        flash("Testimonial deleted successfully!", "success")
        return redirect(url_for('view_vehicle', vehicle_id=testimonial['model_id']))

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('home'))

    finally:
        cursor.close()
        conn.close()
@app.route('/admin/delete_testimonial/<int:testimonial_id>', methods=['POST'])
def admin_delete_testimonial(testimonial_id):
    # Optional: Check if current session is admin
    if 'admin_id' not in session:
        return "Unauthorized", 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("DELETE FROM testimonials WHERE id = %s", (testimonial_id,))
        conn.commit()
        return '', 204  # AJAX success response

    except Exception as e:
        return f"Error: {str(e)}", 500

    finally:
        cursor.close()
        conn.close()
@app.route('/manage_queries')
def manage_queries():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT id, email FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()

    cursor.close()
    return render_template('manage_queries.html', users=users)

@socketio.on('typing')
def handle_typing(data):
    emit('typing', {'sender': data['sender'], 'typing': data.get('typing', True)}, broadcast=True)

@socketio.on('connect')
def handle_connect():
    user_id = session.get('user_id')
    admin_id = session.get('admin_id')
    email = session.get('email')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if user_id and not email:
        # Get user email
        cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            session['email'] = result['email']

        # Assign admin if not yet assigned
        if not admin_id:
            cursor.execute("SELECT id FROM admin ORDER BY RAND() LIMIT 1")
            admin = cursor.fetchone()
            if admin:
                session['admin_id'] = admin['id']
                admin_id = admin['id']

        room_id = f"chat_{user_id}_{admin_id}"
        join_room(room_id)

        # Check if this user has any previous messages
        cursor.execute(
            "SELECT COUNT(*) AS message_count FROM messages WHERE user_id = %s AND admin_id = %s",
            (user_id, admin_id)
        )
        message_count = cursor.fetchone()['message_count']

        if message_count == 0:
            welcome_msg = "Welcome to the chat! How can I assist you?"
        else:
            welcome_msg = "Welcome to the chat! How can I assist you?"

        emit('message', {'sender': 'admin', 'text': welcome_msg}, room=room_id)

    elif admin_id and not email:
        # Get admin email
        cursor.execute("SELECT email FROM admin WHERE id = %s", (admin_id,))
        result = cursor.fetchone()
        if result:
            session['email'] = result['email']

        room_id = f"chat_{user_id}_{admin_id}" if user_id else f"admin_{admin_id}"
        join_room(room_id)

        emit('message', {'sender': 'admin', 'text': 'Welcome back, admin!'}, room=room_id)

    cursor.close()

# user chat box to admin
@app.route('/chat')
def chat():
    user_id = session.get('user_id')
    admin_id = 1  # Or fetch dynamically if needed

    if not user_id:
        return "User not logged in", 403

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        return "User not found", 404

    # Fetch previous messages between user and assigned admin
    cursor.execute("""
        SELECT * FROM messages
        WHERE (user_id = %s AND admin_id = %s) OR (user_id = %s AND admin_id = %s)
        ORDER BY created_at ASC
    """, (user_id, admin_id, user_id, admin_id))
    messages = cursor.fetchall()

    return render_template(
        'chat.html',
        user_id=user_id,
        admin_id=admin_id,
        user_email=user['email'],
        messages=messages  # Pass the fetched messages to the template
    )

#admin chat box to user
@app.route('/admin/chat/<user_email>')
def admin_chat(user_email):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get user by email
    cursor.execute("SELECT id, email FROM users WHERE email = %s", (user_email,))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        return "User not found", 404

    user_id = user['id']
    admin_id = session['admin_id']

    # Fetch messages between admin and this user
    cursor.execute("""
    SELECT * FROM messages
    WHERE (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
    ORDER BY created_at ASC
""", (user_id, admin_id, admin_id, user_id))
    messages = cursor.fetchall()
    cursor.close()

    return render_template(
        'admin_chat.html',
        user_id=user_id,
        admin_id=admin_id,
        user_email=user['email'],
        admin_email='admin@gmail.com',  # Replace with dynamic admin email if needed
        messages=messages
    )
@socketio.on('private_message')
def handle_private_message(data):
    if 'room' not in data or 'text' not in data or 'user_id' not in data:
        print("❌ Error: Missing required data fields.")
        return

    user_id_raw = data['user_id']
    if not user_id_raw or not str(user_id_raw).isdigit():
        print(f"❌ Error: Invalid user_id received -> {user_id_raw}")
        return

    user_id = int(user_id_raw)
    text = data['text']
    room = data['room']
    sender = data['sender']  # 'admin' or 'user'
    admin_id = room.split("_")[1]

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # 🟡 Check if user exists
        cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone()

        if not user_row:
            print(f"❌ Error: No user found with ID {user_id}")
            return

        user_email = user_row['email']
        admin_email = 'admin@gmail.com'

        if sender == 'admin':
            sender_email = admin_email
            receiver_email = user_email
            receiver = 'user'
        else:
            sender_email = user_email
            receiver_email = admin_email
            receiver = 'admin'

        cursor.execute("""
            INSERT INTO messages (user_id, admin_id, email, sender, message, receiver, receiver_type, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, admin_id, sender_email, sender, text, receiver_email, receiver))
        db.commit()

        # Emit message to the room
        emit('private_message', {
            'sender': sender,
            'text': text,
            'email': sender_email
        }, room=room)

    except Exception as e:
        print(f"⚠️ Exception in handle_private_message: {e}")
    finally:
        cursor.close()
        db.close()

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    user_id = request.form.get('target_user_id')
    message = request.form.get('message')

    if not user_id or not message:
        flash('User ID and message are required.', 'danger')
        return redirect(url_for('dashboard'))

    admin_id = session['admin_id']
    admin_email = session.get('admin_email')  # Dynamically retrieve admin's email from session

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Get user's email
    cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        flash('User not found.', 'danger')
        return redirect(url_for('dashboard'))

    user_email = user['email']

    # ✅ INSERT message with admin email
    cursor.execute("""
        INSERT INTO messages (user_id, admin_id, email, sender, message, receiver, receiver_type, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    """, (user_id, admin_id, admin_email, 'admin', message, user_email, 'user'))

    db.commit()
    cursor.close()

    # Send message to user without duplicating it via socket emission
    flash('Message sent!', 'success')
    return redirect(url_for('admin_chat', user_email=user_email))

@app.route('/manage_users')
def manage_users():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.close()
    return render_template('manage_users.html', users=users)
@app.route("/view_user/<int:user_id>")
def view_user(user_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))  # Ensure admin login page

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, firstname, lastname, email, phone, province, city, barangay, user_type,
               profile_picture, license_image, created_at, updated_at, birthday 
        FROM users WHERE id = %s
        """,
        (user_id,),
    )
    user = cursor.fetchone()

    cursor.close()
    db.close()

    if not user:
        flash("User not found!", "error")
        return redirect(url_for("manage_users"))

    # Debug: Print the birthday value
    print(f"Birthday value from database: {user['birthday']}")

    # Debug: Print the type of 'birthday'
    print(f"Birthday type: {type(user['birthday'])}")

    # Calculate age from birthday
    if user['birthday']:
        today = datetime.today().date()
        birthday = user['birthday']  # It's already a datetime.date object

        # Calculate the age
        age = today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))
        user['age'] = age
    else:
        user['age'] = None

    return render_template("view_user.html", user=user)

@app.route('/update_user/<int:user_id>', methods=['GET', 'POST'])
def update_user(user_id):
    if 'admin_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        email = request.form['email']
        phone = request.form['phone']
        province = request.form['province']
        city = request.form['city']
        barangay = request.form['barangay']
        birthday = request.form['birthday']

        # Fetch existing user data
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        # Default to existing images
        profile_picture_relative_path = user['profile_picture']
        license_image_relative_path = user['license_image']

        # Handle profile picture upload
        if 'profile_picture' in request.files:
            profile_picture = request.files['profile_picture']
            if profile_picture and profile_picture.filename != '':
                profile_filename = secure_filename(profile_picture.filename)
                profile_picture_path = os.path.join(PROFILE_PICTURE_FOLDER, profile_filename)
                profile_picture.save(profile_picture_path)
                profile_picture_relative_path = f"uploads/profile_pictures/{profile_filename}"

        # Handle license image upload
        if 'license_image' in request.files:
            license_image = request.files['license_image']
            if license_image and license_image.filename != '':
                license_filename = secure_filename(license_image.filename)
                license_image_path = os.path.join(LICENSE_IMAGE_FOLDER, license_filename)
                license_image.save(license_image_path)
                license_image_relative_path = f"uploads/license_images/{license_filename}"
        # Update user info
        cursor.execute("""
            UPDATE users 
            SET firstname=%s, lastname=%s, email=%s, phone=%s, province=%s, city=%s, barangay=%s, 
                birthday=%s, profile_picture=%s, license_image=%s 
            WHERE id=%s
        """, (firstname, lastname, email, phone, province, city, barangay, birthday,
              profile_picture_relative_path, license_image_relative_path, user_id))

        db.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('view_user', user_id=user_id))

    # GET request: populate form
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    db.close()

    return render_template('update_user.html', user=user)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Perform delete action after confirmation
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()
    cursor.close()

    flash("User deleted successfully!", "success")
    return redirect(url_for('manage_users'))
@app.route('/manage_subscribers')
def manage_subscribers():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            u.email,
            up.id AS payment_id,
            up.payment_method,
            up.amount,
            up.status,
            up.duration,
            up.created_at
        FROM user_payments up
        JOIN users u ON up.user_id = u.id
        ORDER BY up.created_at DESC
    """)
    
    subscribers = cursor.fetchall()
    cursor.close()
    db.close()

    # Compute subscription expiry manually
    for s in subscribers:
        created_at = s['created_at']
        duration = s['duration']
        s['subscription_expiry'] = (created_at + timedelta(days=30 * duration)).strftime('%Y-%m-%d')

    return render_template('manage_subscribers.html', subscribers=subscribers)
@app.route('/approve_payment/<int:payment_id>', methods=['GET'])
def approve_payment(payment_id):
    # Ensure the user is an admin
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Check if the payment is pending
        cursor.execute("""
            SELECT * FROM user_payments
            WHERE id = %s AND status = 'pending'
        """, (payment_id,))
        payment = cursor.fetchone()

        if not payment:
            flash('Payment not found or already approved.', 'info')
            return redirect(url_for('manage_subscribers'))

        # Extract payment details
        user_id = payment['user_id']
        amount = payment['amount']
        duration = payment['duration']
        discount = 20 if duration >= 6 else 10

        # Approve the payment
        cursor.execute("""
            UPDATE user_payments 
            SET status = 'approved' 
            WHERE id = %s
        """, (payment_id,))

        # Check if subscription_expiry column exists in the 'users' table
        cursor.execute("SHOW COLUMNS FROM users LIKE 'subscription_expiry'")
        column_exists = cursor.fetchone()
        if not column_exists:
            flash('The subscription expiry column is missing in the users table.', 'danger')
            return redirect(url_for('manage_subscribers'))

        # Apply the discount and update subscription expiry
        cursor.execute("""
            UPDATE users 
            SET discount_percentage = %s,
                subscription_expiry = DATE_ADD(NOW(), INTERVAL %s MONTH)
            WHERE id = %s
        """, (discount, duration, user_id))

        # Generate QR Code
        qr_data = f"User ID: {user_id}, Plan: {duration} months, Amount: ₱{amount}, Discount: {discount}%"
        qr_img = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        # Store QR details in session
        session['show_qr'] = {
            'plan_duration': duration,
            'amount': amount,
            'discount': discount,
            'qr_code': qr_b64
        }

        db.commit()

        flash('Payment approved successfully! QR code generated.', 'success')
        return redirect(url_for('qr_page'))

    except Exception as e:
        db.rollback()
        print("DB Error:", e)
        flash('Something went wrong while approving the payment.', 'danger')
        return redirect(url_for('manage_subscribers'))

    finally:
        cursor.close()
        db.close()

@app.route('/base')
def base():
    return render_template('base.html')
@app.route('/')
@app.route('/index')
def home():
    return render_template('index.html')
@app.route('/choose')
def choose():
    db = get_db_connection()
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True)

    # Get user email
    cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    email = user['email'] if user else None

    # Check if user has an approved subscription
    cursor.execute("""
        SELECT *, DATE_ADD(created_at, INTERVAL duration MONTH) AS subscription_expiry
        FROM user_payments 
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,))
    subscription = cursor.fetchone()

    if subscription:
        if subscription['status'] == 'approved':
            expiry = subscription['subscription_expiry'].strftime('%Y-%m-%d')
            flash(f"You already have an active subscription. It will expire on {expiry}.", 'info')
        elif subscription['status'] == 'pending':
            flash("Your payment is still pending. Please complete it at the cashier.", 'warning')

    cursor.close()
    db.close()

    return render_template('choose.html', email=email)

@app.route('/fill_up', methods=['GET', 'POST'])
def fill_up():
    db = get_db_connection()
    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('login'))

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if not user:
        return redirect(url_for('login'))

    # Check if user already has a pending/active payment
    cursor.execute("""
        SELECT * FROM user_payments 
        WHERE user_id = %s AND status = 'pending' 
        ORDER BY created_at DESC LIMIT 1
    """, (user_id,))
    payment = cursor.fetchone()

    if payment:
        created_at = payment['created_at']
        duration = payment['duration']  # in months

        expiration_date = created_at + timedelta(days=duration * 30)

        if datetime.now() < expiration_date:
            flash(f"You already have an active subscription. It will expire on {expiration_date.strftime('%Y-%m-%d')}.", 'info')
            cursor.close()
            db.close()
            return redirect(url_for('choose'))
    user_data = {
        'firstname': user['firstname'],
        'lastname': user['lastname'],
        'email': user['email'],
        'phone': user['phone'],
        'birthday': user['birthday'],
        'age': user['age'],
        'city': user['city'],
        'province': user['province'],
        'barangay': user['barangay'],
        'created_at': user['created_at']
    }

    cursor.close()
    db.close()

    return render_template('fill_up.html', user=user_data)
@app.route('/process_payment', methods=['POST'])
def process_payment():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor()

    try:
        # Check if already subscribed and approved
        cursor.execute("""
            SELECT id FROM user_payments 
            WHERE user_id = %s AND status = 'approved'
        """, (user_id,))
        existing_payment = cursor.fetchone()

        if existing_payment:
            flash('You are already subscribed.', 'info')
            return redirect(url_for('choose'))

        # Get form data
        payment_method = request.form.get('payment_method')
        payment_plan = request.form.get('payment_plan')

        plan_details = {
            "5000": {"duration": 1, "amount": 5000},
            "10000": {"duration": 2, "amount": 10000},
            "15000": {"duration": 3, "amount": 15000},
            "20000": {"duration": 4, "amount": 20000},
            "25000": {"duration": 5, "amount": 25000},
            "30000": {"duration": 6, "amount": 30000},
            "35000": {"duration": 7, "amount": 35000},
            "40000": {"duration": 8, "amount": 40000},
            "45000": {"duration": 9, "amount": 45000},
            "50000": {"duration": 10, "amount": 50000},
            "55000": {"duration": 11, "amount": 55000},
            "60000": {"duration": 12, "amount": 60000}
        }

        plan = plan_details.get(payment_plan)
        if not plan:
            flash('Invalid payment plan selected.', 'error')
            return redirect(url_for('fill_up'))

        duration = plan['duration']
        amount = plan['amount']
        discount = 20 if duration >= 6 else 10

        if payment_method.lower() == "cash on cashier":
            status = 'pending'
            flash('Payment is pending, please pay at the cashier.', 'info')
            cursor.execute("""
                INSERT INTO user_payments (user_id, payment_method, status, duration, amount) 
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, payment_method, status, duration, amount))
            db.commit()
            return redirect(url_for('choose'))

        # Online payments (auto-approved)
        online_payment_methods = ["gcash", "credit card", "debit card", "bank transfer"]
        if payment_method.lower() in online_payment_methods:
            status = 'approved'
        else:
            status = 'pending'

        cursor.execute("""
            INSERT INTO user_payments (user_id, payment_method, status, duration, amount) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, payment_method, status, duration, amount))

        # Only update discount if payment is approved
        if status == 'approved':
            cursor.execute("""
                UPDATE users SET discount_percentage = %s WHERE id = %s
            """, (discount, user_id))

            # Generate QR Code
            qr_data = f"User ID: {user_id}, Plan: {duration} months, Amount: ₱{amount}, Discount: {discount}%"
            qr_img = qrcode.make(qr_data)
            buf = io.BytesIO()
            qr_img.save(buf, format='PNG')
            qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            session['show_qr'] = {
                'plan_duration': duration,
                'amount': amount,
                'discount': discount,
                'qr_code': qr_b64
            }
            flash('Payment processed successfully! You can now view your QR code.', 'success')
            db.commit()
            return redirect(url_for('qr_page'))

        db.commit()
        flash('Your payment is pending. Please complete the process.', 'info')
        return redirect(url_for('choose'))

    except Exception as e:
        db.rollback()
        print("DB Error:", e)
        flash('Something went wrong during the payment process.', 'danger')
        return redirect(url_for('fill_up'))

    finally:
        cursor.close()
        db.close()
@app.route('/qr_page')
def qr_page():    
    qr_data = session.get('show_qr')
    if not qr_data:
        flash('QR Code not found.', 'danger')
        return redirect(url_for('choose'))

    return render_template(
        'qr_page.html',
        plan=qr_data['plan_duration'],
        amount=qr_data['amount'],
        discount=qr_data['discount'],
        qr_code=qr_data['qr_code']
    )
@app.route('/about')
def about():
    return render_template('about.html')
@app.route('/clients')
def clients():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT t.model_id, t.comment_text, t.created_at, t.average_rating, 
        u.lastname AS user_name, u.profile_picture,  v.id AS vehicle_id
        FROM testimonials t
        JOIN users u ON t.user_id = u.id
        JOIN vehicles v ON t.model_id = v.id
        ORDER BY t.created_at DESC""")
    testimonials = cursor.fetchall()
    cursor.close()
    db.close()
    
    return render_template('clients.html', testimonials=testimonials)
@app.route('/deals')
def deals():
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Get logged-in user's discount
        user_id = session.get('user_id')
        discount = 0  # default if not logged in

        if user_id:
            cursor.execute("SELECT discount_percentage FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user and user['discount_percentage']:
                discount = user['discount_percentage']

        # Fetch all vehicles with their brands and average rating
        cursor.execute(""" 
            SELECT v.id AS vehicle_id, b.brand_name, v.model, v.price_per_day, v.status, 
                   v.image_url, v.people, v.transmission, v.mileage, v.gas,
                   AVG(t.average_rating) AS average_rating
            FROM vehicles v
            JOIN vehicle_brands b ON v.brand_id = b.id
            LEFT JOIN testimonials t ON v.id = t.model_id
            GROUP BY v.id, b.brand_name, v.model, v.price_per_day, v.status, v.image_url, 
                     v.people, v.transmission, v.mileage, v.gas
        """)
        vehicles = cursor.fetchall()    

        # Get unique brands directly from the database
        cursor.execute("SELECT DISTINCT brand_name FROM vehicle_brands")
        unique_brands = [row['brand_name'] for row in cursor.fetchall()]

        cursor.close()
        db.close()

        return render_template(
            'deals.html',
            vehicles=vehicles,
            unique_brands=unique_brands,
            discount=discount
        )

    except mysql.connector.Error as err:
        return f"Database error: {err}", 500
@app.route('/get_deals', methods=['GET'])
def get_deals():
    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Get logged-in user's discount
        user_id = session.get('user_id')
        discount = 0  # default if not logged in

        if user_id:
            cursor.execute("SELECT discount_percentage FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user and user['discount_percentage']:
                discount = user['discount_percentage']

        # Fetch all vehicles with their brands and average rating
        cursor.execute("""
            SELECT v.id AS vehicle_id, b.brand_name, v.model, v.price_per_day, v.status, 
                   v.image_url, v.people, v.transmission, v.mileage, v.gas,
                   AVG(t.average_rating) AS average_rating
            FROM vehicles v
            JOIN vehicle_brands b ON v.brand_id = b.id
            LEFT JOIN testimonials t ON v.id = t.model_id
            GROUP BY v.id, b.brand_name, v.model, v.price_per_day, v.status, v.image_url, 
                     v.people, v.transmission, v.mileage, v.gas
        """)
        vehicles = cursor.fetchall()

        if not vehicles:
            return jsonify({"message": "No vehicles found."}), 404

        # Add discount to each vehicle
        for car in vehicles:
            car['discount'] = discount

        cursor.close()
        db.close()

        return jsonify(vehicles)

    except mysql.connector.Error as err:
        return jsonify({"error": f"Database error: {err}"}), 500

@app.route('/update_profile', methods=['GET', 'POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    def calculate_age(birthday):
        today = datetime.today()
        birth_date = datetime.strptime(birthday, "%Y-%m-%d")
        age = today.year - birth_date.year
        if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
            age -= 1
        return age

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'profile':
            # Collect user input
            firstname = request.form.get('firstname', '').strip()
            lastname = request.form.get('lastname', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            country_code = request.form.get('country_code', '').strip()
            province = request.form.get('province', '').strip()
            city = request.form.get('city', '').strip()
            barangay = request.form.get('barangay', '').strip()
            birthday = request.form.get('birthday', '').strip()

            # Validate required fields
            if not firstname or not lastname or not email or not province or not city or not barangay or not birthday:
                flash("All fields are required.", "error")
                return redirect(url_for('update_profile'))

            # Calculate age from birthday
            age = calculate_age(birthday)

            # Store only the phone number excluding the country code
            full_phone = f"{country_code}{phone}"

            # Update the user profile in the database
            cursor.execute(""" 
                UPDATE users 
                SET firstname=%s, lastname=%s, email=%s, phone=%s, country_code=%s, 
                    province=%s, city=%s, barangay=%s, birthday=%s, age=%s 
                WHERE id=%s
            """, (firstname, lastname, email, phone, country_code, province, city, barangay, birthday, age, user_id))

            flash("Profile updated successfully!", "success")

        elif form_type == 'security':
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            if not current_password or not new_password or not confirm_password:
                flash("All password fields are required.", "error")
                return redirect(url_for('update_profile'))

            if new_password != confirm_password:
                flash("New passwords do not match.", "error")
                return redirect(url_for('update_profile'))

            cursor.execute("SELECT password FROM users WHERE id = %s", (user_id,))
            user_record = cursor.fetchone()

            if not user_record or not check_password_hash(user_record['password'], current_password):
                flash("Current password is incorrect.", "error")
                return redirect(url_for('update_profile'))

            hashed_password = generate_password_hash(new_password)

            cursor.execute(""" 
                UPDATE users SET password=%s WHERE id=%s
            """, (hashed_password, user_id))
            flash("Password updated successfully!", "success")

        elif form_type == 'license':
            allowed_extensions = {'jpg', 'jpeg', 'png'}

            def allowed_file(filename):
                return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

            # Handling Profile Picture Upload
            if 'profile_picture' in request.files:
                profile_picture = request.files['profile_picture']
                if profile_picture.filename != '':
                    if allowed_file(profile_picture.filename):
                        profile_filename = secure_filename(profile_picture.filename)
                        profile_upload_path = os.path.join('static/uploads/profile_pictures', profile_filename)
                        os.makedirs(os.path.dirname(profile_upload_path), exist_ok=True)
                        profile_picture.save(profile_upload_path)

                        profile_picture_relative_path = f"uploads/profile_pictures/{profile_filename}"
                        cursor.execute(""" 
                            UPDATE users SET profile_picture=%s WHERE id=%s
                        """, (profile_picture_relative_path, user_id))
                    else:
                        flash("Invalid file type for profile picture. Only JPG, JPEG, and PNG are allowed.", "error")
                        return redirect(url_for('update_profile'))

            # Handling License Picture Upload
            if 'license_pic' in request.files:
                license_pic = request.files['license_pic']
                if license_pic.filename != '':
                    if allowed_file(license_pic.filename):
                        license_filename = secure_filename(license_pic.filename)
                        license_upload_path = os.path.join('static/uploads/license_images', license_filename)
                        os.makedirs(os.path.dirname(license_upload_path), exist_ok=True)
                        license_pic.save(license_upload_path)

                        license_image_relative_path = f"uploads/license_images/{license_filename}"
                        cursor.execute(""" 
                            UPDATE users SET license_image=%s WHERE id=%s
                        """, (license_image_relative_path, user_id))
                    else:
                        flash("Invalid file type for license picture. Only JPG, JPEG, and PNG are allowed.", "error")
                        return redirect(url_for('update_profile'))

            flash("Profile Picture and/or License Picture updated successfully!", "success")

        else:
            flash("Invalid form submission.", "error")

        conn.commit()

    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("update_profile.html", user=user)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template('login.html')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        # Check if user exists
        if user:
            # Check if password is correct
            if check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['user_name'] = user['firstname'] 
                session['user_email'] = user['email']
                flash("You have been logged in.", "success")
                return redirect(url_for('home'))
            else:
                flash("Invalid password.", "error")
        else:
            flash("No account found with this email.", "error")

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    locations = load_locations()
    
    if request.method == 'POST':    
        # Get form data
        firstname = request.form.get('firstname', '').strip()
        lastname = request.form.get('lastname', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        age = request.form.get('age', '').strip()
        country_code = request.form.get('country_code', '').strip()
        phone = request.form.get('phone', '').strip()
        birthday = request.form.get('birthday', '').strip()
        province = request.form.get('province', '').strip()
        city = request.form.get('city', '').strip()
        barangay = request.form.get('barangay', '').strip()
        
        # Handle file uploads
        profile_picture = request.files.get('profile_picture')
        license_image = request.files.get('license_image')

        # Check if form data is missing
        if not firstname or not lastname or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template('register.html', locations=locations)

        # Validation checks
        if len(firstname) < 3 or len(lastname) < 3:
            flash("First name and last name must be at least 3 characters long.", "error")
            return render_template('register.html', locations=locations)

        if not re.match(r'^[a-z0-9._%+-]+@(gmail\.com|yahoo\.com|outlook\.com)$', email):
            flash("Invalid email format. Use Gmail, Yahoo, or Outlook.", "error")
            return render_template('register.html', locations=locations)

        if not age.isdigit() or int(age) < 18:
            flash("You must be at least 18 years old to register.", "error")
            return render_template('register.html', locations=locations)

        if not re.match(r'^\d{10,13}$', phone):
            flash("Full phone number must be between 10 to 13 digits.", "error")
            return render_template('register.html', locations=locations)
        if not re.match(r'^\d{10,13}$', phone):
            flash("Phone number must be between 10 to 13 digits (without country code).", "error")
            return redirect(url_for('update_profile'))
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template('register.html', locations=locations)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('register.html', locations=locations)

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Handle profile picture upload
        profile_pic_filename = 'static/uploads/profile_pictures/default.jpg'
        if profile_picture and allowed_file(profile_picture.filename):
            filename = secure_filename(profile_picture.filename)
            profile_pic_path = os.path.join(PROFILE_PICTURE_FOLDER, filename)
            profile_picture.save(profile_pic_path)
            profile_pic_filename = f'static/uploads/profile_pictures/{filename}'

        # Handle license image upload
        license_image_filename = 'static/uploads/license_images/default.jpg'
        if license_image and allowed_file(license_image.filename):
            license_filename = secure_filename(license_image.filename)
            license_path = os.path.join(LICENSE_IMAGE_FOLDER, license_filename)
            license_image.save(license_path)
            license_image_filename = f'static/uploads/license_images/{license_filename}'

        # Connect to the database
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Check if email exists
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            existing_user = cursor.fetchone()

            if existing_user:
                flash("Email already exists.", "error")
                return render_template('register.html', locations=locations)

            # Insert user data with both images
            cursor.execute('''
    INSERT INTO users (
        firstname, lastname, email, password, age, phone, country_code, birthday,
        province, city, barangay, profile_picture, license_image
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
''', (
    firstname, lastname, email, hashed_password, age, phone, country_code, birthday,
    province, city, barangay, profile_pic_filename, license_image_filename
))


            conn.commit()

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html', locations=locations)
import uuid 
from datetime import datetime
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        birthday = request.form.get('birthday', '').strip()

        if not email:
            flash("Email is required.", "error")
            return render_template('forgot_password.html')

        if not re.match(r'^[a-z0-9._%+-]+@(gmail\.com|yahoo\.com|outlook\.com)$', email):
            flash("Invalid email format. Use Gmail, Yahoo, or Outlook.", "error")
            return render_template('forgot_password.html')

        if not birthday:
            flash("Birthday is required for verification.", "error")
            return render_template('forgot_password.html')

        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Get user data based on email
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()

            if not user:
                flash("Email not found in our records.", "error")
                return render_template('forgot_password.html')

            # Convert the entered birthday to the correct format
            try:
                entered_birthday = datetime.strptime(birthday, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid birthday format. Please use YYYY-MM-DD.", "error")
                return render_template('forgot_password.html')

            # Directly compare the stored birthday (assuming it is a DATE type)
            stored_birthday = user['birthday']  # No need to call .date()

            if entered_birthday != stored_birthday:
                flash("Birthday does not match our records.", "error")
                return render_template('forgot_password.html')

            # Generate a unique token
            token = str(uuid.uuid4())

            # Save token to database
            cursor.execute('UPDATE users SET reset_token = %s WHERE email = %s', (token, email))
            conn.commit()

            # Redirect to reset_password page with token in query string
            return redirect(url_for('reset_password', token=token))

        except Exception as e:
            flash(f"An error occurred: {e}", "error")
            if conn:
                conn.rollback()

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token')

    if not token:
        flash("Invalid or missing token.", "error")
        return redirect(url_for('forgot_password'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch user by token
        cursor.execute("SELECT * FROM users WHERE reset_token = %s", (token,))
        user = cursor.fetchone()

        if not user:
            flash("Invalid or expired reset token.", "error")
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            if not password or not confirm_password:
                flash("All fields are required.", "error")
                return render_template('reset_password.html', token=token)

            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template('reset_password.html', token=token)

            hashed_password = generate_password_hash(password)

            # Update password and remove the token
            cursor.execute("""
                UPDATE users
                SET password = %s, reset_token = NULL
                WHERE id = %s
            """, (hashed_password, user['id']))
            conn.commit()

            flash("Your password has been reset successfully!", "success")
            return redirect(url_for('login'))

    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('home')) 

if __name__ == '__main__':
    socketio.run(app, debug=True)
