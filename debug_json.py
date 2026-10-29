test_json = '''{
  "tool": "web_search",
  "arguments": {
    "query": "current weather in London"
  }
}'''

print("Test JSON:")
print(repr(test_json))

try:
    import json
    parsed = json.loads(test_json)
    print("JSON is valid!")
    print("Parsed:", parsed)
except Exception as e:
    print("JSON Error:", e)

# Let's also test the exact string from the test
test_response = """        I need to search for information.
        
        {
          "tool": "web_search",
          "arguments": {
            "query": "current weather in London"
          }
        }
        """

print("\n" + "="*50)
print("Extracting JSON from test response...")

# Extract the JSON part - find complete JSON object
lines = test_response.split('\n')
json_start = None
json_end = None

for i, line in enumerate(lines):
    line_stripped = line.strip()
    if line_stripped.startswith('{') and json_start is None:
        json_start = i
    elif line_stripped.endswith('}') and json_start is not None:
        json_end = i
        break

if json_start is not None and json_end is not None:
    extracted_json = '\n'.join(lines[json_start:json_end+1])
    print(f"Found JSON from line {json_start+1} to {json_end+1}")
    print("Extracted lines:")
    for j in range(json_start, json_end+1):
        print(f"  {j+1:2d}: {repr(lines[j])}")
else:
    print("No complete JSON object found")
    extracted_json = ""
print("Extracted JSON:")
print(repr(extracted_json))

try:
    parsed = json.loads(extracted_json)
    print("Extracted JSON is valid!")
    print("Parsed:", parsed)
except Exception as e:
    print("Extracted JSON Error:", e)