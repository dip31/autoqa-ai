"""
Diagram Agent — generates Mermaid syntax for 5 diagram types via Gemini.
Types: class, activity, sequence, architecture, timeline
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv(override=True)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS  = ["gemini-flash-lite-latest", "gemini-flash-latest"]

DIAGRAM_INSTRUCTIONS = {
    "class": {
        "name": "Class Diagram",
        "desc": "UML class diagram showing classes, attributes, methods, and relationships.",
        "example": 'classDiagram\n  class Animal {\n    +String name\n    +int age\n    +makeSound()\n  }\n  class Dog {\n    +String breed\n    +bark()\n  }\n  Animal <|-- Dog',
    },
    "activity": {
        "name": "Activity Diagram",
        "desc": "Flowchart-style activity diagram showing the process flow and decision points.",
        "example": 'flowchart TD\n  A([Start]) --> B[Step One]\n  B --> C{Decision}\n  C -->|Yes| D[Do This]\n  C -->|No| E[Do That]\n  D --> F([End])\n  E --> F',
    },
    "sequence": {
        "name": "Sequence Diagram",
        "desc": "Sequence diagram showing interactions between actors/components over time.",
        "example": 'sequenceDiagram\n  participant U as User\n  participant F as Frontend\n  participant B as Backend\n  participant D as Database\n  U->>F: Submit Form\n  F->>B: POST /api/resource\n  B->>D: INSERT INTO ...\n  D-->>B: OK\n  B-->>F: 201 Created\n  F-->>U: Show Success',
    },
    "architecture": {
        "name": "Architecture Diagram",
        "desc": "High-level system architecture showing components, layers, and data flow.",
        "example": 'graph TB\n  subgraph Client\n    UI[React Frontend]\n  end\n  subgraph Server\n    API[Flask API]\n    Auth[Auth Service]\n  end\n  subgraph Data\n    DB[(SQLite DB)]\n    Cache[(Redis Cache)]\n  end\n  UI -->|HTTPS| API\n  API --> Auth\n  API --> DB\n  API --> Cache',
    },
    "timeline": {
        "name": "Timeline / Gantt Chart",
        "desc": "Gantt chart showing project phases, tasks, and timeline.",
        "example": 'gantt\n  title Project Timeline\n  dateFormat  YYYY-MM-DD\n  section Phase 1\n    Task A :a1, 2024-01-01, 7d\n    Task B :a2, after a1, 5d\n  section Phase 2\n    Task C :a3, after a2, 10d\n    Task D :a4, after a3, 7d',
    },
}


def _call_gemini(prompt: str) -> str:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096}
    }
    last_err = None
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            res = requests.post(url, json=payload, timeout=60)
            res.raise_for_status()
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text
        except Exception as e:
            last_err = str(e)
    raise Exception(f"Gemini unavailable: {last_err}")


def _clean_mermaid(raw: str) -> str:
    """Strip markdown fences and extract pure Mermaid code."""
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for p in parts:
            p = p.strip()
            for keyword in ("classDiagram", "flowchart", "sequenceDiagram",
                            "graph", "gantt", "timeline", "stateDiagram",
                            "erDiagram", "journey"):
                if p.startswith(keyword) or p.lstrip().startswith(keyword):
                    return p.strip()
        # fallback: take the longest code block
        code_blocks = [p.strip() for p in parts if p.strip() and not p.startswith("mermaid")]
        if code_blocks:
            return max(code_blocks, key=len)
    return raw


def generate_diagram(diagram_type: str, requirements: str, project_context: str = "") -> dict:
    """
    Generate a Mermaid diagram from requirements.
    Returns: { diagram_type, title, mermaid_code, description, instructions }
    """
    dtype = diagram_type.lower()
    if dtype not in DIAGRAM_INSTRUCTIONS:
        raise ValueError(f"Unknown diagram type '{diagram_type}'. Valid: {list(DIAGRAM_INSTRUCTIONS.keys())}")

    spec = DIAGRAM_INSTRUCTIONS[dtype]

    prompt = f"""You are an expert software architect and diagram specialist.
Generate a professional, detailed {spec['name']} using Mermaid syntax.

PROJECT CONTEXT: {project_context or 'Not provided'}
REQUIREMENTS: {requirements}

DIAGRAM TYPE: {spec['name']}
DESCRIPTION: {spec['desc']}

EXAMPLE FORMAT:
{spec['example']}

RULES:
1. Return ONLY valid Mermaid syntax — NO explanations, NO markdown fences, NO ```mermaid blocks
2. Make it detailed and realistic — use actual component/class/service names from the requirements
3. Show all major relationships, flows, or interactions
4. Add comments (%%  ...) where helpful
5. For class diagrams: include attributes and methods
6. For sequence diagrams: use 3-5 participants minimum
7. For architecture: use subgraph to group related components
8. For gantt: use realistic timeframes (7d, 14d, 30d)

Return ONLY the raw Mermaid code. Nothing else."""

    raw = _call_gemini(prompt)
    code = _clean_mermaid(raw)

    # Generate a short description
    desc_prompt = f"""In one sentence, describe what this {spec['name']} represents for the given requirements.
Requirements: {requirements[:300]}
Return ONLY the one-sentence description."""
    try:
        description = _call_gemini(desc_prompt).strip().strip('"')
    except Exception:
        description = f"{spec['name']} for the described system"

    return {
        "diagram_type":  dtype,
        "type_label":    spec["name"],
        "title":         f"{spec['name']} — {requirements[:60].strip()}",
        "mermaid_code":  code,
        "description":   description,
    }


def generate_multiple_diagrams(requirements: str, types: list, project_context: str = "") -> list:
    """Generate multiple diagram types for the same requirements."""
    results = []
    for dtype in types:
        try:
            d = generate_diagram(dtype, requirements, project_context)
            d["success"] = True
            results.append(d)
        except Exception as e:
            results.append({"diagram_type": dtype, "success": False, "error": str(e)})
    return results
