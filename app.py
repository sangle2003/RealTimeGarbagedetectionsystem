from flask import Flask, request, redirect, send_from_directory, Response, session, render_template
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from ultralytics import YOLO
from datetime import datetime
import threading
import cv2
import os
import winsound
from bson.objectid import ObjectId
import smtplib
from email.mime.text import MIMEText
Email = "yourgmail@gmail.com"
Password = "your_app_password"


app = Flask(__name__)
try:
    client = MongoClient("mongodb://localhost:27017/")
    db = client["garbage_system"]
    users_collection = db["users"]
    print("✅ Connected to MongoDB successfully!")
except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
app.secret_key = "supersecretkey"
bcrypt = Bcrypt(app)
print(bcrypt.generate_password_hash("admin123").decode("utf-8"))  # Test hashing

# ---------------- DATABASE ------------------ #
# Local MongoDB server sobat connect karne
client = MongoClient("mongodb://localhost:27017/")
db = client["garbage_system"]

# Collections (Tables)
users_collection = db["users"]
reports_collection = db["reports"]
detection_logs = db["detection_logs"]

# ---------------- AI MODEL ---------------- #
model = YOLO("yolov8n.pt")

# ---------------- GLOBAL VARIABLES ---------------- #
camera_active = False
cap = None
garbage_alert_played = False
garbage_count = 0

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- FILE SERVE ---------------- #
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ---------------- HOME ---------------- #
@app.route("/")
def home():
    total_reports = reports_collection.count_documents({})
    total_pending = reports_collection.count_documents({"status": "pending"})
    total_completed = reports_collection.count_documents({"status": "completed"})

    return render_template(
        "home.html",
        total_reports=total_reports,
        total_pending=total_pending,
        total_completed=total_completed
    )

# ---------------- REGISTRATION ROUTE ---------------- #
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return "<script>alert('Please fill all fields!'); window.history.back();</script>"

    existing_user = users_collection.find_one({"email": email})
    if existing_user:
        return f"""
        <script>
            alert('Email {email} is already registered! Please login.');
            window.location.href = '/login/user';
        </script>
        """

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    user_data = {
        "email": email,
        "password": hashed_password,
        "role": "user",
        "workerId": None,
        "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    }

    users_collection.insert_one(user_data)
    return """
    <script>
        alert('Registration Successful! You can now login.');
        window.location.href = '/login/user';
    </script>
    """

# ---------------- CREATE WORKER ---------------- #
@app.route("/create-worker")
def create_worker():
    worker_id = "WRK1001"
    password = "worker123"

    if users_collection.find_one({"workerId": worker_id}):
        return "Worker already exists"

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    users_collection.insert_one({
        "email": None,
        "workerId": worker_id,
        "password": hashed,
        "role": "worker"
    })

    return "Worker Created Successfully"

# ---------------- LOGIN ROUTES (UPDATED) ---------------- #
@app.route("/login/user", methods=["GET", "POST"])
def user_login():
    if request.method == "GET":
        return render_template("login.html", title="User Login", role="user")

    email = request.form.get("email") or (request.json and request.json.get("email"))
    password = request.form.get("password") or (request.json and request.json.get("password"))

    user = users_collection.find_one({"email": email})

    # 🔥 ID WRONG
    if not user:
        return "<script>alert('❌ Email ID is wrong! Please check your email.'); window.history.back();</script>"

    # 🔥 PASSWORD WRONG
    if not bcrypt.check_password_hash(user["password"], password):
        return "<script>alert('❌ Password is wrong! Please try again.'); window.history.back();</script>"

    session["user"] = email
    session["role"] = "user"

    if request.is_json:
        return {"message": "Login Successful", "redirect": "/dashboard/user"}
    return redirect("/dashboard/user")

@app.route("/login/worker", methods=["GET", "POST"])
def worker_login():
    if request.method == "GET":
        return render_template("login.html", title="Worker Login", role="worker")

    workerId = request.form.get("workerId") or (request.json and request.json.get("workerId"))
    password = request.form.get("password") or (request.json and request.json.get("password"))

    worker = users_collection.find_one({"workerId": workerId})

    # 🔥 ID WRONG MESSAGE
    if not worker:
        return "<script>alert('❌ Worker ID is wrong! Please check your ID.'); window.history.back();</script>"

    # 🔥 PASSWORD WRONG MESSAGE
    if not bcrypt.check_password_hash(worker["password"], password):
        return "<script>alert('❌ Password is wrong! Please try again.'); window.history.back();</script>"

    session["worker"] = workerId
    session["role"] = "worker"

    if request.is_json:
        return {"message": "Login Successful", "redirect": "/dashboard/worker"}
    return redirect("/dashboard/worker")

# ---------------- DASHBOARD ---------------- #
@app.route("/dashboard/user")
def user_dashboard():
    if "role" not in session or session["role"] != "user":
        return redirect("/login/user")
    return render_template("user_dashboard.html")

@app.route("/dashboard/worker")
def worker_dashboard():
    if "role" not in session or session["role"] != "worker":
        return redirect("/login/worker")

    worker_id = session.get("worker")
    completed_count = reports_collection.count_documents({"status": "completed", "completed_by": worker_id})
    total_pending = reports_collection.count_documents({"status": "pending"})
    total_completed = reports_collection.count_documents({"status": "completed"})
    total_reports = reports_collection.count_documents({})

    return render_template(
        "worker_dashboard.html",
        completed_count=completed_count,
        total_pending=total_pending,
        total_completed=total_completed,
        total_reports=total_reports
    )

# ---------------- VIEW ALL REPORTS ROUTE ---------------- #
@app.route("/view-reports")
def view_reports():
    if "role" not in session or session["role"] not in ["admin", "worker"]:
        return redirect("/login/admin")
    all_reports = list(reports_collection.find().sort("date", -1))
    return render_template("view_reports.html", reports=all_reports)

# ---------------- DETECTION LOGS ---------------- #
@app.route("/detection-logs")
def view_detection_logs():
    logs = list(detection_logs.find().sort("timestamp", -1))
    return render_template("detection_logs.html", logs=logs)

# ---------------- LIVE DETECTION ---------------- #
def play_beep():
    winsound.Beep(3000, 1000)

def generate_frames():
    global cap, camera_active, garbage_alert_played, garbage_count
    while camera_active:
        if cap is None:
            break
            
        success, frame = cap.read()
        if not success:
            break

        results = model(frame)
        garbage_found = False

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                class_name = model.names[cls]

                if class_name == "bottle":
                    garbage_found = True
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                    cv2.putText(frame, "Garbage Detected", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)

        if garbage_found and not garbage_alert_played:
            garbage_count += 1
            threading.Thread(target=play_beep).start()
            garbage_alert_played = True

        if not garbage_found:
            garbage_alert_played = False

        cv2.putText(frame, f"Garbage Count: {garbage_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route("/live-detection")
def live_detection():
    return render_template("live_detection.html")

@app.route("/video-feed")
def video_feed():
    global cap, camera_active
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    camera_active = True
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/stop-camera")
def stop_camera():
    global cap, camera_active
    camera_active = False
    if cap:
        cap.release()
        cap = None
    return "Stopped"

# ================= ADMIN SYSTEM ================= #

@app.route("/create-admin")
def create_admin():
    # old admin delete
    users_collection.delete_many({"role": "admin"})

    # new admin password hash
    hashed = bcrypt.generate_password_hash("admin123").decode("utf-8")

    # fresh admin create
    users_collection.insert_one({
        "email": "admin@gmail.com",
        "password": hashed,
        "role": "admin",
        "workerId": None
    })

    return "✅ Fresh Admin Created Successfully"


@app.route("/login/admin", methods=["GET", "POST"])
def admin_login():

    if request.method == "GET":
        return render_template("admin_login.html")

    email = request.form.get("email")
    password = request.form.get("password")

    admin = users_collection.find_one({
        "email": email,
        "role": "admin"
    })

    # email wrong
    if not admin:
        return "<script>alert('❌ Admin Email is wrong!'); window.location.href='/login/admin';</script>"

    # password wrong
    if not bcrypt.check_password_hash(admin["password"], password):
        return "<script>alert('❌ Admin Password is wrong!'); window.location.href='/login/admin';</script>"

    # success login
    session["admin"] = email
    session["role"] = "admin"

    return redirect("/dashboard/admin")


@app.route("/dashboard/admin")
def admin_dashboard():

    if "role" not in session or session["role"] != "admin":
        return redirect("/login/admin")

    total_users = users_collection.count_documents({"role": "user"})
    total_workers = users_collection.count_documents({"role": "worker"})
    total_reports = reports_collection.count_documents({})
    total_pending = reports_collection.count_documents({"status": "pending"})
    total_completed = reports_collection.count_documents({"status": "completed"})

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_workers=total_workers,
        total_reports=total_reports,
        total_pending=total_pending,
        total_completed=total_completed
    )


@app.route("/admin/create-worker", methods=["GET", "POST"])
def admin_create_worker():

    if "role" not in session or session["role"] != "admin":
        return redirect("/login/admin")

    if request.method == "GET":
        return render_template("admin_create_worker.html")

    worker_id = request.form.get("workerId")
    password = request.form.get("password")

    if not worker_id or not password:
        return "<script>alert('Please fill all fields!'); window.history.back();</script>"

    if users_collection.find_one({"workerId": worker_id}):
        return "<script>alert('Worker ID already exists!'); window.history.back();</script>"

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")

    users_collection.insert_one({
        "email": None,
        "workerId": worker_id,
        "password": hashed,
        "role": "worker"
    })

    return "<script>alert('✅ Worker Created Successfully!'); window.location.href='/dashboard/admin';</script>"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- REPORT GARBAGE ROUTE ---------------- #
@app.route("/report-garbage", methods=["GET", "POST"])
def report_garbage():

    if "role" not in session:
        return redirect("/login/user")

    if request.method == "GET":
        return render_template("report_garbage.html")

    # ✅ SAFE DATA FETCH (NO KEY ERROR)
    address = request.form.get("address")
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    file = request.files.get("image")

    # ✅ VALIDATION
    if not lat or not lng:
        return "<script>alert('Please click on map to select location');window.history.back()</script>"

    if not address:
        return "<script>alert('Address not detected');window.history.back()</script>"

    if not file:
        return "<script>alert('Please upload image');window.history.back()</script>"

    filename = secure_filename(file.filename)
    unique_filename = f"{datetime.now().timestamp()}_{filename}"

    file.save(os.path.join(UPLOAD_FOLDER, unique_filename))

    reports_collection.insert_one({
        "user_email": session.get("user"),
        "address": address,
        "lat": lat,
        "lng": lng,
        "image": unique_filename,
        "status": "pending",
        "date": datetime.now().strftime("%d-%m-%Y"),
        "time": datetime.now().strftime("%H:%M:%S")
    })

    return "<script>alert('Report Submitted Successfully');window.location='/dashboard/user'</script>"

# ---------------- COMPLAINT LETTER ---------------- #
@app.route("/generate-complaint/<report_id>")
def generate_complaint(report_id):
    if "email" not in session:
        return redirect("/login/user")
    
    report = reports_collection.find_one({"_id": ObjectId(report_id)})
    
    if report:
        complaint_text = f"""
        To,
        The Municipal Commissioner,
        Health & Sanitation Department.
        
        Subject: Formal Complaint regarding uncleaned garbage (Report ID: {report_id})
        
        Respected Sir/Madam,
        I am writing to bring to your notice that a garbage issue reported on {report['date']} 
        at location {report['address']} has not been resolved for more than 3 days.
        
        Despite the initial report, the status remains 'Pending'. This is causing health 
        hazards and a foul smell in the area. 
        
        Kindly look into this matter urgently.
        
        Regards,
        Concerned Citizen ({session['email']})
        """
        return render_template("complaint_letter.html", letter=complaint_text, report=report)
    
    return "Report not found", 404
    #----------------- ROOT CAUSE ------------------#
    

@app.route("/mark-cleaned/<id>")
def mark_cleaned(id):

    if "role" not in session or session["role"] != "worker":
        return redirect("/login/worker")

    reports_collection.update_one(
        {"_id": ObjectId(id)},
        {
            "$set": {
                "status": "completed",
                "completed_by": session.get("worker")
            }
        }
    )

    return redirect("/view-reports")
 
    #----------------- MARK CLEANED ------------------#
    @app.route("/mark-cleaned/<report_id>")
    def mark_cleaned(report_id):
        if "role" not in session or session["role"] != "worker":
            return redirect("/login/worker")

        reports_collection.update_one(
            {"_id": ObjectId(report_id)},
            {
                "$set": {
                    "status": "completed",
                    "completed_by": session.get("worker")
                }
            }
        )

        return redirect("/view-reports")
    
    #----------------- COMPLETED REPORTS ------------------#
@app.route("/completed-reports")
def completed_reports():
    if "role" not in session or session["role"] != "worker":
        return redirect("/login/worker")
    completed=list(reports_collection.find({"status": "completed"}))
    return render_template("completed_reports.html", reports=completed)

    #----------------- DELETED REPORTS ------------------#
    from bson.objectid import ObjectId

@app.route("/delete-report/<report_id>")
def delete_report(report_id):

    if "role" not in session or session["role"] != "worker":
        return redirect("/login/worker")

    try:
        reports_collection.delete_one({"_id": ObjectId(report_id)})
    except:
        return "Invalid ID"

    return redirect("/view-reports")

def send_email(to_email, address):
    subject = "Garbage Cleaned Successfully"
    body = f"""Hello,
    
    Your reported garbage at {address} has been cleaned. Thank you for helping us keep the city clean!

    """
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['To'] = to_email
    msg['From'] = Email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(Email, Password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")
        



if __name__ == "__main__":
    app.run(debug=True)