"""
Security Report Agent – generates security assessment reports.
"""
import os
import json
import re
from groq import Groq
from database.db import execute_query
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def extract_json(text: str) -> dict:
    """Extracts the first JSON object from a string using regex."""
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except Exception as e:
        print(f"[JSON Parse Error] {e}")
        raise ValueError(
            f"Failed to parse report data from AI response: {text[:200]}..."
        )


def generate_security_report(run_id: int) -> dict:
    """Generate a security assessment report for a completed run."""
    try:
        # Fetch run details
        run_rows = execute_query(
            "SELECT * FROM autonomous_runs WHERE id=? AND run_type='security'", (run_id,), fetch=True
        )
        if not run_rows:
            return {"error": "Security run not found"}
        run = run_rows[0]

        # Fetch findings
        findings = execute_query(
            "SELECT * FROM security_findings WHERE run_id=? ORDER BY severity DESC, created_at DESC",
            (run_id,), fetch=True
        )

        # Fetch evidence for findings
        for finding in findings:
            evidence = execute_query(
                "SELECT * FROM security_evidence WHERE finding_id=? ORDER BY created_at",
                (finding["id"],), fetch=True
            )
            finding["evidence"] = evidence

        # Count findings by severity
        severity_counts = {
            "Critical": len([f for f in findings if f["severity"] == "Critical"]),
            "High": len([f for f in findings if f["severity"] == "High"]),
            "Medium": len([f for f in findings if f["severity"] == "Medium"]),
            "Low": len([f for f in findings if f["severity"] == "Low"]),
            "Informational": len([f for f in findings if f["severity"] == "Informational"]),
        }

        # Count findings by validator
        validator_counts = {}
        for f in findings:
            vid = f.get("validator_id", "unknown")
            validator_counts[vid] = validator_counts.get(vid, 0) + 1

        # Group findings by category
        category_counts = {}
        for f in findings:
            cat = f.get("category", "Unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Build summary prompt
        summary_prompt = f"""
        Generate a professional security assessment report based on this security validation data:

        Assessment Metadata:
        - Run ID: {run_id}
        - Title: {run.get("title", "Security Validation Run")}
        - Target: {run.get("url", "N/A")}
        - Status: {run.get("status", "Unknown")}
        - Duration: {run.get("duration_seconds", 0)} seconds
        - Validators Executed: {run.get("validators_executed", 0)}
        - Total Findings: {len(findings)}

        Finding Summary:
        - Critical: {severity_counts["Critical"]}
        - High: {severity_counts["High"]}
        - Medium: {severity_counts["Medium"]}
        - Low: {severity_counts["Low"]}
        - Informational: {severity_counts["Informational"]}

        By Category:
        {json.dumps(category_counts, indent=2)}

        By Validator:
        {json.dumps(validator_counts, indent=2)}

        Sample Findings (top 10):
        {json.dumps(findings[:10], indent=2, default=str)}

        Return ONLY valid JSON with exactly these keys:
        - executive_summary: High-level security posture summary (2-3 sentences).
        - risk_score: Overall security risk score (0-100, where 0 is no risk, 100 is critical).
        - compliance_assessment: Assessment against common security best practices.
        - top_findings: Array of top 5 most critical findings with title, severity, and recommendation.
        - recommendations: Array of 5-7 actionable remediation steps prioritized by impact.
        - validator_coverage: Description of which security controls were validated.
        - limitations: Known limitations of this assessment.
        """

        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
            )
            raw_text = response.choices[0].message.content.strip()
            report = extract_json(raw_text)

            # Add structured data
            report["metadata"] = {
                "run_id": run_id,
                "title": run.get("title"),
                "target": run.get("url"),
                "status": run.get("status"),
                "duration_seconds": run.get("duration_seconds", 0),
                "validators_executed": run.get("validators_executed", 0),
                "total_findings": len(findings),
                "severity_counts": severity_counts,
                "category_counts": category_counts,
                "validator_counts": validator_counts,
                "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
            }
            return report
        except Exception as e:
            print(f"[Security Report Agent Error] {e}")
            # Return fallback report
            return {
                "executive_summary": "Failed to generate AI summary. Basic stats are available below.",
                "risk_score": 0,
                "compliance_assessment": "N/A",
                "top_findings": [],
                "recommendations": [
                    "Ensure API keys are valid",
                    "Check internet connection",
                ],
                "validator_coverage": "Six validators executed: HTTPS, Security Headers, Cookie Security, Information Disclosure, Redirect Analysis, TLS Configuration",
                "limitations": [
                    "AI summary generation failed",
                    "Manual review of findings recommended"
                ],
                "metadata": {
                    "run_id": run_id,
                    "total_findings": len(findings),
                    "severity_counts": severity_counts,
                    "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
                },
            }
    except Exception as e:
        print(f"[Security Report Agent DB Error] {e}")
        return {"error": f"Failed to generate report: {e}"}