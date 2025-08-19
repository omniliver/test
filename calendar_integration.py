from flask import Flask, jsonify

app = Flask(__name__)

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

@app.route("/")
@app.route("/mcp/tools")
@app.route("/sse")
def serve_tools():
    return jsonify(tools)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
