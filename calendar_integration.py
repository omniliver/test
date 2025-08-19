import os, json
from datetime import datetime, timedelta
import pytz

from googleapiclient.discovery import build
from google.oauth2 import service_account

# --- MCP server ---
from fastmcp import FastMCP

# ---- Google Calendar setup ----
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")

creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
creds = service_account.Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=["https://www.googleapis.com/auth/calendar"],
)
service = build("calendar", "v3", credentials=creds)

mcp = FastMCP("calendar-bridge")

@mcp.tool
def get_available_slots(start: str, end: str, duration_minutes: int):
    """
    Check free slots in Google Calendar.
    start/end: ISO 8601 datetime strings (e.g. 2025-08-20T12:00:00Z)
    duration_minutes: length of each slot to check.
    """
    # Freebusy query
    result = service.freebusy().query(body={
        "timeMin": start,
        "timeMax": end,
        "timeZone": TIMEZONE,
        "items": [{"id": CALENDAR_ID}]
    }).execute()

    busy_times = result["calendars"][CALENDAR_ID]["busy"]
    def parse(dt): return datetime.fromisoformat(dt.replace("Z", "+00:00"))

    start_dt = parse(start)
    end_dt = parse(end)

    slots = []
    current = start_dt
    delta = timedelta(minutes=duration_minutes)

    while current + delta <= end_dt:
        candidate_start = current
        candidate_end = current + delta
        overlap = False
        for b in busy_times:
            b_start = parse(b["start"])
            b_end = parse(b["end"])
            if candidate_start < b_end and candidate_end > b_start:
                overlap = True
                break
        if not overlap:
            slots.append({
                "start": candidate_start.isoformat(),
                "end": candidate_end.isoformat()
            })
        current += delta

    return {"slots": slots}

@mcp.tool
def book_meeting(start: str, end: str, summary: str,
                 description: str = "", attendees: list[str] = []):
    """
    Create a new meeting in Google Calendar.
    """
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start, "timeZone": TIMEZONE},
        "end": {"dateTime": end, "timeZone": TIMEZONE},
        "attendees": [{"email": a} for a in attendees],
    }
    created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return {"id": created.get("id"), "link": created.get("htmlLink")}

if __name__ == "__main__":
    # Run as a **Streamable HTTP** MCP server at /mcp (ideal for ElevenLabs)
    port = int(os.getenv("PORT", "10000"))
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
