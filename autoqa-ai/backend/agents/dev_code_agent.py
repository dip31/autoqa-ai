"""
Developer Code Agent — generates production-ready code from requirements using Gemini.
Also provides developer-focused risk prediction.
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS  = ["gemini-flash-lite-latest", "gemini-flash-latest"]

LANGUAGE_CONFIGS = {
    "python":     {"ext": "py",  "label": "Python",     "framework_hint": "Flask/FastAPI/Django"},
    "javascript": {"ext": "js",  "label": "JavaScript", "framework_hint": "Node.js/Express/React"},
    "typescript": {"ext": "ts",  "label": "TypeScript", "framework_hint": "Node.js/Express/React"},
    "java":       {"ext": "java","label": "Java",       "framework_hint": "Spring Boot/Maven"},
    "sql":        {"ext": "sql", "label": "SQL",        "framework_hint": "PostgreSQL/MySQL/SQLite"},
    "bash":       {"ext": "sh",  "label": "Shell/Bash", "framework_hint": "Linux/macOS"},
}


def _call_gemini(prompt: str) -> str:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192}
    }
    last_err = None
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            res = requests.post(url, json=payload, timeout=90)
            res.raise_for_status()
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            last_err = str(e)
    raise Exception(f"Gemini unavailable: {last_err}")


def _strip_fences(raw: str, language: str) -> str:
    """Remove markdown code fences."""
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        # take the longest part that isn't a language tag
        code_parts = [p.strip() for p in parts
                      if p.strip() and not p.strip().lower() in
                      ("python","javascript","typescript","java","sql","bash","js","ts","sh","")]
        if code_parts:
            return max(code_parts, key=len)
    return raw


def generate_code(requirements: str, language: str, tech_stack: str = "",
                  project_context: str = "") -> dict:
    """
    Generate production-ready code from requirements.
    Returns { language, title, code_content, description, filename_suggestion, metrics }
    """
    lang = language.lower()
    cfg  = LANGUAGE_CONFIGS.get(lang, {"ext": "txt", "label": language, "framework_hint": ""})

    prompt = f"""You are a Senior Software Engineer. Write clean, production-ready {cfg['label']} code.

PROJECT CONTEXT: {project_context or 'General purpose'}
TECH STACK: {tech_stack or cfg['framework_hint']}
REQUIREMENTS:
{requirements}

RULES:
1. Write COMPLETE, runnable code — not pseudocode or stubs
2. Include proper error handling and input validation
3. Add inline comments for complex logic
4. Follow {cfg['label']} best practices and conventions
5. Use meaningful variable/function/class names
6. Include type hints / type annotations where applicable
7. Structure code properly (imports → constants → classes/functions → main logic)
8. If it's a class, include __init__ and relevant methods
9. If it's an API endpoint, include request validation and proper HTTP status codes

Return ONLY clean {cfg['label']} code. No markdown fences, no explanations before or after."""

    raw  = _call_gemini(prompt)
    code = _strip_fences(raw, lang)

    # Generate filename hint
    fn_prompt = f"""Suggest a single appropriate filename (with .{cfg['ext']} extension) for this code:
Requirements: {requirements[:200]}
Return ONLY the filename, nothing else. Example: auth_service.py"""
    try:
        filename = _call_gemini(fn_prompt).strip().strip('"').split()[0]
        if not filename.endswith(f".{cfg['ext']}"):
            filename = f"generated.{cfg['ext']}"
    except Exception:
        filename = f"generated.{cfg['ext']}"

    loc = len([l for l in code.splitlines() if l.strip() and not l.strip().startswith(("#","//","/*","*","*/"))])
    return {
        "language":            cfg["label"],
        "language_key":        lang,
        "ext":                 cfg["ext"],
        "title":               requirements[:80].strip(),
        "code_content":        code,
        "description":         f"Generated {cfg['label']} code for: {requirements[:100]}",
        "filename_suggestion": filename,
        "metrics": {
            "total_lines":  len(code.splitlines()),
            "code_lines":   loc,
            "char_count":   len(code),
        }
    }


def review_dev_code(code: str, language: str, context: str = "") -> dict:
    """
    Developer code review — returns structured JSON with issues, improvements, score.
    """
    lang = language.lower()
    prompt = f"""You are a Senior Code Reviewer. Review this {language} code professionally.

CONTEXT: {context or 'General code review'}

CODE:
```
{code[:4000]}
```

Return a strict JSON object:
{{
  "overall_score": 82,
  "grade": "B+",
  "summary": "2-sentence overall assessment",
  "issues": [
    {{
      "severity": "Error|Warning|Info",
      "category": "Security|Performance|Logic|Style|Maintainability|Testing",
      "line_hint": "approximate line or function name",
      "description": "clear description of the issue",
      "suggestion": "how to fix it"
    }}
  ],
  "strengths": ["strength 1", "strength 2"],
  "improvements": [
    {{
      "improvement": "what to improve",
      "example": "short code example or null",
      "benefit": "why this is better"
    }}
  ],
  "security_flags": ["security concern 1"],
  "performance_notes": ["performance note 1"],
  "maintainability_score": 75,
  "readability_score": 80,
  "test_coverage_suggestion": "what tests should be written"
}}"""

    try:
        raw = _call_gemini(prompt)
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "overall_score": 70, "grade": "C+",
            "summary": "Code review could not be fully parsed.",
            "issues": [], "strengths": [], "improvements": [],
            "security_flags": [], "performance_notes": [],
            "maintainability_score": 70, "readability_score": 70,
            "test_coverage_suggestion": "Add unit tests for all public functions.",
            "error": str(e)
        }


def predict_dev_risk(project_title: str, requirements: str,
                     tech_stack: str, existing_issues: list = None) -> dict:
    """Risk prediction for a developer project."""
    prompt = f"""You are a Senior Architect doing risk assessment for a software project.

PROJECT: {project_title}
TECH STACK: {tech_stack}
REQUIREMENTS: {requirements[:500]}
KNOWN ISSUES: {json.dumps(existing_issues or [])}

Return strict JSON risk report:
{{
  "overall_risk_score": 45,
  "risk_level": "Low|Medium|High|Critical",
  "risks": [
    {{
      "risk": "specific risk",
      "category": "Technical|Security|Performance|Scalability|Maintainability|Timeline",
      "impact": "Low|Medium|High|Critical",
      "probability": "Low|Medium|High",
      "mitigation": "specific action to reduce this risk"
    }}
  ],
  "technical_debt_estimate": "Low|Medium|High",
  "scalability_concern": "Low|Medium|High",
  "security_concern": "Low|Medium|High",
  "recommendations": ["recommendation 1", "recommendation 2"],
  "estimated_complexity": "Simple|Moderate|Complex|Very Complex",
  "suggested_tech_improvements": ["improvement 1"]
}}"""
    try:
        raw = _call_gemini(prompt)
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "overall_risk_score": 50, "risk_level": "Medium",
            "risks": [], "technical_debt_estimate": "Medium",
            "scalability_concern": "Medium", "security_concern": "Medium",
            "recommendations": ["Review requirements thoroughly"],
            "estimated_complexity": "Moderate",
            "suggested_tech_improvements": [], "error": str(e)
        }
