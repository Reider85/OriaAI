import re

# Test the regex with unfenced JSON
TOOL_CALL_REGEX = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```|(\{[\s\S]*?\})",
    re.DOTALL,
)

response = """
        I need to search for information.
        
        {
          "tool": "web_search",
          "arguments": {
            "query": "current weather in London"
          }
        }
        """

print("Response:")
print(repr(response))
print("\nResponse with visible characters:")
print(repr(response.encode('unicode-escape')))

matches = TOOL_CALL_REGEX.findall(response)
print(f"\nMatches: {matches}")
if matches:
    match = matches[0]
    json_str = match[0] if match[0] else match[1]
    print(f"\nMatched JSON string (length {len(json_str)}):")
    print(repr(json_str))
    print("\nJSON string with visible characters:")
    print(repr(json_str.encode('unicode-escape')))
    
    # Check if it's valid JSON
    try:
        import json
        parsed = json.loads(json_str)
        print(f"\nParsed successfully: {parsed}")
    except Exception as e:
        print(f"\nJSON Error: {e}")
        print("Let's try to fix it...")
        # Add missing closing brace
        fixed_json = json_str.strip() + "}"
        print(f"Fixed JSON: {repr(fixed_json)}")
        try:
            parsed = json.loads(fixed_json)
            print(f"Fixed parsed: {parsed}")
        except Exception as e2:
            print(f"Still failed: {e2}")