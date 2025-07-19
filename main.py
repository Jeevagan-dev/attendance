import os
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from geopy.distance import geodesic
from streamlit_js_eval import get_geolocation
from PIL import Image
import io
import pymongo
from dotenv import load_dotenv
import pytz
import hashlib
import plotly.express as px
import streamlit.components.v1 as components

# ----------- ENV + DB -----------
load_dotenv()
connection_string = os.getenv("MONGODB_CONNECTION_STRING")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

try:
    client = pymongo.MongoClient(connection_string, serverSelectionTimeoutMS=3000)

    client.server_info()
    st.toast("✅ MongoDB connected", icon="✅")
except Exception as e:
    st.error(f"❌ MongoDB error: {e}")
    st.stop()



db = client["attendance_db"]


attendance_collection = db["attendance"]
settings_collection = db["settings"]
employees_collection = db["employees"]

IST = pytz.timezone('Asia/Kolkata')
ALLOWED_LOCATION = (12.8324706, 80.2286148)
MAX_DISTANCE_KM = 1.0

# ----------- Utility -----------
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_current_ist_time():
    return datetime.now(IST)

def save_image(img):
    image = Image.open(img)
    image = image.resize((250, 250))
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def speak_feedback(message):
    js_code = f"""
    <script>
    var utter = new window.SpeechSynthesisUtterance("{message}");
    window.speechSynthesis.speak(utter);
    </script>
    """
    components.html(js_code)

def is_within_allowed_location(lat, lon):
    user_location = (lat, lon)
    distance = geodesic(user_location, ALLOWED_LOCATION).kilometers
    return distance <= MAX_DISTANCE_KM

def get_location_restriction():
    setting = settings_collection.find_one({"setting": "location_restriction"})
    if setting:
        return setting["value"]
    else:
        settings_collection.insert_one({"setting": "location_restriction", "value": True})
        return True

def set_location_restriction(value):
    settings_collection.update_one({"setting": "location_restriction"},{"$set": {"value": value}},upsert=True)

# ----------- Employee Management -----------
def add_employee(emp_id, name, password):
    emp_id = emp_id.strip()
    name = name.strip()
    if not emp_id or not name or not password:
        return False, "ID, name, and password required."
    if employees_collection.find_one({"Employee ID": emp_id}):
        return False, "Employee ID already exists."
    doc = {"Employee ID": emp_id, "Name": name, "Password Hash": hash_password(password)}
    employees_collection.insert_one(doc)
    return True, "Employee added successfully."

def remove_employee(emp_id):
    if not employees_collection.find_one({"Employee ID": emp_id}):
        return False, "Employee ID not found."
    employees_collection.delete_one({"Employee ID": emp_id})
    return True, f"Removed employee: {emp_id}"

def authenticate_employee(emp_id, pw):
    emp = employees_collection.find_one({"Employee ID": emp_id})
    if emp and hash_password(pw) == emp["Password Hash"]:
        return emp
    return None

def load_employees():
    return [{"Employee ID": e["Employee ID"], "Name": e["Name"]} for e in employees_collection.find()]

# ----------- Attendance Management -----------
def log_arrival(emp_id, name, date, photo):
    query_date = datetime.combine(date, datetime.min.time())
    if attendance_collection.find_one({"Employee ID": emp_id, "Date": query_date}):
        return False, "Arrival already logged for today."
    entry = {
        'Employee ID': emp_id,
        'Name': name,
        'Date': query_date,
        'Arrival Time': get_current_ist_time().strftime('%I:%M %p'),
        'Leaving Time': None,
        'Hours Present': None,
        'Arrival Photo': save_image(photo),
        'Leaving Photo': None
    }
    attendance_collection.insert_one(entry)
    return True, "Arrival logged successfully."

def log_leaving(emp_id, date, photo):
    query_date = datetime.combine(date, datetime.min.time())
    entry = attendance_collection.find_one({"Employee ID": emp_id, "Date": query_date})
    if not entry:
        return False, "Arrival not logged for today."
    if entry['Leaving Time'] is not None:
        return False, "Leaving time already logged for today."
    leaving_time = get_current_ist_time()
    arrival_time = datetime.strptime(entry['Arrival Time'], '%I:%M %p')
    date_obj = datetime.combine(date, datetime.min.time())
    arrival_datetime = date_obj.replace(hour=arrival_time.hour, minute=arrival_time.minute)
    leaving_datetime = date_obj.replace(hour=leaving_time.hour, minute=leaving_time.minute)
    time_diff = (leaving_datetime - arrival_datetime).total_seconds() / 3600
    if time_diff < 0:
        leaving_datetime += timedelta(days=1)
        time_diff = (leaving_datetime - arrival_datetime).total_seconds() / 3600
    attendance_collection.update_one(
        {"_id": entry["_id"]},
        {"$set": {
            'Leaving Time': leaving_time.strftime('%I:%M %p'),
            'Hours Present': round(time_diff, 2),
            'Leaving Photo': save_image(photo)
        }}
    )
    return True, "Leaving time logged successfully."

def load_attendance(emp_id=None):
    q = {"Employee ID": emp_id} if emp_id else {}
    entries = list(attendance_collection.find(q))
    cleaned = []
    for entry in entries:
        entry['Date'] = entry['Date'].strftime('%Y-%m-%d')
        cleaned.append(entry)
    df = pd.DataFrame(cleaned)
    cols = ['Employee ID','Name','Date','Arrival Time','Leaving Time','Hours Present','Arrival Photo','Leaving Photo']
    for c in cols:
        if c not in df.columns:
            df[c]=None
    return df

# ----------- Employee UI -----------
def employee_login():
    st.header("Employee Login")
    emp_id = st.text_input("Employee ID")
    pw = st.text_input("Password", type="password")
    if st.button("Login"):
        emp = authenticate_employee(emp_id, pw)
        if emp:
            st.session_state.employee = {"Employee ID": emp_id, "Name": emp["Name"]}
            st.success(f"Logged in as {emp['Name']}")
            st.rerun()
        else:
            st.error("Invalid ID or password.")

def employee_dashboard():
    emp = st.session_state.employee
    st.header(f"Welcome, {emp['Name']} (ID: {emp['Employee ID']})!")
    current_date = date.today()
    location = get_geolocation()
    location_restriction = get_location_restriction()

    if location_restriction:
        if location is None:
            st.info("Waiting for device location. Please allow location access.")
            return
        lat, lon = location['coords']['latitude'], location['coords']['longitude']
        if not is_within_allowed_location(lat, lon):
            st.error("❌ Out of allowed location.")
            return

    # Attendance logic
    df = load_attendance(emp["Employee ID"])
    today_entries = df[df['Date'] == current_date.strftime('%Y-%m-%d')]

    st.markdown("---")
    if today_entries.empty:
        st.subheader("Arrival Logging")
        img_file = st.camera_input("Take a selfie to verify your arrival")
        if img_file is not None:
            if st.button("Log Arrival Time", use_container_width=True):
                success, message = log_arrival(emp["Employee ID"], emp["Name"], current_date, img_file)
                if success:
                    speak_feedback("Arrival logged successfully.")
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)
    else:
        latest_entry = today_entries.iloc[-1]
        if pd.isna(latest_entry['Leaving Time']):
            st.info(f"Arrival time logged at: {latest_entry['Arrival Time']}")
            st.subheader("Leave Logging")
            img_file = st.camera_input("Take a selfie to verify your leaving")
            if img_file is not None:
                if st.button("Log Leaving Time", use_container_width=True):
                    success, message = log_leaving(emp["Employee ID"], current_date, img_file)
                    if success:
                        speak_feedback("Leaving logged successfully.")
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        else:
            st.success(f"All done ✅ Arrival: {latest_entry['Arrival Time']} | Leaving: {latest_entry['Leaving Time']}")
            speak_feedback("You have already logged both arrival and leaving for today.")

    st.markdown("---")
    st.subheader("Your Attendance Records")
    if not df.empty:
        for idx, row in df.sort_values('Date', ascending=False).head(30).iterrows():
            col1, col2, col3 = st.columns([1, 1, 3])
            if row['Arrival Photo']:
                try:
                    col1.image(Image.open(io.BytesIO(row['Arrival Photo'])), width=80, caption="Arrival")
                except Exception:
                    col1.warning("No Arrival Photo")
            else:
                col1.warning("No Arrival Photo")
            if row['Leaving Photo']:
                try:
                    col2.image(Image.open(io.BytesIO(row['Leaving Photo'])), width=80, caption="Leaving")
                except Exception:
                    col2.warning("No Leaving Photo")
            else:
                col2.warning("No Leaving Photo")
            col3.write(f"**Date:** {row['Date']}\n**Arrival:** {row.get('Arrival Time','-')}\n**Leaving:** {row.get('Leaving Time','-')}\n**Hours:** {row.get('Hours Present','-')}")
            st.markdown("---")

# ----------- Admin UI -----------
def admin_page():
    st.header("🛡️ Admin Panel")
    tab1, tab2, tab3, tab4 = st.tabs([
        "Add/Remove Employee", "Attendance Records", "Visualization/Download", "Location Restriction"])
    # Add/Remove Employee Tab
    with tab1:
        st.subheader("Manage Employees")
        with st.form("add_employee_form"):
            emp_id = st.text_input("Employee ID")
            emp_name = st.text_input("Employee Name")
            emp_pw = st.text_input("Employee Password", type="password")
            submitted = st.form_submit_button("Add Employee")
            if submitted:
                success, msg = add_employee(emp_id, emp_name, emp_pw)
                if success:
                    st.success(msg)
                else:
                    st.warning(msg)
        emps = load_employees()
        if emps:
            remove_id = st.selectbox("Select Employee ID to remove", [e["Employee ID"] for e in emps])
            if st.button("Remove Employee"):
                success, msg = remove_employee(remove_id)
                if success:
                    st.success(msg)
                else:
                    st.warning(msg)
        st.dataframe(pd.DataFrame(emps), use_container_width=True)

    # Attendance Records & Photos
    with tab2:
        st.subheader("Attendance Records & Photo Proof")
        df = load_attendance()
        if df.empty:
            st.info("No attendance records found.")
        else:
            selected = st.selectbox("Select Employee for Records", ["All"]+[e["Employee ID"] for e in load_employees()], key="adm_view_emp")
            display_df = df.drop(columns=['_id'], errors='ignore')
            if selected == "All":
                sub = display_df
            else:
                sub = display_df[display_df["Employee ID"]==selected]
            for idx, row in sub.sort_values('Date', ascending=False).iterrows():
                col1, col2, col3, col4 = st.columns([1,1,2,2])
                if row['Arrival Photo']:
                    try: col1.image(Image.open(io.BytesIO(row['Arrival Photo'])), width=80, caption="Arrival")
                    except Exception: col1.warning("No Arrival Photo")
                else:
                    col1.warning("No Arrival Photo")
                if row['Leaving Photo']:
                    try: col2.image(Image.open(io.BytesIO(row['Leaving Photo'])), width=80, caption="Leaving")
                    except Exception: col2.warning("No Leaving Photo")
                else:
                    col2.warning("No Leaving Photo")
                col3.write(f"**ID:** {row['Employee ID']}\n**Name:** {row['Name']}\n**Date:** {row['Date']}")
                col4.write(f"**Arrival:** {row.get('Arrival Time','-')}\n**Leaving:** {row.get('Leaving Time','-')}\n**Hours:** {row.get('Hours Present','-')}")
                st.markdown("---")

            # Attendance Record Editing
            st.subheader("Edit Attendance Record")
            emp_id_list = [e["Employee ID"] for e in load_employees()]
            emp_to_update = st.selectbox('Employee to Update', emp_id_list, key="edit_emp")
            date_to_update = st.date_input('Date to Update', date.today())
            entry = attendance_collection.find_one({"Employee ID": emp_to_update, "Date": datetime.combine(date_to_update, datetime.min.time())})
            if entry:
                arr_time = st.text_input('Arrival Time', value=entry.get('Arrival Time', ''))
                leave_time = st.text_input('Leaving Time', value=entry.get('Leaving Time', ''))
                if st.button('Update Record', use_container_width=True):
                    try:
                        arr_dt = datetime.strptime(arr_time, '%I:%M %p')
                        leave_dt = datetime.strptime(leave_time, '%I:%M %p')
                        diff = (leave_dt - arr_dt).total_seconds() / 3600
                        hours_present = round(diff, 2)
                    except Exception:
                        hours_present = None
                    result = attendance_collection.update_one(
                        {"_id": entry["_id"]},
                        {"$set": {
                            "Arrival Time": arr_time,
                            "Leaving Time": leave_time,
                            "Hours Present": hours_present
                        }}
                    )
                    if result.modified_count > 0:
                        st.success("Updated successfully.")
                    else:
                        st.warning("No change or update failed.")
                if entry.get('Arrival Photo'):
                    st.image(Image.open(io.BytesIO(entry['Arrival Photo'])), caption="Arrival Photo")
                if entry.get('Leaving Photo'):
                    st.image(Image.open(io.BytesIO(entry['Leaving Photo'])), caption="Leaving Photo")
            else:
                st.info("No record found for that employee/date.")

    # Visualization Tab
    with tab3:
        st.subheader("Visualization and Data Download")
        df = load_attendance()
        if df.empty:
            st.info("No attendance data.")
        else:
            df["Date"] = pd.to_datetime(df["Date"])
            grp = df.groupby('Date')["Employee ID"].nunique().reset_index()
            fig = px.line(grp, x='Date', y='Employee ID', labels={"Employee ID": "Employees Present"})
            st.plotly_chart(fig, use_container_width=True)
            df2 = df.groupby('Employee ID')['Hours Present'].sum().reset_index()
            fig2 = px.bar(df2, x="Employee ID", y="Hours Present")
            st.plotly_chart(fig2, use_container_width=True)
            st.download_button(
                label="Download as CSV",
                data=df.to_csv(index=False),
                file_name="attendance.csv",
                mime="text/csv"
            )

    # Geolocation Restriction Admin
    with tab4:
        st.subheader("Geolocation Attendance Restriction")
        loc_restrict = get_location_restriction()
        opt = st.checkbox("Enable Attendance Location Restriction", value=loc_restrict)
        if st.button("Update Location Setting"):
            set_location_restriction(opt)
            st.success(f"Location restriction {'enabled' if opt else 'disabled'}.")

# ----------- Main Routing -----------
def main():
    st.set_page_config(page_title="Attendance System", layout="wide")
    st.sidebar.title("📋 Navigation")
    page = st.sidebar.radio("", ["Employee Login", "Admin Panel"])

    # Employee Auth
    if page == "Employee Login":
        if "employee" not in st.session_state:
            employee_login()
        else:
            if st.sidebar.button("Logout"):
                del st.session_state.employee
                st.rerun()
            else:
                employee_dashboard()
    elif page == "Admin Panel":
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if not st.session_state.authenticated:
            st.sidebar.subheader("🔐 Admin Login")
            username = st.sidebar.text_input("Admin Username")
            password = st.sidebar.text_input("Admin Password", type="password")
            if st.sidebar.button("Admin Login", use_container_width=True):
                if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Invalid admin credentials")
        else:
            if st.sidebar.button("Admin Logout", use_container_width=True):
                st.session_state.authenticated = False
                st.rerun()
            admin_page()

if __name__ == "__main__":
    main()
