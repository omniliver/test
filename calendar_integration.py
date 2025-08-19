from flask import Flask, jsonify, request, Response

app = Flask(__name__)

SECRET_TOKEN = "calendar_secret"

tools = [
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
                "attendees": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["start", "end", "summary"]
        }
    }
]

def check_auth():
    auth_header = request.headers.get("Authorization", "")
    return auth_header == f"Bearer {SECRET_TOKEN}"

@app.route("/")
@app.route("/mcp/tools")
@app.route("/sse")
def serve_tools():
    if not check_auth():
        return Response("Unauthorized", status=403)
    return Response(jsonify(tools).get_data(as_text=True), mimetype="application/json")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
