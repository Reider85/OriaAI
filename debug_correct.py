# Let's manually construct the correct JSON
correct_json = '''{
  "tool": "web_search",
  "arguments": {
    "query": "current weather in London"
  }
}'''

print("Correct JSON:")
print(repr(correct_json))

# Test with correct JSON
import re

TOOL_CALL_REGEX = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```|(\{[\s\S]*?\})",
    re.DOTALL,
)

response = f"""
I need to search for information.

{correct_json}
"""

print("\nResponse with correct JSON:")
print(repr(response))

matches = TOOL_CALL_REGEX.findall(response)
print(f"\nMatches: {matches}")
if matches:
    match = matches[0]
    json_str = match[0] if match[0] else match[1]
    print(f"\nMatched JSON string: {repr(json_str)}")
    
    # Check if it's valid JSON
    try:
        import json
        parsed = json.loads(json_str)
        print(f"\nParsed successfully: {parsed}")
    except Exception as e:
        print(f"\nJSON Error: {e}")