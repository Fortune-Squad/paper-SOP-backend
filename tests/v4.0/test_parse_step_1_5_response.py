"""
Debug script to analyze Step 1.5 AI response format
"""
import re

# Read the latest AI response from the log
with open("projects/physics-driven-compressed-sens-9d772ae8/logs/step_1_5_ai_conversation.md", "r", encoding="utf-8") as f:
    content = f.read()

# Extract the AI response section
response_pattern = r'### AI 响应 \(Response\)\s*\n\s*```\s*\n(.*?)\n\s*```\s*\n\s*=+'
match = re.search(response_pattern, content, re.DOTALL)

if not match:
    print("Could not find AI response in log")
    exit(1)

ai_response = match.group(1)

print("=" * 80)
print("AI Response Analysis")
print("=" * 80)
print(f"Total length: {len(ai_response)} characters")
print(f"\nFirst 500 characters:")
print(repr(ai_response[:500]))
print(f"\nLast 500 characters:")
print(repr(ai_response[-500:]))

# Try to find document delimiters
doc1_start = re.search(r'---DOCUMENT_1:', ai_response)
doc1_end = re.search(r'---END_DOCUMENT_1---', ai_response)
doc2_start = re.search(r'---DOCUMENT_2:', ai_response)
doc2_end = re.search(r'---END_DOCUMENT_2---', ai_response)

print(f"\n\nDocument delimiter search:")
print(f"  DOCUMENT_1 start: {doc1_start is not None} (pos: {doc1_start.start() if doc1_start else 'N/A'})")
print(f"  DOCUMENT_1 end: {doc1_end is not None} (pos: {doc1_end.start() if doc1_end else 'N/A'})")
print(f"  DOCUMENT_2 start: {doc2_start is not None} (pos: {doc2_start.start() if doc2_start else 'N/A'})")
print(f"  DOCUMENT_2 end: {doc2_end is not None} (pos: {doc2_end.start() if doc2_end else 'N/A'})")

# Check for code block wrapping
if ai_response.startswith('```'):
    print(f"\n\nAI response starts with code block marker")
    first_newline = ai_response.find('\n')
    print(f"First line: {repr(ai_response[:first_newline])}")

    # Find closing code block
    closing_pattern = r'\n```\s*$'
    closing_match = re.search(closing_pattern, ai_response)
    if closing_match:
        print(f"Closing code block found at position: {closing_match.start()}")
        print(f"Closing line: {repr(ai_response[closing_match.start():])}")
    else:
        print("No closing code block found")
        # Check alternative patterns
        if ai_response.endswith('```'):
            print("Response ends with ``` (no newline)")
        if ai_response.endswith('```\n'):
            print("Response ends with ```\\n")

# Test code block stripping patterns
print("\n\nTesting code block stripping patterns:")
patterns = [
    r'^```(?:yaml|markdown)?\s*\n(.*)\n```$',  # Standard
    r'^```(?:yaml|markdown)?\s*\n(.*)```$',     # No final newline
    r'^```(?:yaml|markdown)?\s*(.*)\n```$',     # No initial newline
    r'^```(?:yaml|markdown)?\s*(.*)```$'        # Minimal
]

for i, pattern in enumerate(patterns, 1):
    match = re.match(pattern, ai_response.strip(), re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        print(f"  Pattern {i}: MATCHED (extracted {len(extracted)} chars)")
    else:
        print(f"  Pattern {i}: NO MATCH")
