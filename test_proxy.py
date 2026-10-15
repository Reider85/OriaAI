import requests
import json

url = "http://host.docker.internal:8000/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer dev-key-12345"
}
data = {
    "model": "glm-4.5-flash",
    "messages": [{"role": "user", "content": "hello test"}],
    "max_tokens": 5
}

try:
    response = requests.post(url, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")