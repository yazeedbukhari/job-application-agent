BASE_PROMPT = """Extract job details from the provided input.
Return only a JSON object with keys exactly:
- title
- location
- company
- salary range
- hiring manager
- department
If any of the keys don't have a proper value, set their value to an empty string.

IMPORTANT OUTPUT RULES:
- Respond with a single JSON object only.
- Do not include any prose, explanations, or code fences.
- Every value must be a string.

For location, return only the city.
"""

