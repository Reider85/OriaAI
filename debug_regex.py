import re

# Test the regex
TOOL_CALL_REGEX = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```|(\{[\s\S]*?\})",
    re.DOTALL,
)

response = """
I need to search for information.

```json
{
  "tool": "web_search",
  "arguments": {
    "query": "current weather in London"
  }
}
```
"""

print("Response:", repr(response))

# Let's also test with a corrected JSON
response2 = """
I need to search for information.

```json
{
  "tool": "web_search",
  "arguments": {
    "query": "current weather in London"
  }
}
```
"""
print("\nResponse2:", repr(response2))

matches2 = TOOL_CALL_REGEX.findall(response2)
print("Matches2:", matches2)
if matches2:
    match = matches2[0]
    json_str = match[0] if match[0] else match[1]
    print("JSON string2:", repr(json_str))
    json_str = json_str.strip()
    print("JSON string stripped2:", repr(json_str))
    try:
        import json
        parsed = json.loads(json_str)
        print("Parsed2:", parsed)
    except Exception as e:
        print("Error2:", e)

print("Response:", repr(response))

matches = TOOL_CALL_REGEX.findall(response)
print("Matches:", matches)
if matches:
    match = matches[0]
    json_str = match[0] if match[0] else match[1]
    print("JSON string:", repr(json_str))
    # Clean up the JSON string
    json_str = json_str.strip()
    print("JSON string stripped:", repr(json_str))
    try:
        import json
        parsed = json.loads(json_str)
        print("Parsed:", parsed)
    except Exception as e:
        print("Error:", e)