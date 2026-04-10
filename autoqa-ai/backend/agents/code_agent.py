import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT_TEMPLATE = """
You are a senior software engineer and security expert. Review the following {language} code.

Code:
{code}

Analyze for:
- Code quality issues
- Bugs and logical errors
- Security vulnerabilities
- Performance problems
- Best practice violations

Return ONLY valid JSON with:
- score: (0-100 quality score)
- issues: list of objects with (line, severity: high/medium/low, type, description)
- suggestions: list of improvement suggestions
- summary: brief overall assessment
- optimized_code: a fully rewritten, optimized version of the code that fixes all issues and follows best practices

Return ONLY valid JSON, no extra text.
"""

def review_code(code: str, language: str) -> dict:
    prompt = PROMPT_TEMPLATE.format(code=code, language=language)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
