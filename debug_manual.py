import re

# Test the exact regex from the code
TOOL_CALL_REGEX = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\"tool\"[\s\S]*?\})\s*```|(\{[\s\S]*?\"tool\"[\s\S]*?\})",
    re.DOTALL,
)

# Test with the exact response from the test
response = """I need to search for information.

{
  "tool": "web_search",
  "arguments": {
    "query": "current weather in London"
  }
}"""

print("Response:")
print(repr(response))

matches = TOOL_CALL_REGEX.findall(response)
print(f"\nMatches: {matches}")

if matches:
    for i, match in enumerate(matches):
        print(f"\nMatch {i}: {match}")
        for j, part in enumerate(match):
            print(f"  Part {j}: {repr(part)}")

# Let's also try to find all JSON objects manually
print("\nManual search for {...}:")
json_pattern = r"\{[\s\S]*?\}"
manual_matches = re.findall(json_pattern, response)
for i, match in enumerate(manual_matches):
    print(f"Manual match {i}: {repr(match)}")
    
    # Try to parse each match
    try:
        import json
        parsed = json.loads(match)
        print(f"  Parsed: {parsed}")
    except Exception as e:
        print(f"  Error: {e}")