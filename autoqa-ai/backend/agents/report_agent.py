import os
import json
from groq import Groq
from database.db import execute_query
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_report(user_id: int = None) -> dict:
    try:
        if user_id:
            tc_query  = "SELECT score, review_result FROM test_cases WHERE user_id=%s ORDER BY created_at DESC LIMIT 20"
            cr_query  = "SELECT score, language, result FROM code_reviews WHERE user_id=%s ORDER BY created_at DESC LIMIT 20"
            wt_query  = "SELECT url, result FROM website_tests WHERE user_id=%s ORDER BY created_at DESC LIMIT 10"
            test_cases   = execute_query(tc_query,  (user_id,), fetch=True)
            code_reviews = execute_query(cr_query,  (user_id,), fetch=True)
            website_tests= execute_query(wt_query,  (user_id,), fetch=True)
        else:
            test_cases = code_reviews = website_tests = []
    except Exception as db_err:
        print(f"[DB Warning] Could not fetch report data: {db_err}")
        test_cases, code_reviews, website_tests = [], [], []

    # Calculate averages
    tc_scores = [r["score"] for r in test_cases if r.get("score")]
    cr_scores = [r["score"] for r in code_reviews if r.get("score")]
    avg_tc_score = round(sum(tc_scores) / len(tc_scores), 1) if tc_scores else 0
    avg_cr_score = round(sum(cr_scores) / len(cr_scores), 1) if cr_scores else 0

    summary_prompt = f"""
    Generate a QA report summary based on this data:
    - Test Cases Reviewed: {len(test_cases)}, Average Score: {avg_tc_score}
    - Code Reviews: {len(code_reviews)}, Average Score: {avg_cr_score}
    - Website Tests: {len(website_tests)}
    - Languages reviewed: {list(set(r['language'] for r in code_reviews if r.get('language')))}

    Return ONLY valid JSON with:
    - executive_summary: string
    - quality_score: overall quality score (0-100)
    - test_coverage_analysis: string
    - bug_summary: string
    - recommendations: list of strings
    - stats: object with total_testcases, total_code_reviews, total_website_tests, avg_testcase_score, avg_code_score
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.3
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    report = json.loads(raw.strip())
    report["stats"] = {
        "total_testcases": len(test_cases),
        "total_code_reviews": len(code_reviews),
        "total_website_tests": len(website_tests),
        "avg_testcase_score": avg_tc_score,
        "avg_code_score": avg_cr_score
    }
    return report
