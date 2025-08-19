"""
calendar_integration.py
========================

This module provides a simple Flask application exposing two REST endpoints
that can be used by an ElevenLabs Conversational AI agent to check
availability in a Google Calendar and to book meetings.  The endpoints
`/get_available_slots` and `/book_meeting` can be configured as server tools
within ElevenLabs' dashboard, allowing the agent to call them during
conversations.

The application makes use of the Google Calendar API via a service
account.  To use this code you must create a Google Cloud project, enable
the Google Calendar API, and generate a service account key file.  The
service account must have at least read access (for free/busy queries)
and write access (for event insertion) to the calendar you wish to manage.

Configuration is controlled through environment variables:

```
GOOGLE_APPLICATION_CREDENTIALS  Path to the service account JSON file.
GOOGLE_CALENDAR_ID             The ID of the calendar to query and
                               insert events into.  For a primary
                               calendar, this is typically the user's
                               email address.
DEFAULT_TIMEZONE               Time zone for date calculations (e.g. "Europe/Stockholm").
```

Install dependencies with:

```
pip install flask google-api-python-client google-auth-httplib2 google-auth-oauthlib pytz
```

Start the server locally with:

```
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
export GOOGLE_CALENDAR_ID=your_calendar_id@group.calendar.google.com
export DEFAULT_TIMEZONE=Europe/Stockholm
python calendar_integration.py
```

The server will listen on port 5000 by default.

Endpoints
---------

**GET /get_available_slots**

Checks for free time slots between a start and end time.  Call this
endpoint with query parameters:

- `start` (ISO 8601 datetime, required) – the beginning of the search window.
- `end` (ISO 8601 datetime, required) – the end of the search window.
- `duration_minutes` (int, optional, default=60) – desired meeting duration.

It returns a JSON object with a list of suggested slot objects, each
containing a `start` and `end` ISO timestamp.  The algorithm finds
free periods based on the calendar's busy times and splits them into
intervals at least as long as `duration_minutes`.

**POST /book_meeting**

Creates an event in the configured calendar.  Provide a JSON body
containing:

- `start` (ISO 8601 datetime, required) – start time of the meeting.
- `end` (ISO 8601 datetime, required) – end time of the meeting.
- `summary` (string, optional) – event title.
- `description` (string, optional) – additional details for attendees.
- `attendees` (list of strings, optional) – email addresses of attendees.

The endpoint returns the created event's summary, start and end times,
and a link to the event in Google Calendar.

Note
----

This script is intended to be an example implementation.  You may
customize the logic for availability and event creation according to
your business rules.  For example, you could add validation to
enforce working hours, automatically assign meeting locations or
conference links, or integrate with additional services.

"""

import os
import datetime
from typing import List, Dict

from flask import Flask, request, jsonify
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz


def get_calendar_service():
    """Create a Google Calendar API service using a service account."""
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.exists(credentials_path):
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS environment variable must point to a valid JSON credentials file."
        )
    scopes = ["https://www.googleapis.com/auth/calendar"]
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=scopes
    )
    service = build("calendar", "v3", credentials=credentials)
    return service


def parse_iso(dt_str: str, tz: pytz.timezone) -> datetime.datetime:
    """Parse an ISO 8601 datetime string into a timezone-aware datetime."""
    # Use fromisoformat which supports most ISO strings but not necessarily Z suffix
    dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        # Assume naive datetimes are in the provided timezone
        dt = tz.localize(dt)
    else:
        # Convert to the provided timezone
        dt = dt.astimezone(tz)
    return dt


def compute_free_slots(busy_periods: List[Dict[str, str]], start: datetime.datetime, end: datetime.datetime, duration: datetime.timedelta) -> List[Dict[str, str]]:
    """Given busy periods, compute free time slots of at least the specified duration."""
    free_slots: List[Dict[str, str]] = []
    current_start = start
    for period in busy_periods:
        busy_start = parse_iso(period["start"], start.tzinfo)
        busy_end = parse_iso(period["end"], start.tzinfo)
        if busy_start > current_start:
            # There is a free period between current_start and busy_start
            free_duration = busy_start - current_start
            if free_duration >= duration:
                free_slots.append({
                    "start": current_start.isoformat(),
                    "end": busy_start.isoformat(),
                })
        # Move current_start past this busy block if it overlaps
        if busy_end > current_start:
            current_start = busy_end
    # Check for free time after the last busy period
    if end > current_start:
        free_duration = end - current_start
        if free_duration >= duration:
            free_slots.append({
                "start": current_start.isoformat(),
                "end": end.isoformat(),
            })
    return free_slots


def query_free_busy(service, calendar_id: str, start: datetime.datetime, end: datetime.datetime) -> List[Dict[str, str]]:
    """Query the Google Calendar API for busy periods within the specified interval."""
    body = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "items": [{"id": calendar_id}],
    }
    freebusy_result = service.freebusy().query(body=body).execute()
    busy_periods = freebusy_result["calendars"][calendar_id].get("busy", [])
    # Sort busy periods by start time
    busy_periods.sort(key=lambda x: x["start"])
    return busy_periods


app = Flask(__name__)

@app.route("/get_available_slots", methods=["GET"])
def get_available_slots():
    """Endpoint to return available slots between start and end times."""
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        return jsonify({"error": "GOOGLE_CALENDAR_ID environment variable is not set"}), 500
    tz_name = os.environ.get("DEFAULT_TIMEZONE", "UTC")
    tz = pytz.timezone(tz_name)
    start_str = request.args.get("start")
    end_str = request.args.get("end")
    duration_minutes = request.args.get("duration_minutes", default=60, type=int)
    if not start_str or not end_str:
        return jsonify({"error": "start and end query parameters are required"}), 400
    try:
        start = parse_iso(start_str, tz)
        end = parse_iso(end_str, tz)
    except Exception as e:
        return jsonify({"error": f"Invalid datetime format: {e}"}), 400
    if start >= end:
        return jsonify({"error": "start must be before end"}), 400
    duration = datetime.timedelta(minutes=duration_minutes)
    try:
        service = get_calendar_service()
        busy_periods = query_free_busy(service, calendar_id, start, end)
        free_slots = compute_free_slots(busy_periods, start, end, duration)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"free_slots": free_slots})


@app.route("/book_meeting", methods=["POST"])
def book_meeting():
    """Endpoint to create a meeting in the calendar."""
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        return jsonify({"error": "GOOGLE_CALENDAR_ID environment variable is not set"}), 500
    tz_name = os.environ.get("DEFAULT_TIMEZONE", "UTC")
    tz = pytz.timezone(tz_name)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    start_str = data.get("start")
    end_str = data.get("end")
    summary = data.get("summary", "Meeting")
    description = data.get("description", "")
    attendees_emails = data.get("attendees", [])
    if not start_str or not end_str:
        return jsonify({"error": "start and end fields are required"}), 400
    try:
        start = parse_iso(start_str, tz)
        end = parse_iso(end_str, tz)
    except Exception as e:
        return jsonify({"error": f"Invalid datetime format: {e}"}), 400
    if start >= end:
        return jsonify({"error": "start must be before end"}), 400
    try:
        service = get_calendar_service()
        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end.isoformat(), "timeZone": tz_name},
        }
        if attendees_emails:
            event_body["attendees"] = [{"email": email} for email in attendees_emails]
        created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        response = {
            "id": created_event.get("id"),
            "htmlLink": created_event.get("htmlLink"),
            "summary": created_event.get("summary"),
            "start": created_event.get("start"),
            "end": created_event.get("end"),
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(response), 201


if __name__ == "__main__":
    # Determine host/port from environment variables or defaults
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port)