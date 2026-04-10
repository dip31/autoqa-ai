import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

PROMPT_TEMPLATE = """
You are a QA risk analysis expert. Analyze the provided input and predict bug risk levels.

Input Type: {input_type}
Content:
{content}

Analyze and identify modules/components/areas and their risk levels.

Return ONLY valid JSON with:
- overall_risk_score: (0-100)
- risk_summary: brief explanation
- modules: list of objects with:
  - name: module/component name
  - risk_level: "high" | "medium" | "low"
  - risk_score: (0-100)
  - reasons: list of reasons for this risk level
  - recommendations: list of recommendations
- high_risk_count: number of high risk modules
- medium_risk_count: number of medium risk modules
- low_risk_count: number of low risk modules
- risk_reduction_plan: object with:
  - immediate_actions: list of objects with (priority: 1-5, action, impact, effort: low/medium/high)
  - short_term_actions: list of objects with (priority: 1-5, action, impact, effort: low/medium/high)
  - long_term_actions: list of objects with (priority: 1-5, action, impact, effort: low/medium/high)
  - estimated_risk_after_reduction: number (0-100, estimated overall risk score after applying all suggestions)

Return ONLY valid JSON, no extra text.
"""

def predict_risk(content: str, input_type: str = "general") -> dict:
    prompt = PROMPT_TEMPLATE.format(content=content, input_type=input_type)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
