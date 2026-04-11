"""
QA-to-Dev Bridge Agent
Converts QA findings -> root cause analysis, fix recommendations,
Mermaid diagrams, timeline, code suggestions, code review, risk prediction.
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS  = ["gemini-flash-lite-latest", "gemini-flash-latest"]


def _call_gemini(prompt: str) -> dict:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 8192,
            "response_mime_type": "application/json"
        }
    }
    last_err = None
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            res = requests.post(url, json=payload, timeout=90)
            res.raise_for_status()
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except Exception as e:
            last_err = str(e)
    raise Exception(f"Gemini unavailable: {last_err}")


def analyze_qa_to_dev(qa_data: dict, system_mode: str = "FULL") -> dict:
    """
    Main entry point.
    system_mode: "FULL" -> all sections
                 "QA_ONLY" -> summary + bug analysis only
    """
    application  = qa_data.get("application", "Unknown App")
    url          = qa_data.get("url", "")
    bugs         = qa_data.get("bugs", [])
    severity     = qa_data.get("severity", [])
    steps        = qa_data.get("steps_to_reproduce", [])
    expected     = qa_data.get("expected_behavior", [])
    actual       = qa_data.get("actual_behavior", [])
    screenshots  = qa_data.get("screenshots", [])
    logs         = qa_data.get("logs", [])

    # Build context string
    context = f"""
APPLICATION: {application}
URL: {url}

BUGS REPORTED ({len(bugs)}):
{json.dumps(bugs, indent=2)}

SEVERITY MAP:
{json.dumps(severity, indent=2)}

STEPS TO REPRODUCE:
{json.dumps(steps, indent=2)}

EXPECTED VS ACTUAL:
Expected: {json.dumps(expected, indent=2)}
Actual:   {json.dumps(actual, indent=2)}

LOGS:
{json.dumps(logs, indent=2)}
"""

    if system_mode == "QA_ONLY":
        prompt = f"""You are a QA Analyst. Analyze these QA findings and produce insights.

{context}

Return strict JSON:
{{
  "summary": "2-3 paragraph professional QA summary",
  "bug_analysis": [
    {{
      "bug": "bug name",
      "severity": "Critical/High/Medium/Low",
      "category": "UI/Backend/API/Logic/Performance",
      "insight": "detailed analysis",
      "test_coverage_gap": "what test was missing"
    }}
  ],
  "test_insights": {{
    "total_bugs": {len(bugs)},
    "critical_count": 0,
    "high_count": 0,
    "patterns_detected": ["pattern 1", "pattern 2"],
    "most_affected_module": "module name",
    "coverage_recommendation": "what to test next"
  }}
}}"""
        try:
            result = _call_gemini(prompt)
            result["mode"] = "QA_ONLY"
            return result
        except Exception as e:
            return {"error": str(e), "mode": "QA_ONLY"}

    # ── FULL MODE ──────────────────────────────────────────────────────────────
    prompt = f"""You are an Advanced AI Software Engineering System bridging QA and Development.
Act as: QA Analyst + Software Architect + Developer Assistant + Risk Analyst.

QA FINDINGS:
{context}

Generate a complete developer-ready intelligence report. Return STRICT JSON:
{{
  "summary": "3-paragraph professional executive summary of QA findings and recommended action plan",

  "root_cause_analysis": [
    {{
      "bug": "exact bug name from input",
      "possible_cause": "technical root cause explanation",
      "category": "UI | Backend | API | Logic | Database | Network | State | Auth",
      "confidence": "Low | Medium | High",
      "affected_component": "component name or file"
    }}
  ],

  "fix_recommendations": [
    {{
      "bug": "exact bug name",
      "solution": "clear, actionable fix description",
      "priority": "Critical | High | Medium | Low",
      "effort": "1h | 4h | 1d | 3d | 1w",
      "fix_type": "UI | Backend | Config | Logic | Database"
    }}
  ],

  "diagrams": {{
    "bug_flow_diagram": "graph TD\\n  A[User Action] --> B[Bug Trigger]\\n  B --> C[Failure Point]\\n  C --> D[Error State]",
    "fixed_flow_diagram": "graph TD\\n  A[User Action] --> B[Fixed Handler]\\n  B --> C[Success State]\\n  C --> D[User Sees Result]",
    "sequence_diagram": "sequenceDiagram\\n  participant U as User\\n  participant F as Frontend\\n  participant B as Backend\\n  participant D as Database\\n  U->>F: Action\\n  F->>B: API Call\\n  B->>D: Query\\n  D-->>B: Result\\n  B-->>F: Response\\n  F-->>U: Render"
  }},

  "timeline": {{
    "total_estimated_days": 0,
    "tasks": [
      {{
        "task": "specific task name",
        "description": "what needs to be done",
        "assigned_to": "Frontend | Backend | Fullstack | DevOps",
        "estimated_time": "2h | 4h | 1d | 2d",
        "priority": "Critical | High | Medium | Low",
        "depends_on": "task name or null"
      }}
    ]
  }},

  "code_suggestions": [
    {{
      "bug": "exact bug name",
      "language": "JavaScript | Python | TypeScript | Java | CSS",
      "file_hint": "suggested filename (e.g. auth.js, api.py)",
      "description": "what this fix does",
      "code_fix": "// production-ready code fix\\nfunction example() {{\\n  // fixed implementation\\n}}"
    }}
  ],

  "code_review": {{
    "issues": [
      {{
        "issue": "specific code quality issue",
        "severity": "Error | Warning | Info",
        "location": "component or file hint"
      }}
    ],
    "improvements": [
      {{
        "improvement": "specific improvement suggestion",
        "benefit": "why this improves quality"
      }}
    ],
    "overall_code_health": "Poor | Fair | Good",
    "technical_debt_level": "Low | Medium | High"
  }},

  "risk_prediction": {{
    "overall_risk_level": "Low | Medium | High | Critical",
    "risks": [
      {{
        "risk": "specific risk description",
        "category": "Regression | Security | Performance | UX | Data | Reliability",
        "impact": "Low | Medium | High | Critical",
        "probability": "Low | Medium | High",
        "mitigation": "actionable mitigation strategy"
      }}
    ],
    "regression_risk": "Low | Medium | High",
    "security_risk": "Low | Medium | High",
    "performance_impact": "Low | Medium | High"
  }}
}}

IMPORTANT:
- Mermaid diagrams must use valid Mermaid syntax
- Code fixes must be production-ready (no pseudocode)
- All bugs from input must appear in root_cause_analysis and fix_recommendations
- Timeline must be realistic and sequenced"""

    try:
        result = _call_gemini(prompt)
        result["mode"] = "FULL"
        result["meta"] = {
            "application": application,
            "url": url,
            "total_bugs": len(bugs),
            "screenshots_count": len(screenshots)
        }
        return result
    except Exception as e:
        return {"error": str(e), "mode": "FULL"}
