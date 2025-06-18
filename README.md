AIIoTS-Aiml-Attendance-System
Welcome to the AIIoTS-Aiml-Attendance-System! This project provides an efficient solution for managing attendance through two main modules: one for students and one for administrators. The system not only records attendance but also offers insights into attendance patterns and statistics.

📋 Table of Contents
Introduction
Features
Modules Overview
Technology Stack
Installation
Usage
Contributing
License
📖 Introduction
The AIIoTS-Aiml-Attendance-System is a dual-module application designed for students and administrators. It simplifies attendance management and provides actionable insights for administrators to track patterns and statistics. This system is suitable for educational institutions, workplaces, or organizations looking for a streamlined attendance process.

✨ Features
Student Module:

Allows students to mark attendance through a user-friendly interface.
Admin Module:

Secure login for administrators to monitor attendance.
Provides detailed attendance patterns and statistical analysis.
Attendance Analytics:

Highlights trends and absenteeism rates.
Modular Design:

Separate modules for employers and administrators ensure clarity and security
📂 Modules Overview
1. main.py (Student Module)
This file handles student interactions with the system. Students can:

Mark their attendance.
Receive a confirmation of their submission.
2. admin.py (Admin Module)
This file is designed for administrators to:

Log in with a secure username and password.
Access attendance records.
Analyze patterns and statistics for better decision-making.
🛠️ Technology Stack
Programming Language: Python
Framework: FastApi
Database: Mongo db compass
Visualization: Matplotlib, Seaborn
Tools/Libraries: NumPy, Pandas, Matplolib
🚀 Installation
1:Clone the Repository
git clone https://github.com/muzamil-javeed/AIIoTS-Aiml-Attendance-System.git
cd Aiiots-Attendance
2:Install Dependencies
pip install -r requirements.txt
3:Set Up Database
Download mongo compass and connect the above code with your database
4:Run the Modules
To launch the employer Module
python main.py
5:To launch the Admin Module:
python admin.py
Access the system through your browser or terminal.
📚 Usage
Employer Workflow
Run the main.py file.
Employers enter their details to mark attendance.
Admin Workflow
Run the admin.py file.
Admin logs in using a secure username and password.
Admin views attendance data, tracks patterns, and analyzes statistics.
🤝 Contributing
We welcome contributions! If you'd like to improve the system:

Fork the repository.
Create a feature branch: git checkout -b feature/your-feature-name.
Commit your changes: git commit -m "Add some feature".
Push to the branch: git push origin feature/your-feature-name.
Open a pull request.
📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
