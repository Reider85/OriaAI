import requests

url = "http://127.0.0.1:8010/sessions/new/stream"
headers = {
    "Accept": "text/event-stream"
}

try:
    response = requests.get(url, headers=headers, stream=True)
    print(f"Status Code: {response.status_code}")
    
    for line in response.iter_lines():
        if line:
            print(f"Stream: {line.decode('utf-8')}")
except Exception as e:
    print(f"Error: {e}")