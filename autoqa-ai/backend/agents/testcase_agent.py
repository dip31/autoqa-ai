import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT_TEMPLATE = """
You are an expert QA engineer. Analyze the following manual test case and provide a detailed review.

Test Case:
{testcase}

Evaluate and return a JSON response with:
- score: (0-100 quality score)
- issues: list of issues found (completeness, clarity, missing edge cases, ambiguity)
- suggestions: list of improvement suggestions
- improved_testcase: a rewritten, improved version of the test case

Return ONLY valid JSON, no extra text.
"""

def review_testcase(testcase: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(testcase=testcase)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
