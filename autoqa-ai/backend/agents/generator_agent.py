import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT_TEMPLATE = """
You are an expert QA engineer. Generate comprehensive test cases based on the following input.

Requirement / User Story / Feature:
{requirement}

Generate test cases covering ALL of:
- Positive test cases (happy path)
- Negative test cases (invalid inputs, error scenarios)
- Boundary test cases (edge values, limits)
- UI test cases (if applicable)

Return ONLY valid JSON with:
- positive_tests: list of objects (id, title, preconditions, steps, expected_result)
- negative_tests: list of objects (id, title, preconditions, steps, expected_result)
- boundary_tests: list of objects (id, title, preconditions, steps, expected_result)
- ui_tests: list of objects (id, title, preconditions, steps, expected_result)
- total_count: total number of test cases generated

Return ONLY valid JSON, no extra text.
"""

def generate_testcases(requirement: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(requirement=requirement)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
