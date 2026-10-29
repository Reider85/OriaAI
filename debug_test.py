response = """
        I need to search for information.
        
        {
          "tool": "web_search",
          "arguments": {
            "query": "current weather in London"
          }
        }
        """

print("Raw response:")
print(repr(response))
print("\nLines:")
for i, line in enumerate(response.split('\n'), 1):
    print(f"{i:2d}: {repr(line)}")