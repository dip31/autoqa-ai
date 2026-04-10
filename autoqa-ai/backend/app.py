from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import bcrypt
import sys, os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))

from agents.testcase_agent import review_testcase
from agents.code_agent import review_code
from agents.website_agent import analyze_website
from agents.generator_agent import generate_testcases
from agents.risk_agent import predict_risk
from agents.report_agent import generate_report
from agents.chatbot_agent import chat
from database.db import execute_query

app = Flask(__name__)
CORS(app, supports_credentials=True)

from dotenv import load_dotenv
load_dotenv(override=True)
app.config["JWT_SECRET_KEY"] = os.getenv("SECRET_KEY", "autoqa-secret-2024")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)
jwt = JWTManager(app)

def db_save(query, params):
    try:
        execute_query(query, params)
    except Exception as e:
        print(f"[DB Warning] {e}")

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check duplicate
    existing = execute_query(
        "SELECT id FROM users WHERE email=%s OR username=%s", (email, username), fetch=True
    )
    if existing:
        return jsonify({"error": "Email or username already exists"}), 409

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = execute_query(
        "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
        (username, email, hashed)
    )
    # Auto-create first chat session
    execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (%s, %s)",
        (user_id, "Welcome Chat")
    )
    token = create_access_token(identity=str(user_id))
    return jsonify({
        "success": True,
        "token": token,
        "user": {"id": user_id, "username": username, "email": email}
    }), 201

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    rows = execute_query("SELECT * FROM users WHERE email=%s", (email,), fetch=True)
    if not rows:
        return jsonify({"error": "Invalid email or password"}), 401

    user = rows[0]
    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user["id"]))
    return jsonify({
        "success": True,
        "token": token,
        "user": {"id": user["id"], "username": user["username"], "email": user["email"]}
    })

@app.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    rows = execute_query("SELECT id, username, email, created_at FROM users WHERE id=%s", (user_id,), fetch=True)
    if not rows:
        return jsonify({"error": "User not found"}), 404

    # Stats
    tc  = execute_query("SELECT COUNT(*) as c FROM test_cases WHERE user_id=%s",  (user_id,), fetch=True)[0]["c"]
    cr  = execute_query("SELECT COUNT(*) as c FROM code_reviews WHERE user_id=%s", (user_id,), fetch=True)[0]["c"]
    wt  = execute_query("SELECT COUNT(*) as c FROM website_tests WHERE user_id=%s",(user_id,), fetch=True)[0]["c"]
    return jsonify({"success": True, "user": rows[0], "stats": {"test_cases": tc, "code_reviews": cr, "website_tests": wt}})

# ── Chat History ──────────────────────────────────────────────────────────────
@app.route("/chat/sessions", methods=["GET"])
@jwt_required()
def get_sessions():
    user_id = int(get_jwt_identity())
    sessions = execute_query(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id=%s ORDER BY updated_at DESC",
        (user_id,), fetch=True
    )
    return jsonify({"success": True, "sessions": sessions})

@app.route("/chat/sessions", methods=["POST"])
@jwt_required()
def create_session():
    user_id = int(get_jwt_identity())
    title = request.get_json().get("title", "New Chat")
    sid = execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (%s, %s)", (user_id, title)
    )
    return jsonify({"success": True, "session_id": sid})

@app.route("/chat/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    user_id = int(get_jwt_identity())
    execute_query("DELETE FROM chat_sessions WHERE id=%s AND user_id=%s", (session_id, user_id))
    return jsonify({"success": True})

@app.route("/chat/sessions/<int:session_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(session_id):
    user_id = int(get_jwt_identity())
    msgs = execute_query(
        "SELECT role, content, created_at FROM chat_messages WHERE session_id=%s AND user_id=%s ORDER BY created_at ASC",
        (session_id, user_id), fetch=True
    )
    return jsonify({"success": True, "messages": msgs})

@app.route("/chat", methods=["POST"])
@jwt_required()
def api_chat():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    messages   = data.get("messages", [])
    session_id = data.get("session_id")

    if not messages:
        return jsonify({"error": "messages are required"}), 400
    try:
        reply = chat(messages)

        # Save to DB if session provided
        if session_id:
            last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
            if last_user:
                execute_query(
                    "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (%s,%s,%s,%s)",
                    (session_id, user_id, "user", last_user["content"])
                )
            execute_query(
                "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (%s,%s,%s,%s)",
                (session_id, user_id, "assistant", reply)
            )
            # Update session title from first user message
            first = execute_query(
                "SELECT COUNT(*) as c FROM chat_messages WHERE session_id=%s", (session_id,), fetch=True
            )[0]["c"]
            if first <= 2 and last_user:
                title = last_user["content"][:50]
                execute_query("UPDATE chat_sessions SET title=%s WHERE id=%s", (title, session_id))
            execute_query("UPDATE chat_sessions SET updated_at=NOW() WHERE id=%s", (session_id,))

        return jsonify({"success": True, "reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Feature endpoints (all require auth) ─────────────────────────────────────
@app.route("/review-testcase", methods=["POST"])
@jwt_required()
def api_review_testcase():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    testcase = data.get("testcase", "").strip()
    if not testcase:
        return jsonify({"error": "testcase is required"}), 400
    try:
        result = review_testcase(testcase)
        db_save("INSERT INTO test_cases (user_id, testcase, review_result, score) VALUES (%s,%s,%s,%s)",
                (user_id, testcase, str(result), result.get("score")))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/review-code", methods=["POST"])
@jwt_required()
def api_review_code():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    code     = data.get("code", "").strip()
    language = data.get("language", "Python").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    try:
        result = review_code(code, language)
        db_save("INSERT INTO code_reviews (user_id, code, language, result, score) VALUES (%s,%s,%s,%s,%s)",
                (user_id, code[:5000], language, str(result), result.get("score")))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/website-test", methods=["POST"])
@jwt_required()
def api_website_test():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    try:
        result = analyze_website(url)
        db_save("INSERT INTO website_tests (user_id, url, result) VALUES (%s,%s,%s)",
                (user_id, url, str(result)))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate-testcase", methods=["POST"])
@jwt_required()
def api_generate_testcase():
    data = request.get_json()
    requirement = data.get("requirement", "").strip()
    if not requirement:
        return jsonify({"error": "requirement is required"}), 400
    try:
        result = generate_testcases(requirement)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/predict-risk", methods=["POST"])
@jwt_required()
def api_predict_risk():
    data = request.get_json()
    content    = data.get("content", "").strip()
    input_type = data.get("input_type", "general")
    if not content:
        return jsonify({"error": "content is required"}), 400
    try:
        result = predict_risk(content, input_type)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate-report", methods=["GET"])
@jwt_required()
def api_generate_report():
    user_id = int(get_jwt_identity())
    try:
        result = generate_report(user_id)
        db_save("INSERT INTO reports (user_id, report_data) VALUES (%s,%s)", (user_id, str(result)))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Report Image Generation ───────────────────────────────────────────────────
@app.route("/generate-report-image", methods=["POST"])
@jwt_required()
def api_generate_report_image():
    from dotenv import load_dotenv
    import time
    load_dotenv(override=True)
    import requests as req
    data = request.get_json()
    report_data = data.get("report", {})
    api_key = os.getenv("GEMINI_API_KEY")
    score = report_data.get('quality_score', 0)
    stats = report_data.get('stats', {})

    prompt = f"""You are a QA report analyst. Based on the data below, write a concise professional QA Report Card with these exact sections. Use plain text only, no markdown symbols like *, #, or -.

QA REPORT CARD
Quality Score: {score}/100
Status: {"Excellent" if score >= 80 else "Needs Improvement" if score >= 50 else "Critical"}

ACTIVITY SUMMARY
Test Cases Reviewed: {stats.get('total_testcases', 0)}
Code Reviews Completed: {stats.get('total_code_reviews', 0)}
Website Tests Run: {stats.get('total_website_tests', 0)}
Average Test Case Score: {stats.get('avg_testcase_score', 0)}
Average Code Score: {stats.get('avg_code_score', 0)}

EXECUTIVE SUMMARY
{report_data.get('executive_summary', 'No data available')}

TEST COVERAGE
{report_data.get('test_coverage_analysis', 'No data available')}

BUG SUMMARY
{report_data.get('bug_summary', 'No data available')}

TOP 3 RECOMMENDATIONS
Write exactly 3 short recommendations based on: {', '.join((report_data.get('recommendations') or ['Improve test coverage'])[:3])}

Keep each section to 2-3 sentences maximum. Be direct and professional."""

    models = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024}
    }

    last_error = None
    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            res = req.post(url, json=payload, timeout=45)
            res.raise_for_status()
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return jsonify({"success": True, "content": text, "model": model})
        except Exception as e:
            last_error = str(e)
            time.sleep(1)
            continue

    return jsonify({"error": f"All Gemini models unavailable. {last_error}"}), 503

if __name__ == "__main__":
    app.run(debug=True, port=5000)
