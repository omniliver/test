from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pytz
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)

# Load environment variables
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")

# Load Google credentials from environment variable (JSON string)
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
creds = service_account.Credentials.from_service_account_info(json.loads(creds_json), scopes=["https://www.googleapis.com/auth/calendar"])
service = build("calendar", "v3", credentials=creds)

@app.route("/get_available_slots", methods=["GET"])
def get_available_slots():
    start = request.args.get("start")
    end = request.args.get("end")
    duration = int(request.args.get("duration_minutes", 30))

    events_result = service.freebusy().query(body={
        "timeMin": start,
        "timeMax": end,
        "timeZone": TIMEZONE,
        "items": [{"id": CALENDAR_ID}]
    }).execute()

    busy_times = events_result["calendars"][CALENDAR_ID]["busy"]
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    slots = []
    current = start_dt

    while current + timedelta(minutes=duration) <= end_dt:
        candidate_start = current
        candidate_end = current + timedelta(minutes=duration)
        overlap = False
        for busy in busy_times:
            busy_start = datetime.fromisoformat(busy["start"].replace("Z", "+00:00"))
            busy_end = datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
            if candidate_start < busy_end and candidate_end > busy_start:
                overlap = True
                break
        if not overlap:
            slots.append({"start": candidate_start.isoformat(), "end": candidate_end.isoformat()})
        current += timedelta(minutes=duration)
    return jsonify(slots)

@app.route("/book_meeting", methods=["POST"])
def book_meeting():
    data = request.json
    event = {
        "summary": data.get("summary", "Meeting"),
        "description": data.get("description", ""),
        "start": {"dateTime": data["start"], "timeZone": TIMEZONE},
        "end": {"dateTime": data["end"], "timeZone": TIMEZONE},
        "attendees": [{"email": a} for a in data.get("attendees", [])]
    }
    created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return jsonify(created)

# MCP manifest endpoint
@app.route("/mcp/tools", methods=["GET"])
def mcp_tools():
    return jsonify({
        "tools": [
            {
                "name": "get_available_slots",
                "description": "Check free slots in Google Calendar",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "format": "date-time"},
                        "end": {"type": "string", "format": "date-time"},
                        "duration_minutes": {"type": "integer"}
                    },
                    "required": ["start", "end", "duration_minutes"]
                }
            },
            {
                "name": "book_meeting",
                "description": "Create a new meeting in Google Calendar",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string", "format": "date-time"},
                        "end": {"type": "string", "format": "date-time"},
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                        "attendees": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["start", "end", "summary"]
                }
            }
        ]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
