from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import bcrypt
import sys, os
import requests
import secrets
import json
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))

from agents.testcase_agent import review_testcase
from agents.code_agent import review_code
from agents.website_agent import analyze_website
from agents.generator_agent import generate_testcases
from agents.risk_agent import predict_risk
from agents.report_agent import generate_report
from agents.chatbot_agent import chat
from agents.autonomous_agent import run_autonomous_qa
from agents.qa_dev_bridge_agent import analyze_qa_to_dev
from agents.diagram_agent import generate_diagram, generate_multiple_diagrams
from agents.dev_code_agent import generate_code, review_dev_code, predict_dev_risk
from agents.github_agent import GitHubAgent
from agents.repo_intelligence_agent import RepoIntelligenceAgent
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
        app.logger.error(f"[DB Error] {e}")
        raise e

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
        "SELECT id FROM users WHERE email=? OR username=?", (email, username), fetch=True
    )
    if existing:
        return jsonify({"error": "Email or username already exists"}), 409

    role = data.get("role", "qa_engineer").strip()
    if role not in ("qa_engineer", "developer"):
        role = "qa_engineer"

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = execute_query(
        "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
        (username, email, hashed, role)
    )
    # Auto-create first chat session
    execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
        (user_id, "Welcome Chat")
    )
    token = create_access_token(identity=str(user_id))
    return jsonify({
        "success": True,
        "token": token,
        "user": {"id": user_id, "username": username, "email": email, "role": role}
    }), 201

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    rows = execute_query("SELECT * FROM users WHERE email=?", (email,), fetch=True)
    if not rows:
        return jsonify({"error": "Invalid email or password"}), 401

    user = rows[0]
    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user["id"]))
    return jsonify({
        "success": True,
        "token": token,
        "user": {"id": user["id"], "username": user["username"],
                 "email": user["email"], "role": user.get("role", "qa_engineer")}
    })

# ── GitHub OAuth ─────────────────────────────────────────────────────────────
@app.route("/auth/github/login")
def github_login():
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        return jsonify({"error": "GITHUB_CLIENT_ID not configured in .env"}), 500
    state = secrets.token_hex(16)
    redirect_uri = "http://localhost:5000/auth/github/callback"
    url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope=user:email,repo&state={state}"
    return redirect(url)

@app.route("/auth/github/callback")
def github_callback():
    code = request.args.get("code")
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    
    if not code:
        return "GitHub auth failed: No code provided", 400
        
    res = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={"client_id": client_id, "client_secret": client_secret, "code": code}
    )
    data = res.json()
    token = data.get("access_token")
    if not token:
        return f"GitHub auth failed: {data.get('error_description', 'No access token')}", 400
        
    u_res = requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"})
    gh_u = u_res.json()
    gh_id = str(gh_u.get("id"))
    gh_login = gh_u.get("login")
    
    # Try to find user by github_id
    rows = execute_query("SELECT * FROM users WHERE github_id=?", (gh_id,), fetch=True)
    if rows:
        user = rows[0]
        execute_query("UPDATE users SET github_token=? WHERE id=?", (token, user["id"]))
    else:
        # Check by email (fetch emails if needed)
        e_res = requests.get("https://api.github.com/user/emails", headers={"Authorization": f"token {token}"})
        emails = e_res.json()
        primary_email = next((e['email'] for e in emails if e['primary']), f"{gh_login}@github.com")
        
        rows = execute_query("SELECT * FROM users WHERE email=?", (primary_email,), fetch=True)
        if rows:
            user = rows[0]
            execute_query("UPDATE users SET github_id=?, github_token=? WHERE id=?", (gh_id, token, user["id"]))
        else:
            # Create new
            uid = execute_query(
                "INSERT INTO users (username, email, password, role, github_id, github_token) VALUES (?,?,?,?,?,?)",
                (gh_login, primary_email, "GITHUB_OAUTH", "qa_engineer", gh_id, token)
            )
            execute_query("INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)", (uid, "GitHub Welcome"))
            user = {"id": uid, "username": gh_login, "email": primary_email, "role": "qa_engineer"}
            
    jwt_token = create_access_token(identity=str(user["id"]))
    # Redirect to frontend callback route with token
    frontend_url = f"http://localhost:3000/login?token={jwt_token}&username={user['username']}&role={user.get('role', 'qa_engineer')}&id={user['id']}"
    return redirect(frontend_url)

@app.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    rows = execute_query("SELECT id, username, email, role, created_at FROM users WHERE id=?", (user_id,), fetch=True)
    if not rows:
        return jsonify({"error": "User not found"}), 404

    # Stats
    tc  = execute_query("SELECT COUNT(*) as c FROM test_cases WHERE user_id=?",  (user_id,), fetch=True)[0]["c"]
    cr  = execute_query("SELECT COUNT(*) as c FROM code_reviews WHERE user_id=?", (user_id,), fetch=True)[0]["c"]
    wt  = execute_query("SELECT COUNT(*) as c FROM website_tests WHERE user_id=?",(user_id,), fetch=True)[0]["c"]
    # Check if GitHub is connected
    gh_rows = execute_query("SELECT github_id, github_token FROM users WHERE id=?", (user_id,), fetch=True)
    github_connected = bool(gh_rows[0]["github_id"]) if gh_rows else False
    
    return jsonify({
        "success": True, 
        "user": rows[0], 
        "github_connected": github_connected,
        "stats": {"test_cases": tc, "code_reviews": cr, "website_tests": wt}
    })

# ── GitHub Intelligence ──────────────────────────────────────────────────────
@app.route("/api/github/repos", methods=["GET"])
@jwt_required()
def api_github_repos():
    user_id = int(get_jwt_identity())
    rows = execute_query("SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True)
    if not rows or not rows[0]["github_token"]:
        return jsonify({"success": False, "repos": [], "connected": False, "error": "GitHub not connected"}), 200
    
    agent = GitHubAgent(rows[0]["github_token"])
    repos = agent.get_user_repos()
    return jsonify({"success": True, "repos": repos})

@app.route("/api/github/branches", methods=["POST"])
@jwt_required()
def api_github_branches():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    repo_url = data.get("repo_url")
    owner = data.get("owner")
    repo_name = data.get("repo_name")
    
    rows = execute_query("SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True)
    token = rows[0]["github_token"] if rows else None
    
    agent = GitHubAgent(token)
    if not owner or not repo_name:
        owner, repo_name = agent.parse_repo_url(repo_url)
        
    if not owner or not repo_name:
        return jsonify({"error": "Invalid repo information"}), 400
        
    branches = agent.get_repo_branches(owner, repo_name)
    return jsonify({"success": True, "branches": branches})

@app.route("/api/github/analyze", methods=["POST"])
@jwt_required()
def api_github_analyze():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    repo_url = data.get("repo_url")
    branch = data.get("branch", "main")
    
    try:
        rows = execute_query("SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True)
        token = rows[0]["github_token"] if rows else None
        
        int_agent = RepoIntelligenceAgent(token)
        result = int_agent.analyze(repo_url, branch)
        
        if "error" in result:
            return jsonify(result), 400
            
        # Save analysis
        execute_query(
            "INSERT INTO github_analyses (user_id, repo_url, analysis_json) VALUES (?, ?, ?)",
            (user_id, repo_url, json.dumps(result))
        )
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        app.logger.error(f"[Analyze Error] {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/github/history", methods=["GET"])
@jwt_required()
def api_github_history():
    user_id = int(get_jwt_identity())
    rows = execute_query("SELECT * FROM github_analyses WHERE user_id=? ORDER BY created_at DESC", (user_id,), fetch=True)
    return jsonify({"success": True, "history": rows})

# ── Chat History ──────────────────────────────────────────────────────────────
@app.route("/chat/sessions", methods=["GET"])
@jwt_required()
def get_sessions():
    user_id = int(get_jwt_identity())
    sessions = execute_query(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,), fetch=True
    )
    return jsonify({"success": True, "sessions": sessions})

@app.route("/chat/sessions", methods=["POST"])
@jwt_required()
def create_session():
    user_id = int(get_jwt_identity())
    title = request.get_json().get("title", "New Chat")
    sid = execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)", (user_id, title)
    )
    return jsonify({"success": True, "session_id": sid})

@app.route("/chat/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    user_id = int(get_jwt_identity())
    execute_query("DELETE FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id))
    return jsonify({"success": True})

@app.route("/chat/sessions/<int:session_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(session_id):
    user_id = int(get_jwt_identity())
    msgs = execute_query(
        "SELECT role, content, created_at FROM chat_messages WHERE session_id=? AND user_id=? ORDER BY created_at ASC",
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
                    "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (?,?,?,?)",
                    (session_id, user_id, "user", last_user["content"])
                )
            execute_query(
                "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (?,?,?,?)",
                (session_id, user_id, "assistant", reply)
            )
            # Update session title from first user message
            first = execute_query(
                "SELECT COUNT(*) as c FROM chat_messages WHERE session_id=?", (session_id,), fetch=True
            )[0]["c"]
            if first <= 2 and last_user:
                title = last_user["content"][:50]
                execute_query("UPDATE chat_sessions SET title=? WHERE id=?", (title, session_id))
            execute_query("UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))

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
    if len(testcase) > 10000:
        return jsonify({"error": "testcase content too large"}), 400
    try:
        result = review_testcase(testcase)
        db_save("INSERT INTO test_cases (user_id, testcase, review_result, score) VALUES (?,?,?,?)",
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
    if len(code) > 50000:
        return jsonify({"error": "code content too large"}), 400
    try:
        result = review_code(code, language)
        db_save("INSERT INTO code_reviews (user_id, code, language, result, score) VALUES (?,?,?,?,?)",
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
        db_save("INSERT INTO website_tests (user_id, url, result) VALUES (?,?,?)",
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
        import json
        db_save("INSERT INTO reports (user_id, report_data) VALUES (?,?)", (user_id, json.dumps(result)))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── QA-to-Dev Bridge ─────────────────────────────────────────────────────────
@app.route("/api/qa-dev-bridge/analyze", methods=["POST"])
@jwt_required()
def api_qa_dev_bridge():
    data        = request.get_json()
    qa_data     = data.get("qa_data", {})
    system_mode = data.get("system_mode", "FULL")
    if not qa_data.get("bugs") and not qa_data.get("application"):
        return jsonify({"error": "qa_data with bugs or application is required"}), 400
    try:
        result = analyze_qa_to_dev(qa_data, system_mode)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Autonomous QA ─────────────────────────────────────────────────────────────
@app.route("/api/autonomous-qa/run", methods=["POST"])
@jwt_required()
def api_autonomous_run():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    title = data.get("title", "Autonomous Run")
    module = data.get("module_name", "General")
    req_text = data.get("requirement_text", "").strip()
    url = data.get("url", "").strip()
    mode = data.get("execution_mode", "Full Autonomous Run")
    repo_url = data.get("repo_url", "").strip()

    if not req_text and not url and not repo_url:
        return jsonify({"error": "Requirement, URL, or Repo URL is required"}), 400

    # Create run entry
    run_id = execute_query(
        "INSERT INTO autonomous_runs (user_id, title, module_name, requirement_text, url, repo_url, execution_mode, status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, title, module, req_text, url, repo_url, mode, "Starting")
    )

    import threading
    thread = threading.Thread(target=run_autonomous_qa, args=(run_id,))
    thread.start()

    return jsonify({"success": True, "run_id": run_id}), 201

@app.route("/api/autonomous-qa/runs", methods=["GET"])
@jwt_required()
def api_get_autonomous_runs():
    user_id = int(get_jwt_identity())
    runs = execute_query("SELECT * FROM autonomous_runs WHERE user_id=? ORDER BY created_at DESC", (user_id,), fetch=True)
    return jsonify({"success": True, "runs": runs})

@app.route("/api/autonomous-qa/run/<int:run_id>", methods=["GET"])
@jwt_required()
def api_get_autonomous_run_details(run_id):
    user_id = int(get_jwt_identity())
    # Verify ownership
    run_rows = execute_query("SELECT * FROM autonomous_runs WHERE id=? AND user_id=?", (run_id, user_id), fetch=True)
    if not run_rows:
        return jsonify({"error": "Run not found"}), 404
    
    run = run_rows[0]
    scope = execute_query("SELECT * FROM autonomous_scope WHERE run_id=?", (run_id,), fetch=True)
    test_cases = execute_query("SELECT * FROM autonomous_test_cases WHERE run_id=?", (run_id,), fetch=True)
    logs = execute_query("SELECT * FROM autonomous_execution_logs WHERE run_id=? ORDER BY timestamp ASC", (run_id,), fetch=True)
    findings = execute_query("SELECT * FROM autonomous_findings WHERE run_id=?", (run_id,), fetch=True)
    risk = execute_query("SELECT * FROM autonomous_risk_analysis WHERE run_id=?", (run_id,), fetch=True)
    report = execute_query("SELECT * FROM autonomous_reports WHERE run_id=?", (run_id,), fetch=True)
    healing = execute_query("SELECT * FROM autonomous_healing_logs WHERE run_id=? ORDER BY timestamp ASC", (run_id,), fetch=True)

    # Repo Intelligence
    repo_intel = execute_query("SELECT analysis_json FROM autonomous_repo_intelligence WHERE run_id=?", (run_id,), fetch=True)
    repo_data = json.loads(repo_intel[0]["analysis_json"]) if repo_intel else None

    return jsonify({
        "success": True,
        "run": run,
        "scope": scope[0] if scope else None,
        "test_cases": test_cases,
        "logs": logs,
        "findings": findings,
        "risk": risk[0] if risk else None,
        "report": report[0] if report else None,
        "healing": healing,
        "repo_intelligence": repo_data
    })

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

# ── Developer Portal ─────────────────────────────────────────────────────────

# Projects
@app.route("/api/dev/projects", methods=["GET"])
@jwt_required()
def dev_list_projects():
    uid = int(get_jwt_identity())
    rows = execute_query("SELECT * FROM dev_projects WHERE user_id=? ORDER BY created_at DESC", (uid,), fetch=True)
    return jsonify({"success": True, "projects": [dict(r) for r in rows]})

@app.route("/api/dev/projects", methods=["POST"])
@jwt_required()
def dev_create_project():
    uid  = int(get_jwt_identity())
    data = request.get_json()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    pid = execute_query(
        "INSERT INTO dev_projects (user_id, title, description, requirements_text, tech_stack, status) VALUES (?,?,?,?,?,?)",
        (uid, title, data.get("description",""), data.get("requirements_text",""),
         data.get("tech_stack",""), data.get("status","Active"))
    )
    rows = execute_query("SELECT * FROM dev_projects WHERE id=?", (pid,), fetch=True)
    return jsonify({"success": True, "project": dict(rows[0])}), 201

@app.route("/api/dev/projects/<int:pid>", methods=["GET"])
@jwt_required()
def dev_get_project(pid):
    uid = int(get_jwt_identity())
    rows = execute_query("SELECT * FROM dev_projects WHERE id=? AND user_id=?", (pid, uid), fetch=True)
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    project = dict(rows[0])
    project["diagrams"] = [dict(r) for r in execute_query(
        "SELECT * FROM dev_diagrams WHERE project_id=? ORDER BY created_at DESC", (pid,), fetch=True)]
    project["code"] = [dict(r) for r in execute_query(
        "SELECT * FROM dev_code WHERE project_id=? ORDER BY created_at DESC", (pid,), fetch=True)]
    return jsonify({"success": True, "project": project})

@app.route("/api/dev/projects/<int:pid>", methods=["PUT"])
@jwt_required()
def dev_update_project(pid):
    uid  = int(get_jwt_identity())
    data = request.get_json()
    execute_query(
        "UPDATE dev_projects SET title=?, description=?, requirements_text=?, tech_stack=?, status=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
        (data.get("title",""), data.get("description",""), data.get("requirements_text",""),
         data.get("tech_stack",""), data.get("status","Active"), pid, uid)
    )
    return jsonify({"success": True})

@app.route("/api/dev/projects/<int:pid>", methods=["DELETE"])
@jwt_required()
def dev_delete_project(pid):
    uid = int(get_jwt_identity())
    execute_query("DELETE FROM dev_projects WHERE id=? AND user_id=?", (pid, uid))
    return jsonify({"success": True})

# Diagrams
@app.route("/api/dev/projects/<int:pid>/diagrams", methods=["POST"])
@jwt_required()
def dev_generate_diagram(pid):
    uid  = int(get_jwt_identity())
    data = request.get_json()
    requirements = data.get("requirements", "")
    dtype        = data.get("diagram_type", "architecture")
    types_list   = data.get("types", [])  # for multi-diagram request

    rows = execute_query("SELECT * FROM dev_projects WHERE id=? AND user_id=?", (pid, uid), fetch=True)
    project_context = rows[0]["requirements_text"] if rows else ""

    try:
        if types_list:
            results = generate_multiple_diagrams(requirements or project_context, types_list, project_context)
            saved   = []
            for r in results:
                if r.get("success") and r.get("mermaid_code"):
                    did = execute_query(
                        "INSERT INTO dev_diagrams (project_id, user_id, diagram_type, title, mermaid_code, description) VALUES (?,?,?,?,?,?)",
                        (pid, uid, r["diagram_type"], r["title"], r["mermaid_code"], r["description"])
                    )
                    r["id"] = did
                    saved.append(r)
            return jsonify({"success": True, "diagrams": saved})
        else:
            result = generate_diagram(dtype, requirements or project_context, project_context)
            did = execute_query(
                "INSERT INTO dev_diagrams (project_id, user_id, diagram_type, title, mermaid_code, description) VALUES (?,?,?,?,?,?)",
                (pid, uid, result["diagram_type"], result["title"], result["mermaid_code"], result["description"])
            )
            result["id"] = did
            return jsonify({"success": True, "diagram": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dev/diagrams", methods=["GET"])
@jwt_required()
def dev_all_diagrams():
    uid  = int(get_jwt_identity())
    rows = execute_query("SELECT * FROM dev_diagrams WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (uid,), fetch=True)
    return jsonify({"success": True, "diagrams": [dict(r) for r in rows]})

# Code Generation
@app.route("/api/dev/projects/<int:pid>/code", methods=["POST"])
@jwt_required()
def dev_generate_code(pid):
    uid  = int(get_jwt_identity())
    data = request.get_json()
    requirements = data.get("requirements", "")
    language     = data.get("language", "python")

    rows = execute_query("SELECT * FROM dev_projects WHERE id=? AND user_id=?", (pid, uid), fetch=True)
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    project = rows[0]

    try:
        result = generate_code(
            requirements or project["requirements_text"],
            language, project.get("tech_stack", ""), project["title"]
        )
        cid = execute_query(
            "INSERT INTO dev_code (project_id, user_id, language, title, code_content, description) VALUES (?,?,?,?,?,?)",
            (pid, uid, result["language_key"], result["title"], result["code_content"], result["description"])
        )
        result["id"] = cid
        return jsonify({"success": True, "code": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dev/code/review", methods=["POST"])
@jwt_required()
def dev_code_review():
    data = request.get_json()
    code     = data.get("code", "")
    language = data.get("language", "python")
    context  = data.get("context", "")
    if not code:
        return jsonify({"error": "code is required"}), 400
    try:
        result = review_dev_code(code, language, context)
        return jsonify({"success": True, "review": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/dev/projects/<int:pid>/risk", methods=["POST"])
@jwt_required()
def dev_project_risk(pid):
    uid  = int(get_jwt_identity())
    data = request.get_json()
    rows = execute_query("SELECT * FROM dev_projects WHERE id=? AND user_id=?", (pid, uid), fetch=True)
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    p = rows[0]
    try:
        result = predict_dev_risk(
            p["title"], p.get("requirements_text",""),
            p.get("tech_stack",""), data.get("issues", [])
        )
        return jsonify({"success": True, "risk": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Messaging ────────────────────────────────────────────────────────────────
@app.route("/api/users/team", methods=["GET"])
@jwt_required()
def get_team_users():
    """Return all users of the opposite role (for the To: dropdown)."""
    uid  = int(get_jwt_identity())
    rows = execute_query("SELECT role FROM users WHERE id=?", (uid,), fetch=True)
    my_role    = rows[0]["role"] if rows else "qa_engineer"
    other_role = "developer" if my_role == "qa_engineer" else "qa_engineer"
    users = execute_query(
        "SELECT id, username, email, role FROM users WHERE role=? AND id!=?",
        (other_role, uid), fetch=True
    )
    return jsonify({"success": True, "users": [dict(u) for u in users]})

@app.route("/api/messages", methods=["GET"])
@jwt_required()
def get_platform_messages():
    uid = int(get_jwt_identity())
    box = request.args.get("box", "inbox")  # inbox | sent
    if box == "sent":
        msgs = execute_query(
            "SELECT m.*, u.username as receiver_name, u.email as receiver_email "
            "FROM platform_messages m JOIN users u ON u.id=m.receiver_id "
            "WHERE m.sender_id=? ORDER BY m.created_at DESC", (uid,), fetch=True)
    else:
        msgs = execute_query(
            "SELECT m.*, u.username as sender_name, u.email as sender_email "
            "FROM platform_messages m JOIN users u ON u.id=m.sender_id "
            "WHERE m.receiver_id=? ORDER BY m.created_at DESC", (uid,), fetch=True)
    result = []
    for m in msgs:
        d = dict(m)
        d["replies"] = [dict(r) for r in execute_query(
            "SELECT r.*, u.username as sender_name FROM message_replies r "
            "JOIN users u ON u.id=r.sender_id WHERE r.message_id=? ORDER BY r.created_at ASC",
            (d["id"],), fetch=True)]
        result.append(d)
    unread = execute_query(
        "SELECT COUNT(*) as cnt FROM platform_messages WHERE receiver_id=? AND is_read=0",
        (uid,), fetch=True)[0]["cnt"]
    return jsonify({"success": True, "messages": result, "unread_count": unread})

@app.route("/api/messages", methods=["POST"])
@jwt_required()
def send_message():
    uid  = int(get_jwt_identity())
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    subject     = data.get("subject", "(No subject)").strip()
    body        = data.get("body", "").strip()
    project_id  = data.get("project_id")
    if not receiver_id or not body:
        return jsonify({"error": "receiver_id and body are required"}), 400
    mid = execute_query(
        "INSERT INTO platform_messages (sender_id, receiver_id, project_id, subject, body) VALUES (?,?,?,?,?)",
        (uid, receiver_id, project_id, subject, body)
    )
    return jsonify({"success": True, "message_id": mid}), 201

@app.route("/api/messages/<int:mid>/reply", methods=["POST"])
@jwt_required()
def reply_message(mid):
    uid  = int(get_jwt_identity())
    data = request.get_json()
    body = data.get("body", "").strip()
    if not body:
        return jsonify({"error": "body is required"}), 400
    # Verify sender or receiver
    rows = execute_query("SELECT * FROM platform_messages WHERE id=?", (mid,), fetch=True)
    if not rows:
        return jsonify({"error": "Message not found"}), 404
    m = rows[0]
    if uid not in (m["sender_id"], m["receiver_id"]):
        return jsonify({"error": "Not allowed"}), 403
    rid = execute_query(
        "INSERT INTO message_replies (message_id, sender_id, body) VALUES (?,?,?)",
        (mid, uid, body)
    )
    # Mark as read for the other party
    execute_query("UPDATE platform_messages SET is_read=1 WHERE id=?", (mid,))
    return jsonify({"success": True, "reply_id": rid}), 201

@app.route("/api/messages/<int:mid>/read", methods=["PATCH"])
@jwt_required()
def mark_read(mid):
    uid = int(get_jwt_identity())
    execute_query(
        "UPDATE platform_messages SET is_read=1 WHERE id=? AND receiver_id=?", (mid, uid))
    return jsonify({"success": True})

@app.route("/api/messages/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    uid = int(get_jwt_identity())
    cnt = execute_query(
        "SELECT COUNT(*) as cnt FROM platform_messages WHERE receiver_id=? AND is_read=0",
        (uid,), fetch=True)[0]["cnt"]
    return jsonify({"success": True, "unread_count": cnt})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
