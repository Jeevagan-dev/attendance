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
import plotly.express as px
import plotly.graph_objects as go

# Load environment variables from .env file
load_dotenv()

# Get the connection string from environment variables
connection_string = os.getenv("MONGODB_CONNECTION_STRING")

# Define the allowed location coordinates (latitude, longitude)
ALLOWED_LOCATION = (12.1174794, 79.6146406)  #coordinates
MAX_DISTANCE_KM = 1.0 # Maximum allowed distance in kilometers

# Connect to MongoDB
client = pymongo.MongoClient(connection_string)
db = client["attendance_db"]
attendance_collection = db["attendance"]
settings_collection = db["settings"]

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')

def get_current_ist_time():
    return datetime.now(IST)

def save_image(img):
    image = Image.open(img)
    image = image.resize((250, 250))  # Resize to 250x250 pixels
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def log_arrival(name, date, photo):
    # Convert date to datetime for MongoDB query
    query_date = datetime.combine(date, datetime.min.time())
    
    if attendance_collection.find_one({"Name": name, "Date": query_date}):
        return False, "Arrival already logged for today."

    current_time = get_current_ist_time()
    photo_data = save_image(photo)

    new_entry = {
        'Name': name,
        'Date': query_date,
        'Arrival Time': current_time.strftime('%I:%M %p'),
        'Leaving Time': None,
        'Hours Present': None,
        'Arrival Photo': photo_data,
        'Leaving Photo': None
    }

    attendance_collection.insert_one(new_entry)
    return True, "Arrival logged successfully."

def log_leaving(name, date, photo):
    # Convert date to datetime for MongoDB query
    query_date = datetime.combine(date, datetime.min.time())
    
    entry = attendance_collection.find_one({"Name": name, "Date": query_date})
    if not entry:
        return False, "Arrival not logged for today."

    if entry['Leaving Time'] is not None:
        return False, "Leaving time already logged for today."

    leaving_time = get_current_ist_time()
    arrival_time = datetime.strptime(entry['Arrival Time'], '%I:%M %p')
    # Combine the date and time for both arrival and leaving
    date_obj = datetime.combine(date, datetime.min.time())
    arrival_datetime = date_obj.replace(hour=arrival_time.hour, minute=arrival_time.minute)
    leaving_datetime = date_obj.replace(hour=leaving_time.hour, minute=leaving_time.minute)
    
    # Calculate time difference
    time_diff = leaving_datetime - arrival_datetime
    
    # Handle case where leaving time is on the next day
    if time_diff.total_seconds() < 0:
        leaving_datetime += timedelta(days=1)
        time_diff = leaving_datetime - arrival_datetime
    
    # Calculate hours present
    hours_present = round(time_diff.total_seconds() / 3600, 2)

    photo_data = save_image(photo)

    attendance_collection.update_one(
        {"_id": entry["_id"]},
        {
            "$set": {
                'Leaving Time': leaving_time.strftime('%I:%M %p'),
                'Hours Present': hours_present,
                'Leaving Photo': photo_data
            }
        }
    )
    return True, "Leaving time logged successfully."

def load_attendance():
    entries = list(attendance_collection.find())
    for entry in entries:
        entry['Date'] = entry['Date'].strftime('%Y-%m-%d')
    return pd.DataFrame(entries)

def is_within_allowed_location(lat, lon):
    user_location = (lat, lon)
    distance = geodesic(user_location, ALLOWED_LOCATION).kilometers
    return distance <= MAX_DISTANCE_KM

def calculate_attendance_stats(df, employee, month):
    df['Date'] = pd.to_datetime(df['Date'])
    if month != 'All':
        df = df[df['Date'].dt.strftime('%B %Y') == month]
    
    if employee != 'All':
        df = df[df['Name'] == employee]
    
    stats = []
    for name in df['Name'].unique():
        employee_df = df[df['Name'] == name]
        total_days = len(employee_df)
        total_hours = employee_df['Hours Present'].sum()
        leaves_taken = (employee_df['Arrival Time'].isna() | employee_df['Leaving Time'].isna()).sum()
        
        # Adjust for allowed leave
        if leaves_taken > 1:
            total_days -= (leaves_taken - 1)
            # total_hours -= (leaves_taken - 1) * 8
        
        stats.append({
            'Name': name,
            'Total Days Present': total_days,
            'Total Hours': round(total_hours, 2),
            'Leaves Taken': leaves_taken
        })
    
    return pd.DataFrame(stats)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def authenticate(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def view_attendance(df, start_date, end_date, employee, attributes):
    df['Date'] = pd.to_datetime(df['Date'])
    df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
    
    if employee != 'All':
        df = df[df['Name'] == employee]
    
    # Calculate 'Days Present' if selected
    if 'Days Present' in attributes:
        df['Days Present'] = df.groupby('Name')['Date'].transform('nunique')
    
    return df[['Name', 'Date'] + attributes]

def calculate_hours_present(arrival_time, leaving_time):
    try:
        # Parse arrival and leaving times in 12-hour format with AM/PM
        arrival = datetime.strptime(arrival_time, '%I:%M %p')
        leaving = datetime.strptime(leaving_time, '%I:%M %p')

        # Calculate difference in hours
        difference = (leaving - arrival).total_seconds() / 3600

        # Round to two decimal places
        hours_present = round(difference, 2)

        return hours_present

    except ValueError as e:
        print(f"Error parsing time: {e}")
        return None

def update_attendance_page():
    st.title('Update Attendance Records')

    df = load_attendance()
    employees = list(df['Name'].unique())
    selected_employee = st.selectbox('Select Employee to Update', employees)

    selected_date = st.date_input('Select Date', date.today())
    query_date = datetime.combine(selected_date, datetime.min.time())

    # Fetch attendance record for selected employee and date
    entry = attendance_collection.find_one({"Name": selected_employee, "Date": query_date})

    if entry:
        st.subheader('Update Details:')
        new_arrival_time = st.text_input('Arrival Time', value=entry['Arrival Time'])
        new_leaving_time = st.text_input('Leaving Time', value=entry['Leaving Time'])

        if st.button('Update'):
            # Calculate new hours present
            hours_present = calculate_hours_present(new_arrival_time, new_leaving_time)

            if hours_present is not None:
                # Update MongoDB record with Hours Present
                result = attendance_collection.update_one(
                    {"_id": entry["_id"]},
                    {
                        "$set": {
                            'Arrival Time': new_arrival_time,
                            'Leaving Time': new_leaving_time,
                            'Hours Present': hours_present
                        }
                    }
                )
                if result.modified_count > 0:
                    st.success('Attendance record updated successfully.')
                else:
                    st.warning('Failed to update attendance record.')
            else:
                st.error('Error calculating hours present. Please check your time inputs.')

    else:
        st.warning('No record found for the selected employee and date.')

def visualize_attendance(df):
    st.title('Visualize Attendance Records')
    
    # Date range selection
    col1, col2 = st.columns(2)
    start_date = pd.to_datetime(col1.date_input("Start Date", min_value=df['Date'].min().date(), max_value=df['Date'].max().date(), value=df['Date'].min().date()))
    end_date = pd.to_datetime(col2.date_input("End Date", min_value=df['Date'].min().date(), max_value=df['Date'].max().date(), value=df['Date'].max().date()))
    
    # Employee selection
    employees = ['All'] + list(df['Name'].unique())
    selected_employee = st.selectbox('Select Employee', employees)
    
    if selected_employee == 'All':
        df_filtered = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
    else:
        df_filtered = df[(df['Date'] >= start_date) & (df['Date'] <= end_date) & (df['Name'] == selected_employee)]
    
    if df_filtered.empty:
        st.warning("No data available for the selected filters.")
        return

    # Visualize total hours per day or employees present per day
    if selected_employee == 'All':
        st.subheader('Employees Present Per Day')
        df_grouped = df_filtered.groupby('Date')['Name'].nunique().reset_index()
        fig_employees_per_day = px.line(df_grouped, x='Date', y='Name', title='Employees Present Per Day')
        fig_employees_per_day.update_layout(yaxis_title='Number of Employees')
        st.plotly_chart(fig_employees_per_day)
    else:
        st.subheader('Hours Present Per Day')
        df_grouped = df_filtered.groupby('Date')['Hours Present'].sum().reset_index()
        fig_hours_per_day = px.line(df_grouped, x='Date', y='Hours Present', title='Hours Present Per Day')
        st.plotly_chart(fig_hours_per_day)

    # Visualize hours present per employee only when all employees are selected
    if selected_employee == 'All':
        st.subheader('Total Hours Present Per Employee')
        df_grouped = df_filtered.groupby('Name')['Hours Present'].sum().reset_index()
        df_grouped = df_grouped.sort_values(by='Hours Present', ascending=False)
        fig_hours_per_employee = px.bar(df_grouped, x='Name', y='Hours Present', title='Total Hours Present Per Employee')
        st.plotly_chart(fig_hours_per_employee)

    # Visualize arrival and leaving times
    st.subheader('Arrival and Leaving Times')
    fig_times = go.Figure()
    fig_times.add_trace(go.Scatter(x=df_filtered['Date'], y=pd.to_datetime(df_filtered['Arrival Time']).dt.time, mode='markers', name='Arrival Time'))
    fig_times.add_trace(go.Scatter(x=df_filtered['Date'], y=pd.to_datetime(df_filtered['Leaving Time']).dt.time, mode='markers', name='Leaving Time'))
    fig_times.update_layout(title='Arrival and Leaving Times', xaxis_title='Date', yaxis_title='Time')
    st.plotly_chart(fig_times)

def get_location_restriction():
    setting = settings_collection.find_one({"setting": "location_restriction"})
    if setting:
        return setting["value"]
    else:
        # Default to True if setting is not found
        settings_collection.insert_one({"setting": "location_restriction", "value": True})
        return True

def set_location_restriction(value):
    settings_collection.update_one(
        {"setting": "location_restriction"},
        {"$set": {"value": value}},
        upsert=True
    )

def attendance_stats_page():
    st.title('Attendance Statistics')
    
    # Authentication
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.sidebar.subheader("Admin Login")
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if authenticate(username, password):
                st.session_state.authenticated = True
                st.rerun
            else:
                st.sidebar.error("Invalid username or password")
        return

    # Logout button
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()
    
    # Admin actions
    admin_action = st.selectbox('Select Action', ['View Attendance', 'Update Records', 'Visualize Attendance', 'Manage Location Restriction'])
    
    if admin_action == 'View Attendance':
        df = load_attendance()
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Date range selection
        col1, col2 = st.columns(2)
        start_date = pd.to_datetime(col1.date_input("Start Date", min_value=df['Date'].min().date(), max_value=df['Date'].max().date(), value=df['Date'].min().date()))
        end_date = pd.to_datetime(col2.date_input("End Date", min_value=df['Date'].min().date(), max_value=df['Date'].max().date(), value=df['Date'].max().date()))
        
        # Employee selection
        employees = ['All'] + list(df['Name'].unique())
        selected_employee = st.selectbox('Select Employee', employees)
        
        if selected_employee == 'All':
            stats_df = calculate_attendance_stats(df, selected_employee, 'All')
            st.dataframe(stats_df)

            # Export as CSV
            if st.button('Export as CSV'):
                csv = stats_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="attendance_stats.csv",
                    mime="text/csv"
                )
        else:
            # Attribute selection
            available_attributes = ['Hours Present', 'Arrival Time', 'Leaving Time', 'Days Present']
            selected_attributes = st.multiselect('Select Attributes', available_attributes, default=['Hours Present'])
            
            if not selected_attributes:
                st.error('Please select at least one attribute.')
                return
            
            # View attendance
            if st.button('View Attendance'):
                result_df = view_attendance(df, start_date, end_date, selected_employee, selected_attributes)
                st.dataframe(result_df)
                
            # Export as CSV
            if st.button('Export as CSV'):
                result_df = view_attendance(df, start_date, end_date, selected_employee, selected_attributes)
                csv = result_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="attendance_stats.csv",
                    mime="text/csv"
                )
    
    elif admin_action == 'Update Records':
        update_attendance_page()
    
    elif admin_action == 'Visualize Attendance':
        df = load_attendance()
        df['Date'] = pd.to_datetime(df['Date'])
        visualize_attendance(df)

    elif admin_action == 'Manage Location Restriction':
        st.title("Manage Location Restriction")
        location_restriction = st.checkbox("Enable Location Restriction", value=get_location_restriction())

        if st.button("Update Restriction"):
            set_location_restriction(location_restriction)
            st.success(f"Location restriction {'enabled' if location_restriction else 'disabled'} successfully.")

def attendance_logging_page():
    st.title('Employee Attendance System')

    # Get user's location
    location = get_geolocation()

    location_restriction = get_location_restriction()

    if location_restriction:
        if location is None:
            st.warning('Waiting for location data...')
            return

        lat, lon = location['coords']['latitude'], location['coords']['longitude']

        if not is_within_allowed_location(lat, lon):
            st.error('You are not within the allowed location to log your attendance.')
            return

    employees = ['Muzamil Javeed', 'Asim Sumair', 'Arsalan Ahmad', 'Mohammad Unaib', 'Talib Shabir', 'Syed Owais Bashir', 'Suhail Ulfath', 'Owais Mir', 'Numair', 'Jehangir','Ingila Irshad', 'Zaineb Khursheed', 'Tabarak','Syed Muntazir','Najma Fayaz','Afsa Imtiyaz','Bisma Nisar','Furkan shabir','Rafiya jan','Rehana Rashid ','Mufazila']
    selected_employee = st.selectbox('Select Employee', employees)

    current_date = date.today()
    
    # Use Streamlit session state to store data
    if 'df' not in st.session_state:
        st.session_state.df = load_attendance()

    # Filter for today's entries for the selected employee
    today_entries = st.session_state.df[(st.session_state.df['Name'] == selected_employee) & (st.session_state.df['Date'] == current_date.strftime('%Y-%m-%d'))]

    if today_entries.empty:
        # No entry for today, show arrival log button and camera input
        st.write("Please take a photo for attendance verification:")
        img_file = st.camera_input("Take a picture")

        if img_file is not None:
            if st.button('Log Arrival Time'):
                success, message = log_arrival(selected_employee, current_date, img_file)
                if success:
                    st.session_state.df = load_attendance()  # Reload the updated dataframe
                    st.success(message)
                    st.rerun()  # Force Streamlit to rerun the script
                else:
                    st.error(message)
    else:
        # Entry exists for today
        latest_entry = today_entries.iloc[-1]  # Get the latest entry for today
        if pd.isna(latest_entry['Leaving Time']):
            # Arrival logged, but leaving time not logged
            st.info(f"Arrival time logged at: {latest_entry['Arrival Time']}")

            st.write("Please take a photo for attendance verification:")
            img_file = st.camera_input("Take a picture")

            if img_file is not None:
                if st.button('Log Leaving Time'):
                    success, message = log_leaving(selected_employee, current_date, img_file)
                    if success:
                        st.session_state.df = load_attendance()  # Reload the updated dataframe
                        st.success(message)
                        st.rerun()  # Force Streamlit to rerun the script
                    else:
                        st.error(message)
        else:
            # Both arrival and leaving times are logged
            st.info(f"You have already logged both arrival ({latest_entry['Arrival Time']}) and leaving ({latest_entry['Leaving Time']}) times for today.")

    # Display all employees' attendance records for today without ID, Arrival Photo, and Leaving Photo
    st.write("Current Attendance Records for Today:")
    today_all_entries = st.session_state.df[st.session_state.df['Date'] == current_date.strftime('%Y-%m-%d')]
    if not today_all_entries.empty:
        today_all_entries = today_all_entries.drop(columns=['_id', 'Arrival Photo', 'Leaving Photo'])
    st.dataframe(today_all_entries)

def main():
    st.sidebar.title('Navigation')
    page = st.sidebar.radio('Go to', ['Attendance Logging', 'Attendance Statistics'])
    
    if page == 'Attendance Logging':
        attendance_logging_page()
    elif page == 'Attendance Statistics':
        attendance_stats_page()

if __name__ == '__main__':
    main()
