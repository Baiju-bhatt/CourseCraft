# Flask App Layout

Minimal Flask app scaffold.

Quick start

```bash
# create venv (macOS/Linux)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

App structure

- app/ - application package
  - __init__.py - factory
  - routes.py - blueprints/routes
  - templates/ - Jinja2 templates
  - static/ - static assets (css/js/images)
- run.py - development entrypoint
- requirements.txt

Features
	•	User signup and login with JWT authentication
	•	Profile management (view & update)
	•	AI-powered course generation
	•	RESTful API endpoints for frontend integration
	•	Secure token-based authentication
	•	JSON-based request/response handling

⸻

Tech Stack
	•	Backend: Python 3, Flask
	•	Database: SQLite (default) / can configure PostgreSQL/MySQL
	•	Authentication: JWT (JSON Web Tokens)
	•	AI: Integrated AI module for course generation
	•	Testing: Postman / any API client

⸻

Project Structure

project_root/
│
├── app/
│   ├── __init__.py
│   ├── routes/
│   │   ├── auth.py          # Login and Signup routes
│   │   ├── profile.py       # Profile routes
│   │   └── course.py        # Course generation routes
│   ├── models.py            # User and Course models
│   └── utils.py             # Helper functions (JWT, hashing, etc.)
│
├── venv/                    # Virtual environment
├── requirements.txt         # Python dependencies
├── run.py                   # Flask app runner
└── README.md


⸻

Setup Instructions

1. Clone the repository

git clone <your-repo-url>
cd <project-root>

2. Create a virtual environment

Mac / Linux:

python3 -m venv venv
source venv/bin/activate

3. Install dependencies

pip install -r requirements.txt

Note: Keep your JWT_SECRET_KEY secure. This is used to sign access tokens.

5. Run the Flask server

python run.py

The backend will run at: http://127.0.0.1:5000/

⸻

API Endpoints

Authentication
  Header:
  Content-Type :  application/json
	•	POST /signup – Register a new user
	•	Body:

  {
    "full_name": "Mohammad Umair",
    "email": "umair11@example.com",
    "password": "mypassword123",
    "role": "learner"
  }


	POST /login – Login and get JWT token
	•	Body:

  {
    "email": "umair@example.com",
    "password": "yourpassword"
  }


	•	Response includes:

  {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc3MDk0NTYyMywianRpIjoiOGZiZDZlMmUtNzQwNC00NDAyLTk3ODEtMWIwMDJlYzkwZWY4IiwidHlwZSI6ImFjY2VzcyIsInN1YiI6IjIiLCJuYmYiOjE3NzA5NDU2MjMsImNzcmYiOiI5ZGVjODgyZi1kYjUxLTQxZWItYmMyNC00Y2M1OTA2MWE1ZTciLCJleHAiOjE3NzA5NDY1MjN9.XPloKBVtUqtm07TMRi3hVPcuK0nFkx76xN7U_TXSK4I",
      "message": "Login successful",
      "user": {
          "email": "umair11@example.com",
          "full_name": "Mohammad Umair",
          "role": "learner"
      }
  }

Profile
	•	http://127.0.0.1:5000/login
	•	Headers:

Authorization: Bearer <jwt_token>
Content-Type: application/json


	•	Body:

    No body required



⸻

Testing with Postman
	1.	Signup & Login to get your JWT token.
	2.	Copy the token and add it in the Authorization header for protected endpoints:

Authorization: Bearer <token>


	3.	Test Profile and Course Generation endpoints with JSON bodies as shown above.

⸻

Notes
	•	Ensure JWT token is stored securely on the frontend (LocalStorage, SessionStorage, or HttpOnly Cookie).
	•	Use Content-Type: application/json for all POST/PUT requests.
	•	Handle token expiration properly in your frontend to avoid 401/422 errors.

