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
        # Find first '{' and last '}'
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text) # Fallback
    except Exception as e:
        print(f"[JSON Parse Error] {e}")
        raise ValueError(f"Failed to parse report data from AI response: {text[:200]}...")

def generate_report(user_id: int = None) -> dict:
    try:
        if user_id:
            tc_query  = "SELECT score, review_result FROM test_cases WHERE user_id=? ORDER BY created_at DESC LIMIT 20"
            cr_query  = "SELECT score, language, result FROM code_reviews WHERE user_id=? ORDER BY created_at DESC LIMIT 20"
            wt_query  = "SELECT url, result FROM website_tests WHERE user_id=? ORDER BY created_at DESC LIMIT 10"
            aq_query  = "SELECT status, title, module_name FROM autonomous_runs WHERE user_id=? ORDER BY created_at DESC LIMIT 5"
            
            test_cases      = execute_query(tc_query,  (user_id,), fetch=True)
            code_reviews    = execute_query(cr_query,  (user_id,), fetch=True)
            website_tests   = execute_query(wt_query,  (user_id,), fetch=True)
            autonomous_runs = execute_query(aq_query,  (user_id,), fetch=True)
        else:
            test_cases = code_reviews = website_tests = autonomous_runs = []
    except Exception as db_err:
        print(f"[DB Warning] Could not fetch report data: {db_err}")
        test_cases, code_reviews, website_tests, autonomous_runs = [], [], [], []

    # Calculate averages
    tc_scores = [r["score"] for r in test_cases if r.get("score")]
    cr_scores = [r["score"] for r in code_reviews if r.get("score")]
    avg_tc_score = round(sum(tc_scores) / len(tc_scores), 1) if tc_scores else 0
    avg_cr_score = round(sum(cr_scores) / len(cr_scores), 1) if cr_scores else 0
    
    # Autonomous stats
    aq_completed = len([r for r in autonomous_runs if r["status"] == "Completed"])
    aq_failed    = len([r for r in autonomous_runs if r["status"] == "Failed"])

    summary_prompt = f"""
    Generate a comprehensive professional QA report summary based on this platform activity data:
    - Manual Test Case Reviews: {len(test_cases)}, Average Score: {avg_tc_score}
    - Autonomous QA Agent Runs: {len(autonomous_runs)} total ({aq_completed} Completed, {aq_failed} Failed)
    - Website Discovery Tests: {len(website_tests)}
    - Legacy Code Reviews: {len(code_reviews)}
    
    Data Details:
    - Autonomous Modules: {[r['module_name'] for r in autonomous_runs if r.get('module_name')]}
    - Websites Analyzed: {[r['url'] for r in website_tests if r.get('url')]}

    Return ONLY valid JSON with exactly these keys:
    - executive_summary: A high-level wrap-up of the quality status.
    - quality_score: An overall calculated quality score (0-100).
    - test_coverage_analysis: Analysis of how well the system is tested.
    - bug_summary: Overview of found issues or areas of high risk.
    - recommendations: An array of 3-5 strings for improvement.
    - stats: An object with total_testcases, total_code_reviews, total_website_tests, total_autonomous_runs, avg_testcase_score, avg_code_score.
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        raw_text = response.choices[0].message.content.strip()
        report = extract_json(raw_text)
        
        # Ensure our precise DB stats are reflected
        report["stats"] = {
            "total_testcases": len(test_cases),
            "total_code_reviews": len(code_reviews),
            "total_website_tests": len(website_tests),
            "total_autonomous_runs": len(autonomous_runs),
            "avg_testcase_score": avg_tc_score,
            "avg_code_score": avg_cr_score
        }
        return report
    except Exception as e:
        print(f"[Report Agent Error] {e}")
        # Return a fallback report so the UI doesn't crash
        return {
            "executive_summary": "Failed to generate AI summary. Basic stats are available below.",
            "quality_score": 0,
            "test_coverage_analysis": "N/A",
            "bug_summary": "N/A",
            "recommendations": ["Ensure API keys are valid", "Check internet connection"],
            "stats": {
                "total_testcases": len(test_cases),
                "total_code_reviews": len(code_reviews),
                "total_website_tests": len(website_tests),
                "total_autonomous_runs": len(autonomous_runs),
                "avg_testcase_score": avg_tc_score,
                "avg_code_score": avg_cr_score
            }
        }
