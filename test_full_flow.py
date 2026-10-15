import requests
import json
import uuid

# Generate a unique session ID
session_id = str(uuid.uuid4())

# First, create a session
chat_url = f"http://127.0.0.1:8010/sessions/{session_id}/chat"
headers = {
    "Content-Type": "application/json"
}
data = {
    "message": "Hello, can you help me?",
    "settings": {}
}

print(f"Creating session: {session_id}")
try:
    response = requests.post(chat_url, headers=headers, json=data)
    print(f"Chat Status Code: {response.status_code}")
    print(f"Chat Response: {response.text}")
except Exception as e:
    print(f"Chat Error: {e}")

# Then, stream the response
stream_url = f"http://127.0.0.1:8010/sessions/{session_id}/stream"
stream_headers = {
    "Accept": "text/event-stream"
}

print(f"\nStreaming session: {session_id}")
try:
    response = requests.get(stream_url, headers=stream_headers, stream=True)
    print(f"Stream Status Code: {response.status_code}")
    
    for line in response.iter_lines():
        if line:
            print(f"Stream: {line.decode('utf-8')}")
except Exception as e:
    print(f"Stream Error: {e}")