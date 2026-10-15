#!/usr/bin/env python3
"""Test script to verify that the UI is loading the correct AGENT_SERVICE_URL from .env"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# First, check if .env exists and has the value
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file, 'r') as f:
        for line in f:
            if "AGENT_SERVICE_URL" in line:
                print(f"Found in .env: {line.strip()}")
                break
else:
    print("ERROR: .env file not found")

# Check current environment before importing app.py
current_agent_url = os.getenv("AGENT_SERVICE_URL", "NOT SET")
print(f"Current env AGENT_SERVICE_URL (before import): {current_agent_url}")

# Import app.py to trigger load_dotenv
try:
    print("Importing app.py...")
    from llm_client.ui import app
    print("SUCCESS: app.py imported")
except ImportError as e:
    print(f"ERROR: Failed to import app.py: {e}")
    sys.exit(1)

# Check current environment after importing app.py
current_agent_url_after = os.getenv("AGENT_SERVICE_URL", "NOT SET")
print(f"Current env AGENT_SERVICE_URL (after import): {current_agent_url_after}")

try:
    from llm_client.ui.chat import agent_service_url
    
    # Check what URL is being returned
    url = agent_service_url()
    print(f"agent_service_url() returned: {url}")
    
    # Check if it matches the .env value
    expected_url = os.getenv("AGENT_SERVICE_URL", "")
    if expected_url:
        print(f"Expected from .env: {expected_url}")
        if url == expected_url:
            print("SUCCESS: UI is using the correct AGENT_SERVICE_URL from .env")
        else:
            print("FAILURE: UI URL does not match .env value")
    else:
        print("WARNING: AGENT_SERVICE_URL not set in environment")
        
    # Check if the URL points to port 8010
    if ":8010" in url:
        print("SUCCESS: URL correctly points to port 8010 (agent-service)")
    elif ":8000" in url:
        print("FAILURE: URL still points to port 8000 (OryaSecurity)")
    else:
        print(f"WARNING: URL points to unexpected port: {url}")

except ImportError as e:
    print(f"Import error: {e}")
    print("This might indicate the fix wasn't applied correctly")