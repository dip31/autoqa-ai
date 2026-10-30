from dotenv import load_dotenv
from database.db import execute_query
from agents.repo_intelligence_agent import RepoIntelligenceAgent
from agents.github_agent import GitHubAgent
from agents.dev_code_agent import (
    generate_code,
    review_dev_code,
    predict_dev_risk,
)
from agents.diagram_agent import generate_diagram, generate_multiple_diagrams
from agents.qa_dev_bridge_agent import analyze_qa_to_dev
from agents.autonomous_agent import run_autonomous_qa
from agents.chatbot_agent import chat
from agents.report_agent import generate_report
from agents.risk_agent import predict_risk
from agents.generator_agent import generate_testcases
from agents.website_agent import analyze_website
from agents.code_agent import review_code
from agents.testcase_agent import review_testcase
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
)
import bcrypt
import sys
import os
import requests
import secrets
import json
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))


app = Flask(__name__)

# CORS – restrict origins in production; allow localhost in development
cors_origins = os.getenv("CORS_ORIGINS")
if cors_origins:
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
else:
    # Development default – only the React dev server
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
CORS(app, supports_credentials=True, origins=origins)

load_dotenv(override=True)

jwt_secret = os.getenv("SECRET_KEY")
if not jwt_secret:
    # In production (non‑debug) refuse to start with a fallback secret
    if not app.debug:
        raise RuntimeError("SECRET_KEY environment variable must be set in production")
    jwt_secret = "autoqa-secret-2024"  # dev fallback only
    app.logger.warning("Using default JWT secret – NOT safe for production")
app.config["JWT_SECRET_KEY"] = jwt_secret
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=7)
jwt = JWTManager(app)


# Initialize the database on first run
from database.init_db import init_db
init_db()


def db_save(query, params):
    try:
        execute_query(query, params)
    except Exception as e:
        app.logger.error(f"[DB Error] {e}")
        raise e


# ── Auth ────────────────────────────────────────────────────────────────
@app.route("/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not username or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return (
            jsonify({"error": "Password must be at least 6 characters"}),
            400,
        )

    # Check duplicate
    existing = execute_query(
        "SELECT id FROM users WHERE email=? OR username=?",
        (email, username),
        fetch=True,
    )
    if existing:
        return jsonify({"error": "Email or username already exists"}), 409

    role = data.get("role", "qa_engineer").strip()
    if role not in ("qa_engineer", "developer"):
        role = "qa_engineer"

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = execute_query(
        "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
        (username, email, hashed, role),
    )
    # Auto-create first chat session
    execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
        (user_id, "Welcome Chat"),
    )
    token = create_access_token(identity=str(user_id))
    return (
        jsonify(
            {
                "success": True,
                "token": token,
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "role": role,
                },
            }
        ),
        201,
    )


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    rows = execute_query(
        "SELECT * FROM users WHERE email=?", (email,), fetch=True
    )
    if not rows:
        return jsonify({"error": "Invalid email or password"}), 401

    user = rows[0]
    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user["id"]))
    return jsonify(
        {
            "success": True,
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user.get("role", "qa_engineer"),
            },
        }
    )


# ── GitHub OAuth ─────────────────────────────────────────────────────────────
@app.route("/auth/github/login")
def github_login():
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        return (
            jsonify({"error": "GITHUB_CLIENT_ID not configured in .env"}),
            500,
        )
    state = secrets.token_hex(16)
    redirect_uri = "http://localhost:5001/auth/github/callback"
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
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
    )
    data = res.json()
    token = data.get("access_token")
    if not token:
        err_desc = data.get("error_description", "No access token")
        return f"GitHub auth failed: {err_desc}", 400

    u_res = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}"},
    )
    gh_u = u_res.json()
    gh_id = str(gh_u.get("id"))
    gh_login = gh_u.get("login")

    # Try to find user by github_id
    rows = execute_query(
        "SELECT * FROM users WHERE github_id=?", (gh_id,), fetch=True
    )
    if rows:
        user = rows[0]
        execute_query(
            "UPDATE users SET github_token=? WHERE id=?", (token, user["id"])
        )
    else:
        # Check by email (fetch emails if needed)
        e_res = requests.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"token {token}"},
        )
        emails = e_res.json()
        primary_email = next(
            (e["email"] for e in emails if e["primary"]),
            f"{gh_login}@github.com",
        )

        rows = execute_query(
            "SELECT * FROM users WHERE email=?", (primary_email,), fetch=True
        )
        if rows:
            user = rows[0]
            execute_query(
                "UPDATE users SET github_id=?, github_token=? WHERE id=?",
                (gh_id, token, user["id"]),
            )
        else:
            # Create new
            uid = execute_query(
                "INSERT INTO users (username, email, password, role, github_id, github_token) VALUES (?,?,?,?,?,?)",
                (gh_login,
                 primary_email,
                 "GITHUB_OAUTH",
                 "qa_engineer",
                 gh_id,
                 token,
                 ),
            )
            execute_query(
                "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
                (uid, "GitHub Welcome"),
            )
            user = {
                "id": uid,
                "username": gh_login,
                "email": primary_email,
                "role": "qa_engineer",
            }

    jwt_token = create_access_token(identity=str(user["id"]))
    # Redirect to frontend callback route with token
    u_name = user['username']
    u_role = user.get('role', 'qa_engineer')
    u_id = user['id']
    frontend_url = f"http://localhost:3000/login?token={jwt_token}&username={u_name}&role={u_role}&id={u_id}"
    return redirect(frontend_url)


@app.route("/auth/me", methods=["GET"])
@jwt_required()
def me():
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT id, username, email, role, created_at FROM users WHERE id=?",
        (user_id,),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "User not found"}), 404

    # Stats
    tc = execute_query(
        "SELECT COUNT(*) as c FROM test_cases WHERE user_id=?",
        (user_id,),
        fetch=True,
    )[0]["c"]
    cr = execute_query(
        "SELECT COUNT(*) as c FROM code_reviews WHERE user_id=?",
        (user_id,),
        fetch=True,
    )[0]["c"]
    wt = execute_query(
        "SELECT COUNT(*) as c FROM website_tests WHERE user_id=?",
        (user_id,),
        fetch=True,
    )[0]["c"]
    # Check if GitHub is connected
    gh_rows = execute_query(
        "SELECT github_id, github_token FROM users WHERE id=?",
        (user_id,),
        fetch=True,
    )
    github_connected = bool(gh_rows[0]["github_id"]) if gh_rows else False

    return jsonify(
        {
            "success": True,
            "user": rows[0],
            "github_connected": github_connected,
            "stats": {
                "test_cases": tc,
                "code_reviews": cr,
                "website_tests": wt,
            },
        }
    )


# ── GitHub Intelligence ──────────────────────────────────────────────────────
@app.route("/api/github/repos", methods=["GET"])
@jwt_required()
def api_github_repos():
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True
    )
    if not rows or not rows[0]["github_token"]:
        return (
            jsonify(
                {
                    "success": False,
                    "repos": [],
                    "connected": False,
                    "error": "GitHub not connected",
                }
            ),
            200,
        )

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

    rows = execute_query(
        "SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True
    )
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
        rows = execute_query(
            "SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True
        )
        token = rows[0]["github_token"] if rows else None

        int_agent = RepoIntelligenceAgent(token)
        result = int_agent.analyze(repo_url, branch)

        if "error" in result:
            return jsonify(result), 400

        # Save analysis
        execute_query(
            "INSERT INTO github_analyses (user_id, repo_url, analysis_json) VALUES (?, ?, ?)",
            (user_id, repo_url, json.dumps(result)),
        )

        return jsonify({"success": True, "data": result})
    except Exception as e:
        app.logger.error(f"[Analyze Error] {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/github/history", methods=["GET"])
@jwt_required()
def api_github_history():
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM github_analyses WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
        fetch=True,
    )
    return jsonify({"success": True, "history": rows})


# ── Chat History ────────────────────────────────────────────────────────
@app.route("/chat/sessions", methods=["GET"])
@jwt_required()
def get_sessions():
    user_id = int(get_jwt_identity())
    sessions = execute_query(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC",
        (user_id,),
        fetch=True,
    )
    return jsonify({"success": True, "sessions": sessions})


@app.route("/chat/sessions", methods=["POST"])
@jwt_required()
def create_session():
    user_id = int(get_jwt_identity())
    title = request.get_json().get("title", "New Chat")
    sid = execute_query(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
        (user_id, title),
    )
    return jsonify({"success": True, "session_id": sid})


@app.route("/chat/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    user_id = int(get_jwt_identity())
    execute_query(
        "DELETE FROM chat_sessions WHERE id=? AND user_id=?",
        (session_id, user_id),
    )
    return jsonify({"success": True})


@app.route("/chat/sessions/<int:session_id>/messages", methods=["GET"])
@jwt_required()
def get_messages(session_id):
    user_id = int(get_jwt_identity())
    msgs = execute_query(
        "SELECT role, content, created_at FROM chat_messages WHERE session_id=? AND user_id=? ORDER BY created_at ASC",
        (session_id, user_id),
        fetch=True,
    )
    return jsonify({"success": True, "messages": msgs})


@app.route("/chat", methods=["POST"])
@jwt_required()
def api_chat():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id")

    if not messages:
        return jsonify({"error": "messages are required"}), 400
    try:
        reply = chat(messages)

        # Save to DB if session provided
        if session_id:
            last_user = next(
                (m for m in reversed(messages) if m["role"] == "user"), None
            )
            if last_user:
                execute_query(
                    "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (?,?,?,?)",
                    (session_id, user_id, "user", last_user["content"]),
                )
            execute_query(
                "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (?,?,?,?)",
                (session_id, user_id, "assistant", reply),
            )
            # Update session title from first user message
            first = execute_query(
                "SELECT COUNT(*) as c FROM chat_messages WHERE session_id=?",
                (session_id,),
                fetch=True,
            )[0]["c"]
            if first <= 2 and last_user:
                title = last_user["content"][:50]
                execute_query(
                    "UPDATE chat_sessions SET title=? WHERE id=?",
                    (title, session_id),
                )
            execute_query(
                "UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (session_id,),
            )

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
        db_save(
            "INSERT INTO test_cases (user_id, testcase, review_result, score) VALUES (?,?,?,?)",
            (user_id, testcase, str(result), result.get("score")),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/review-code", methods=["POST"])
@jwt_required()
def api_review_code():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    code = data.get("code", "").strip()
    language = data.get("language", "Python").strip()
    if len(code) > 50000:
        return jsonify({"error": "code content too large"}), 400
    try:
        result = review_code(code, language)
        db_save(
            "INSERT INTO code_reviews (user_id, code, language, result, score) VALUES (?,?,?,?,?)",
            (user_id, code[:5000], language, str(result), result.get("score")),
        )
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
        db_save(
            "INSERT INTO website_tests (user_id, url, result) VALUES (?,?,?)",
            (user_id, url, str(result)),
        )
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
    content = data.get("content", "").strip()
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

        db_save(
            "INSERT INTO reports (user_id, report_data) VALUES (?,?)",
            (user_id, json.dumps(result)),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── QA-to-Dev Bridge ─────────────────────────────────────────────────────────
@app.route("/api/qa-dev-bridge/analyze", methods=["POST"])
@jwt_required()
def api_qa_dev_bridge():
    data = request.get_json()
    qa_data = data.get("qa_data", {})
    system_mode = data.get("system_mode", "FULL")
    if not qa_data.get("bugs") and not qa_data.get("application"):
        return (
            jsonify({"error": "qa_data with bugs or application is required"}),
            400,
        )
    try:
        result = analyze_qa_to_dev(qa_data, system_mode)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Autonomous QA ───────────────────────────────────────────────────────
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
        return (
            jsonify({"error": "Requirement, URL, or Repo URL is required"}),
            400,
        )

    # Create run entry
    run_id = execute_query(
        "INSERT INTO autonomous_runs (user_id, title, module_name, requirement_text, url, repo_url, execution_mode, status) "
        "VALUES (?,?,?,?,?,?,?,?)", (user_id, title, module, req_text, url, repo_url, mode, "Starting"), )

    import threading

    thread = threading.Thread(target=run_autonomous_qa, args=(run_id,))
    thread.start()

    return jsonify({"success": True, "run_id": run_id}), 201


@app.route("/api/autonomous-qa/runs", methods=["GET"])
@jwt_required()
def api_get_autonomous_runs():
    user_id = int(get_jwt_identity())
    runs = execute_query(
        "SELECT * FROM autonomous_runs WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
        fetch=True,
    )
    return jsonify({"success": True, "runs": runs})


@app.route("/api/autonomous-qa/run/<int:run_id>", methods=["GET"])
@jwt_required()
def api_get_autonomous_run_details(run_id):
    user_id = int(get_jwt_identity())
    # Verify ownership
    run_rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=?",
        (run_id, user_id),
        fetch=True,
    )
    if not run_rows:
        return jsonify({"error": "Run not found"}), 404

    run = run_rows[0]
    scope = execute_query(
        "SELECT * FROM autonomous_scope WHERE run_id=?", (run_id,), fetch=True
    )
    test_cases = execute_query(
        "SELECT * FROM autonomous_test_cases WHERE run_id=?", (run_id,), fetch=True
    )
    logs = execute_query(
        "SELECT * FROM autonomous_execution_logs WHERE run_id=? ORDER BY timestamp ASC",
        (run_id,),
        fetch=True,
    )
    findings = execute_query(
        "SELECT * FROM autonomous_findings WHERE run_id=?", (run_id,), fetch=True
    )
    risk = execute_query(
        "SELECT * FROM autonomous_risk_analysis WHERE run_id=?", (run_id,), fetch=True
    )
    report = execute_query(
        "SELECT * FROM autonomous_reports WHERE run_id=?", (run_id,), fetch=True
    )
    healing = execute_query(
        "SELECT * FROM autonomous_healing_logs WHERE run_id=? ORDER BY timestamp ASC",
        (run_id,),
        fetch=True,
    )
    # Repo Intelligence
    repo_intel = execute_query(
        "SELECT analysis_json FROM autonomous_repo_intelligence WHERE run_id=?",
        (run_id,),
        fetch=True,
    )
    repo_data = (
        json.loads(repo_intel[0]["analysis_json"]) if repo_intel else None
    )

    return jsonify(
        {
            "success": True,
            "run": run,
            "scope": scope[0] if scope else None,
            "test_cases": test_cases,
            "logs": logs,
            "findings": findings,
            "risk": risk[0] if risk else None,
            "report": report[0] if report else None,
            "healing": healing,
            "repo_intelligence": repo_data,
        }
    )


# ── Report Image Generation ─────────────────────────────────────────────
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
    score = report_data.get("quality_score", 0)
    stats = report_data.get("stats", {})

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
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
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

    return (
        jsonify({"error": f"All Gemini models unavailable. {last_error}"}),
        503,
    )


# ── Developer Portal ─────────────────────────────────────────────────────────

# Projects
@app.route("/api/dev/projects", methods=["GET"])
@jwt_required()
def dev_list_projects():
    uid = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM dev_projects WHERE user_id=? ORDER BY created_at DESC",
        (uid,),
        fetch=True,
    )
    return jsonify({"success": True, "projects": [dict(r) for r in rows]})


@app.route("/api/dev/projects", methods=["POST"])
@jwt_required()
def dev_create_project():
    uid = int(get_jwt_identity())
    data = request.get_json()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    pid = execute_query(
        "INSERT INTO dev_projects (user_id, title, description, requirements_text, tech_stack, status) VALUES (?,?,?,?,?,?)",
        (uid,
         title,
         data.get(
             "description",
             ""),
         data.get(
             "requirements_text",
             ""),
         data.get(
             "tech_stack",
             ""),
         data.get(
             "status",
             "Active"),
         ),
    )
    rows = execute_query(
        "SELECT * FROM dev_projects WHERE id=?", (pid,), fetch=True
    )
    return jsonify({"success": True, "project": dict(rows[0])}), 201


@app.route("/api/dev/projects/<int:pid>", methods=["GET"])
@jwt_required()
def dev_get_project(pid):
    uid = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM dev_projects WHERE id=? AND user_id=?",
        (pid, uid),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    project = dict(rows[0])
    project["diagrams"] = [
        dict(r)
        for r in execute_query(
            "SELECT * FROM dev_diagrams WHERE project_id=? ORDER BY created_at DESC",
            (pid,),
            fetch=True,
        )
    ]
    project["code"] = [
        dict(r)
        for r in execute_query(
            "SELECT * FROM dev_code WHERE project_id=? ORDER BY created_at DESC",
            (pid,),
            fetch=True,
        )
    ]
    return jsonify({"success": True, "project": project})


@app.route("/api/dev/projects/<int:pid>", methods=["PUT"])
@jwt_required()
def dev_update_project(pid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    execute_query(
        "UPDATE dev_projects SET title=?, description=?, requirements_text=?, tech_stack=?, status=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (data.get(
            "title", ""), data.get(
            "description", ""), data.get(
                "requirements_text", ""), data.get(
                    "tech_stack", ""), data.get(
                        "status", "Active"), pid, uid, ), )
    return jsonify({"success": True})


@app.route("/api/dev/projects/<int:pid>", methods=["DELETE"])
@jwt_required()
def dev_delete_project(pid):
    uid = int(get_jwt_identity())
    execute_query(
        "DELETE FROM dev_projects WHERE id=? AND user_id=?", (pid, uid)
    )
    return jsonify({"success": True})


# Diagrams
@app.route("/api/dev/projects/<int:pid>/diagrams", methods=["POST"])
@jwt_required()
def dev_generate_diagram(pid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    requirements = data.get("requirements", "")
    dtype = data.get("diagram_type", "architecture")
    types_list = data.get("types", [])  # for multi-diagram request

    rows = execute_query(
        "SELECT * FROM dev_projects WHERE id=? AND user_id=?",
        (pid, uid),
        fetch=True,
    )
    project_context = rows[0]["requirements_text"] if rows else ""

    try:
        if types_list:
            results = generate_multiple_diagrams(
                requirements or project_context, types_list, project_context
            )
            saved = []
            for r in results:
                if r.get("success") and r.get("mermaid_code"):
                    did = execute_query(
                        "INSERT INTO dev_diagrams (project_id, user_id, diagram_type, title, mermaid_code, description) VALUES (?,?,?,?,?,?)",
                        (pid,
                         uid,
                         r["diagram_type"],
                             r["title"],
                             r["mermaid_code"],
                             r["description"],
                             ),
                        )
                    r["id"] = did
                    saved.append(r)
            return jsonify({"success": True, "diagrams": saved})
        else:
            result = generate_diagram(
                dtype, requirements or project_context, project_context
            )
            did = execute_query(
                "INSERT INTO dev_diagrams (project_id, user_id, diagram_type, title, mermaid_code, description) VALUES (?,?,?,?,?,?)",
                (pid,
                 uid,
                 result["diagram_type"],
                     result["title"],
                     result["mermaid_code"],
                     result["description"],
                     ),
            )
            result["id"] = did
            return jsonify({"success": True, "diagram": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dev/diagrams", methods=["GET"])
@jwt_required()
def dev_all_diagrams():
    uid = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM dev_diagrams WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (uid,),
        fetch=True,
    )
    return jsonify({"success": True, "diagrams": [dict(r) for r in rows]})


# Code Generation
@app.route("/api/dev/projects/<int:pid>/code", methods=["POST"])
@jwt_required()
def dev_generate_code(pid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    requirements = data.get("requirements", "")
    language = data.get("language", "python")

    rows = execute_query(
        "SELECT * FROM dev_projects WHERE id=? AND user_id=?",
        (pid, uid),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    project = rows[0]

    try:
        result = generate_code(
            requirements or project["requirements_text"],
            language,
            project.get("tech_stack", ""),
            project["title"],
        )
        cid = execute_query(
            "INSERT INTO dev_code (project_id, user_id, language, title, code_content, description) VALUES (?,?,?,?,?,?)",
            (pid,
             uid,
             result["language_key"],
                 result["title"],
                 result["code_content"],
                 result["description"],
                 ),
        )
        result["id"] = cid
        return jsonify({"success": True, "code": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dev/code/review", methods=["POST"])
@jwt_required()
def dev_code_review():
    data = request.get_json()
    code = data.get("code", "")
    language = data.get("language", "python")
    context = data.get("context", "")
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
    uid = int(get_jwt_identity())
    data = request.get_json()
    rows = execute_query(
        "SELECT * FROM dev_projects WHERE id=? AND user_id=?",
        (pid, uid),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Project not found"}), 404
    p = rows[0]
    try:
        result = predict_dev_risk(
            p["title"],
            p.get("requirements_text", ""),
            p.get("tech_stack", ""),
            data.get("issues", []),
        )
        return jsonify({"success": True, "risk": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Messaging ────────────────────────────────────────────────────────────────
@app.route("/api/users/team", methods=["GET"])
@jwt_required()
def get_team_users():
    """Return all users of the opposite role (for the To: dropdown)."""
    uid = int(get_jwt_identity())
    rows = execute_query(
        "SELECT role FROM users WHERE id=?", (uid,), fetch=True
    )
    my_role = rows[0]["role"] if rows else "qa_engineer"
    other_role = "developer" if my_role == "qa_engineer" else "qa_engineer"
    users = execute_query(
        "SELECT id, username, email, role FROM users WHERE role=? AND id!=?",
        (other_role, uid),
        fetch=True,
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
            "WHERE m.sender_id=? ORDER BY m.created_at DESC", (uid,), fetch=True, )
    else:
        msgs = execute_query(
            "SELECT m.*, u.username as sender_name, u.email as sender_email "
            "FROM platform_messages m JOIN users u ON u.id=m.sender_id "
            "WHERE m.receiver_id=? ORDER BY m.created_at DESC",
            (uid,),
            fetch=True,
        )
    result = []
    for m in msgs:
        d = dict(m)
        d["replies"] = [
            dict(r)
            for r in execute_query(
                "SELECT r.*, u.username as sender_name FROM message_replies r "
                "JOIN users u ON u.id=r.sender_id WHERE r.message_id=? ORDER BY r.created_at ASC",
                (d["id"],),
                fetch=True,
            )
        ]
        result.append(d)
    unread = execute_query(
        "SELECT COUNT(*) as cnt FROM platform_messages WHERE receiver_id=? AND is_read=0",
        (uid,),
        fetch=True,
    )[0]["cnt"]
    return jsonify(
        {"success": True, "messages": result, "unread_count": unread}
    )


@app.route("/api/messages", methods=["POST"])
@jwt_required()
def send_message():
    uid = int(get_jwt_identity())
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    subject = data.get("subject", "(No subject)").strip()
    body = data.get("body", "").strip()
    project_id = data.get("project_id")
    if not receiver_id or not body:
        return jsonify({"error": "receiver_id and body are required"}), 400
    mid = execute_query(
        "INSERT INTO platform_messages (sender_id, receiver_id, project_id, subject, body) VALUES (?,?,?,?,?)",
        (uid, receiver_id, project_id, subject, body),
    )
    return jsonify({"success": True, "message_id": mid}), 201


@app.route("/api/messages/<int:mid>/reply", methods=["POST"])
@jwt_required()
def reply_message(mid):
    uid = int(get_jwt_identity())
    data = request.get_json()
    body = data.get("body", "").strip()
    if not body:
        return jsonify({"error": "body is required"}), 400
    # Verify sender or receiver
    rows = execute_query(
        "SELECT * FROM platform_messages WHERE id=?", (mid,), fetch=True
    )
    if not rows:
        return jsonify({"error": "Message not found"}), 404
    m = rows[0]
    if uid not in (m["sender_id"], m["receiver_id"]):
        return jsonify({"error": "Not allowed"}), 403
    rid = execute_query(
        "INSERT INTO message_replies (message_id, sender_id, body) VALUES (?,?,?)",
        (mid, uid, body),
    )
    # Mark as read for the other party
    execute_query("UPDATE platform_messages SET is_read=1 WHERE id=?", (mid,))
    return jsonify({"success": True, "reply_id": rid}), 201


@app.route("/api/messages/<int:mid>/read", methods=["PATCH"])
@jwt_required()
def mark_read(mid):
    uid = int(get_jwt_identity())
    execute_query(
        "UPDATE platform_messages SET is_read=1 WHERE id=? AND receiver_id=?",
        (mid, uid),
    )
    return jsonify({"success": True})


@app.route("/api/messages/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    uid = int(get_jwt_identity())
    cnt = execute_query(
        "SELECT COUNT(*) as cnt FROM platform_messages WHERE receiver_id=? AND is_read=0",
        (uid,),
        fetch=True,
    )[0]["cnt"]
    return jsonify({"success": True, "unread_count": cnt})


# ── AgentQE (Advanced ML Pipeline) ──────────────────────────────────────────
@app.route("/api/agentqe/run", methods=["POST"])
@jwt_required()
def api_agentqe_run():
    from agentqe.pipeline import start_agentqe_run
    user_id = int(get_jwt_identity())
    data = request.get_json()

    title       = data.get("title", "AgentQE Run").strip()
    module      = data.get("module_name", "General").strip()
    req_text    = data.get("requirement_text", "").strip()
    url         = data.get("url", "").strip()
    repo_url    = data.get("repo_url", "").strip()
    mode        = data.get("execution_mode", "AgentQE Pipeline")
    max_cycles  = int(data.get("max_cycles", 3))

    if not req_text and not url:
        return jsonify({"error": "requirement_text or url is required"}), 400

    run_id = execute_query(
        "INSERT INTO autonomous_runs "
        "(user_id, title, module_name, requirement_text, url, repo_url, execution_mode, status, max_cycles) "
        "VALUES (?,?,?,?,?,?,?,?,?)", (user_id, title, module, req_text, url, repo_url, mode, "Starting", max_cycles), )
    start_agentqe_run(run_id)
    return jsonify({"success": True, "run_id": run_id}), 201


@app.route("/api/agentqe/review/<int:run_id>", methods=["POST"])
@jwt_required()
def api_agentqe_review(run_id):
    from agentqe.human.review_service import HumanReviewService
    user_id = int(get_jwt_identity())
    data    = request.get_json() or {}

    decision = data.get("decision", "").strip().upper()
    feedback = data.get("feedback", "").strip()
    cycle    = int(data.get("cycle", 1))

    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=?",
        (run_id, user_id), fetch=True
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404

    try:
        review = HumanReviewService().submit_review(
            run_id=run_id, decision=decision, feedback=feedback, cycle=cycle
        )
        return jsonify({"success": True, "review": review})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Application Understanding ────────────────────────────────────────────────
@app.route("/api/agentqe/application/understand", methods=["POST"])
@jwt_required()
def api_agentqe_application_understand():
    from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    url = data.get("url", "").strip()
    repo_url = data.get("repo_url", "").strip()
    requirement = data.get("requirement", "").strip()
    module_name = data.get("module_name", "").strip()
    crawl_config = data.get("crawl_config", {})

    # At least one input is required
    if not url and not repo_url and not requirement:
        return jsonify({"error": "At least one of url, repo_url, or requirement is required"}), 400

    # Get GitHub token if available
    rows = execute_query(
        "SELECT github_token FROM users WHERE id=?", (user_id,), fetch=True
    )
    github_token = rows[0]["github_token"] if rows and rows[0]["github_token"] else None

    try:
        agent = ApplicationUnderstandingAgent(github_token)
        input_data = {
            "url": url,
            "repo_url": repo_url,
            "requirement": requirement,
            "module_name": module_name,
            "metadata": {"crawl_config": crawl_config} if crawl_config else {},
        }
        context = agent.analyze(input_data)
        return jsonify({"success": True, "context": context.to_dict()})
    except Exception as e:
        return jsonify({"error": f"Application understanding failed: {str(e)}"}), 500


@app.route("/api/agentqe/tests/generate", methods=["POST"])
@jwt_required()
def api_agentqe_tests_generate():
    from agentqe.models.context import ApplicationContext
    from agentqe.agents.test_planning_agent import TestPlanningAgent
    from agentqe.agents.user_agents import UserAgent
    from agentqe.agents.engineering_agent import EngineeringQAAgent
    from agentqe.pool.candidate_pool import CandidateTestPool
    from agentqe.enrichment.enricher import TestEnricher

    try:
        data = request.get_json() or {}
        context_data = data.get("application_context")
        
        if not context_data:
            return jsonify({"error": "application_context is required"}), 400
            
        context = ApplicationContext(**{k: v for k, v in context_data.items() if hasattr(ApplicationContext, k)})

        # 1. Test Planning
        test_planner = TestPlanningAgent()
        test_plan = test_planner.plan(context)
        
        # 2. Multi-perspective Generation
        user_agent = UserAgent()
        try:
            user_tests = user_agent.generate(context, test_plan)
        except Exception as e:
            app.logger.error(f"UserAgent failed: {e}")
            user_tests = []
            
        engineering_agent = EngineeringQAAgent()
        try:
            engineering_tests = engineering_agent.generate(context, test_plan)
        except Exception as e:
            app.logger.error(f"EngineeringQAAgent failed: {e}")
            engineering_tests = []
            
        # 3. Candidate Pool Merging
        pool = CandidateTestPool()
        merged_tests = pool.merge(user_tests, engineering_tests)
        
        # 4. Enrichment
        enricher = TestEnricher()
        enriched_tests = enricher.enrich(merged_tests, repository_data=context.repository_data)
        
        return jsonify({
            "success": True,
            "test_plan": test_plan,
            "user_tests": [t.to_dict() for t in user_tests],
            "engineering_tests": [t.to_dict() for t in engineering_tests],
            "candidate_tests": [t.to_dict() for t in enriched_tests],
            "metadata": {
                "total_generated": len(user_tests) + len(engineering_tests),
                "total_merged": len(enriched_tests)
            }
        })
        
    except Exception as e:
        app.logger.error(f"Test generation failed: {e}")
        return jsonify({"error": f"Test generation failed: {str(e)}"}), 500

# ── Security Validation Engine (Phase 2 & 5A) ───────────────────────────────────────
@app.route("/api/security/run", methods=["POST"])
@jwt_required()
def api_security_run():
    from agentqe.security.security_preflight import run_preflight
    from agentqe.security.active_testing_profiles import validate_profile, get_profile_limits
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    target_url = data.get("target_url", "").strip()
    title = data.get("title", "Security Validation Run").strip()
    mode = data.get("mode", "passive")  # 'passive', 'active', or 'zap'
    profile = data.get("profile", "passive_only")
    dry_run = bool(data.get("dry_run", False))
    confirmed = bool(data.get("confirmed", False))

    if not target_url:
        return jsonify({"error": "target_url is required"}), 400

    if mode not in ("passive", "active", "zap"):
        return jsonify({"error": "mode must be 'passive', 'active', or 'zap'"}), 400

    # Default profile for zap mode
    if mode == "zap" and profile == "passive_only":
        profile = "zap_baseline"

    # Feature gate for ZAP
    if mode == "zap":
        zap_enabled = os.getenv("ZAP_ENABLED", "false").lower() in ("1", "true", "yes")
        if not zap_enabled:
            return jsonify({
                "success": False,
                "error": "ZAP Baseline scans are disabled on this deployment",
                "reason_code": "ZAP_DISABLED"
            }), 403

    if not validate_profile(profile):
        return jsonify({"error": f"Invalid or disabled profile: {profile}"}), 400

    # Centralized preflight
    decision = run_preflight(user_id, target_url)
    if not decision.allowed:
        return jsonify({
            "success": False,
            "error": decision.message,
            "reason_code": decision.reason_code
        }), 403

    # Authorization required for both passive and active modes
    from agentqe.security.authorization.authorization_repository import get_verified_authorization
    auth = get_verified_authorization(user_id, decision.scope.host)
    if not auth:
        return jsonify({
            "success": False,
            "error": "Target authorization required. Create and verify an authorization for this hostname first.",
            "reason_code": "REQUIRES_AUTHORIZATION",
            "hostname": decision.scope.host,
            "challenge_path": "/.well-known/autoqa-challenge.txt"
        }), 403

    # For active mode, additional checks
    if mode == 'active':
        # Check profile limits
        profile_limits = get_profile_limits(profile)
        
        # For active mode, require confirmation unless dry_run
        if not dry_run and not data.get("confirmed", False):
            return jsonify({
                "success": False,
                "error": "Active assessment requires explicit confirmation",
                "reason_code": "REQUIRES_CONFIRMATION",
                "requires_confirmation": True
            }), 403
    else:
        profile_limits = get_profile_limits(profile)

    # Persist a security run record (reuse autonomous_runs with run_type='security')
    profile_limits_str = json.dumps(profile_limits)
    run_id = execute_query(
        "INSERT INTO autonomous_runs "
        "(user_id, title, module_name, requirement_text, url, repo_url, execution_mode, status, run_type, mode, profile, dry_run, confirmed, profile_limits, active_authorization_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, title, "Security", "", decision.normalized_target, "", "Security Validation", 
         "Authorized", "security",
         mode, profile, 1 if dry_run else 0, 1 if confirmed else 0, profile_limits_str, auth.id),
    )

    return jsonify({
        "success": True,
        "run_id": run_id,
        "normalized_target": decision.normalized_target,
        "scope": {
            "scheme": decision.scope.scheme if decision.scope else None,
            "host": decision.scope.host if decision.scope else None,
            "port": decision.scope.port if decision.scope else None,
        },
        "mode": mode,
        "profile": profile,
        "dry_run": dry_run,
        "requires_confirmation": mode == 'active' and not dry_run and not confirmed,
    }), 201


@app.route("/api/security/runs", methods=["GET"])
@jwt_required()
def api_security_runs():
    user_id = int(get_jwt_identity())
    runs = execute_query(
        "SELECT * FROM autonomous_runs WHERE user_id=? AND run_type='security' ORDER BY created_at DESC",
        (user_id,),
        fetch=True,
    )
    return jsonify({"success": True, "runs": runs})


@app.route("/api/security/run/<int:run_id>", methods=["GET"])
@jwt_required()
def api_security_run_detail(run_id):
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    from urllib.parse import urlparse
    parsed_target = urlparse(run.get("url") or "")
    return jsonify({
        "success": True,
        "run": run,
        "normalized_target": run.get("url"),
        "scope": {
            "scheme": parsed_target.scheme or None,
            "host": parsed_target.hostname or None,
            "port": parsed_target.port,
        },
    })


# ---- Target authorization (ownership verification) ----
@app.route("/api/security/authorize", methods=["POST"])
@jwt_required()
def api_security_authorize_create():
    from agentqe.security.authorization.ownership_verifier import start_verification
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    hostname = data.get("hostname", "").strip().lower()
    scheme = data.get("scheme", "https").strip().lower()
    port = data.get("port")
    path_prefix = data.get("path_prefix", "/")
    allow_subdomains = bool(data.get("allow_subdomains", False))

    if not hostname:
        return jsonify({"error": "hostname is required"}), 400

    auth = start_verification(
        user_id=user_id,
        hostname=hostname,
        scheme=scheme,
        port=port,
        path_prefix=path_prefix,
        allow_subdomains=allow_subdomains,
    )
    return jsonify({
        "success": True,
        "authorization_id": auth.id,
        "hostname": auth.hostname,
        "challenge_token": auth.verification_token,
        "challenge_url": f"{auth.scheme}://{auth.hostname}/.well-known/autoqa-challenge.txt",
        "expires_at": auth.expires_at.isoformat() if auth.expires_at else None,
    }), 201


@app.route("/api/security/authorize/verify", methods=["POST"])
@jwt_required()
def api_security_authorize_verify():
    from agentqe.security.authorization.ownership_verifier import verify_hosted_file
    from agentqe.security.authorization.authorization_repository import get_authorization
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    auth_id = data.get("authorization_id", "").strip()
    if not auth_id:
        return jsonify({"error": "authorization_id required"}), 400
    auth = get_authorization(auth_id)
    if not auth or auth.user_id != user_id:
        return jsonify({"error": "Authorization not found"}), 404
    try:
        verify_hosted_file(auth)
        return jsonify({"success": True, "verified": True})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.route("/api/security/authorizations", methods=["GET"])
@jwt_required()
def api_security_authorizations_list():
    from agentqe.security.authorization.authorization_repository import get_user_authorizations
    user_id = int(get_jwt_identity())
    auths = get_user_authorizations(user_id)
    return jsonify({
        "success": True,
        "authorizations": [
            {
                "id": a.id,
                "hostname": a.hostname,
                "scheme": a.scheme,
                "port": a.port,
                "path_prefix": a.path_prefix,
                "allow_subdomains": a.allow_subdomains,
                "verification_status": a.verification_status,
                "verified_at": a.verified_at.isoformat() if a.verified_at else None,
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                "revoked_at": a.revoked_at.isoformat() if a.revoked_at else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in auths
        ]
    })


@app.route("/api/security/authorizations/<auth_id>", methods=["DELETE"])
@jwt_required()
def api_security_authorizations_revoke(auth_id):
    from agentqe.security.authorization.authorization_repository import revoke_authorization
    user_id = int(get_jwt_identity())
    ok = revoke_authorization(auth_id, user_id)
    if not ok:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})


# ---- Findings & evidence retrieval ----
@app.route("/api/security/run/<int:run_id>/findings", methods=["GET"])
@jwt_required()
def api_security_run_findings(run_id):
    user_id = int(get_jwt_identity())
    # verify ownership
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    findings = execute_query(
        "SELECT * FROM security_findings WHERE run_id=? ORDER BY created_at DESC",
        (run_id,),
        fetch=True,
    )
    return jsonify({"success": True, "findings": findings})


@app.route("/api/security/finding/<int:finding_id>/evidence", methods=["GET"])
@jwt_required()
def api_security_finding_evidence(finding_id):
    user_id = int(get_jwt_identity())
    # ensure finding belongs to user's run
    rows = execute_query(
        """SELECT sf.* FROM security_findings sf
           JOIN autonomous_runs ar ON sf.run_id = ar.id
           WHERE sf.id=? AND ar.user_id=? AND ar.run_type='security'""",
        (finding_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Finding not found"}), 404
    evidences = execute_query(
        "SELECT * FROM security_evidence WHERE finding_id=? ORDER BY created_at",
        (finding_id,),
        fetch=True,
    )
    return jsonify({"success": True, "evidence": evidences})


# ---- Start security run execution (background) ----
@app.route("/api/security/run/<int:run_id>/start", methods=["POST"])
@jwt_required()
def api_security_run_start(run_id):
    import threading
    from agentqe.security.security_runner import execute_security_run_safely
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    if run["status"] not in ("Authorized", "Pending", "Failed"):
        return jsonify({"error": f"Run cannot be started from status {run['status']}"}), 400

    execute_query(
        "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP, "
        "error_summary=NULL WHERE id=?",
        (run_id,),
    )
    thread = threading.Thread(target=execute_security_run_safely, args=(run_id,), daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Security run started", "status": "Running"})


# ---- Cancel security run ----
@app.route("/api/security/run/<int:run_id>/cancel", methods=["POST"])
@jwt_required()
def api_security_run_cancel(run_id):
    from agentqe.security.security_runner import set_cancelled
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    if run["status"] not in ("Running", "Authorized", "Pending"):
        return jsonify({"error": f"Run cannot be cancelled from status {run['status']}"}), 400

    set_cancelled(run_id, True)
    return jsonify({"success": True, "message": "Cancellation requested"})


# ---- Security Report Generation ----
@app.route("/api/security/run/<int:run_id>/report", methods=["GET"])
@jwt_required()
def api_security_run_report(run_id):
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    if run["status"] != "Completed":
        return jsonify({"error": "Report can only be generated for completed runs"}), 400

    try:
        from agents.security_report_agent import generate_security_report
        report = generate_security_report(run_id)
        if "error" in report:
            return jsonify({"error": report["error"]}), 500
        return jsonify({"success": True, "report": report})
    except Exception as e:
        app.logger.error(f"[Security Report Error] {e}")
        return jsonify({"error": f"Failed to generate report: {str(e)}"}), 500


# ---- Phase 5A: Active Testing Endpoints ----

@app.route("/api/security/run/<int:run_id>/dry-run", methods=["POST"])
@jwt_required()
def api_security_run_dry_run(run_id):
    """Generate a dry-run plan for an active assessment."""
    from agentqe.security.active_testing_policy import generate_dry_run_plan, ActiveTestingContext
    from agentqe.security.security_preflight import run_preflight
    from agentqe.security.active_testing_profiles import validate_profile
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    profile = data.get("profile", "safe_active")
    
    if not validate_profile(profile):
        return jsonify({"error": f"Invalid or disabled profile: {profile}"}), 400
    
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    
    target_url = run["url"]
    decision = run_preflight(user_id, target_url)
    if not decision.allowed:
        return jsonify({"error": "Preflight failed"}), 403
    
    # Build context for dry-run
    from agentqe.security.scope_validator import ScopeDefinition
    scope_def = ScopeDefinition(
        scheme=decision.scope.scheme,
        host=decision.scope.host,
        port=decision.scope.port,
        path_prefix="/",
        allow_subdomains=False,
    )
    
    from agentqe.security.active_testing_policy import generate_dry_run_plan
    plan = generate_dry_run_plan(ActiveTestingContext(
        user_id=user_id,
        target_url=target_url,
        normalized_target=decision.normalized_target,
        scope=scope_def,
        mode='active',
        profile=profile,
        dry_run=True,
        confirmed=False,
    ))
    
    return jsonify({"success": True, "plan": plan})


@app.route("/api/security/run/<int:run_id>/confirm", methods=["POST"])
@jwt_required()
def api_security_run_confirm(run_id):
    """Confirm an active assessment to proceed with execution."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    confirmation_token = data.get("confirmation_token", "")
    
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    run = rows[0]
    
    if run["mode"] != 'active':
        return jsonify({"error": "Only active mode runs require confirmation"}), 400
    
    if run["status"] != "AwaitingConfirmation":
        return jsonify({"error": f"Run cannot be confirmed from status {run['status']}"}), 400
    
    if run.get("confirmation_token") != confirmation_token:
        return jsonify({"error": "Invalid confirmation token"}), 400
    
    # Check token expiration
    if run.get("confirmation_expires_at"):
        from datetime import datetime
        expires = datetime.fromisoformat(run["confirmation_expires_at"])
        if datetime.utcnow() > expires:
            return jsonify({"error": "Confirmation token expired"}), 400
    
    # Update run status to Authorized and store confirmation
    execute_query(
        "UPDATE autonomous_runs SET status='Authorized', confirmed=1, confirmed_at=CURRENT_TIMESTAMP WHERE id=?",
        (run_id,),
    )
    
    return jsonify({"success": True, "message": "Assessment confirmed and ready to start"})


@app.route("/api/security/profiles", methods=["GET"])
@jwt_required()
def api_security_profiles():
    """List available testing profiles."""
    from agentqe.security.active_testing_profiles import list_profiles, get_active_profiles
    return jsonify({
        "success": True,
        "profiles": list_profiles(),
        "active_profiles": get_active_profiles(),
    })


@app.route("/api/security/profiles/<profile_id>", methods=["GET"])
@jwt_required()
def api_security_profile_detail(profile_id):
    """Get profile details including limits."""
    from agentqe.security.active_testing_profiles import get_profile, get_profile_limits
    profile = get_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    limits = get_profile_limits(profile_id)
    return jsonify({
        "success": True,
        "profile": profile,
        "limits": limits,
    })


@app.route("/api/security/run/<int:run_id>/audit", methods=["GET"])
@jwt_required()
def api_security_run_audit(run_id):
    """Get audit log for a security run."""
    user_id = int(get_jwt_identity())
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND user_id=? AND run_type='security'",
        (run_id, user_id),
        fetch=True,
    )
    if not rows:
        return jsonify({"error": "Run not found"}), 404
    
    from agentqe.security.audit_logging import get_audit_logger
    audit_logger = get_audit_logger()
    events = audit_logger.query_events(run_id=run_id, limit=200)
    return jsonify({"success": True, "events": events})

# ---- Phase 5D: Finding Lifecycle Management Endpoints ----

# ---- Phase 5D: Finding Lifecycle Management Endpoints ----

@app.route("/api/security/findings", methods=["GET"])
@jwt_required()
def api_security_findings_list():
    """List findings for the current user with filtering options."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    user_id = int(get_jwt_identity())
    lifecycle_state = request.args.get("lifecycle_state")
    verification_state = request.args.get("verification_state")
    severity = request.args.get("severity")
    validator_id = request.args.get("validator_id")
    run_id = request.args.get("run_id", type=int)
    limit = min(int(request.args.get("limit", 50)), 100)
    offset = int(request.args.get("offset", 0))
    
    # Build query
    conditions = ["f.run_id = ar.id", "ar.user_id = ?", "ar.run_type = 'security'"]
    params = [int(get_jwt_identity())]
    
    if lifecycle_state:
        conditions.append("f.lifecycle_state = ?")
        params.append(lifecycle_state)
    if verification_state:
        conditions.append("f.verification_state = ?")
        params.append(verification_state)
    if severity:
        conditions.append("f.severity = ?")
        params.append(severity)
    if validator_id:
        conditions.append("f.validator_id = ?")
        params.append(validator_id)
    if run_id:
        conditions.append("f.run_id = ?")
        params.append(run_id)
    
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT f.*, l.lifecycle_state, l.verification_state, l.resolution_type,
               l.resolution_reason, l.resolved_at, l.resolved_by,
               l.acknowledged_at, l.acknowledged_by, l.remediation_started_at,
               l.remediation_started_by, l.resolved_at, l.resolved_by,
               l.accepted_risk_at, l.accepted_risk_by, l.risk_acceptance_reason,
               l.reopened_count, l.verification_state, l.verification_confidence,
               l.version
        FROM security_findings f
        LEFT JOIN security_finding_lifecycle l ON f.id = l.finding_id
        JOIN autonomous_runs ar ON f.run_id = ar.id
        WHERE {where_clause}
        ORDER BY f.created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    findings = execute_query(query, tuple(params), fetch=True)
    return jsonify({"success": True, "findings": findings})


@app.route("/api/security/findings/<int:finding_id>", methods=["GET"])
@jwt_required()
def api_security_finding_detail(finding_id):
    """Get detailed finding with lifecycle information."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    user_id = int(get_jwt_identity())
    lifecycle_mgr = get_lifecycle_manager()
    finding = lifecycle_mgr.get_finding_with_lifecycle(finding_id, int(get_jwt_identity()))
    
    if not finding:
        return jsonify({"error": "Finding not found"}), 404
    
    return jsonify({"success": True, "finding": finding})


@app.route("/api/security/findings/<int:finding_id>/history", methods=["GET"])
@jwt_required()
def api_security_finding_history(finding_id):
    """Get lifecycle history for a finding."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    
    lifecycle_mgr = get_lifecycle_manager()
    
    # Verify ownership
    rows = execute_query(
        """SELECT f.id FROM security_findings f
           JOIN autonomous_runs ar ON f.run_id = ar.id
           WHERE f.id = ? AND ar.user_id = ? AND ar.run_type = 'security'""",
        (finding_id, int(get_jwt_identity())), fetch=True)
    if not rows:
        return jsonify({"error": "Finding not found"}), 404
    
    history = get_lifecycle_manager().get_history(finding_id)
    return jsonify({"success": True, "history": history})


@app.route("/api/security/findings/<int:finding_id>/transition", methods=["POST"])
@jwt_required()
def api_security_finding_transition(finding_id):
    """Transition finding to a new lifecycle state."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager, LifecycleState, ResolutionType
    
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    lifecycle_mgr = get_lifecycle_manager()
    
    # Validate input
    new_state_str = data.get("lifecycle_state")
    if not new_state_str:
        return jsonify({"error": "lifecycle_state is required"}), 400
    
    try:
        new_state = LifecycleState(new_state_str)
    except ValueError:
        return jsonify({"error": f"Invalid lifecycle state: {new_state_str}"}), 400
    
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "Reason is required"}), 400
    
    evidence_refs = data.get("evidence_refs", [])
    resolution_type = data.get("resolution_type")
    resolution_reason = data.get("resolution_reason", "")
    resolution_evidence_refs = data.get("resolution_evidence_refs", [])
    expected_version = data.get("expected_version")
    
    # Validate resolution requirements
    if new_state == LifecycleState.RESOLVED and not resolution_type:
        return jsonify({"error": "Resolution type required when resolving"}), 400
    
    # Convert enums
    try:
        if resolution_type:
            resolution_type = ResolutionType(resolution_type)
    except ValueError:
        return jsonify({"error": f"Invalid resolution type: {resolution_type}"}), 400
    
    try:
        new_state = LifecycleState(new_state_str)
    except ValueError:
        return jsonify({"error": f"Invalid lifecycle state: {new_state_str}"}), 400
    
    # Get lifecycle manager
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    lifecycle_mgr = get_lifecycle_manager()
    
    # Perform transition
    if new_state == LifecycleState.ACKNOWLEDGED:
        success, msg = lifecycle_mgr.acknowledge_finding(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    elif new_state == LifecycleState.IN_REMEDIATION:
        success, msg = lifecycle_mgr.start_remediation(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    elif new_state == LifecycleState.RESOLVED:
        if not resolution_type:
            return jsonify({"error": "Resolution type required"}), 400
        success, msg = lifecycle_mgr.resolve_finding(
            finding_id, int(get_jwt_identity()), 
            resolution_type=ResolutionType(resolution_type),
            resolution_reason=resolution_reason,
            resolution_evidence_refs=resolution_evidence_refs,
            expected_version=data.get("expected_version")
        )
    elif new_state == LifecycleState.ACCEPTED_RISK:
        success, msg = lifecycle_mgr.accept_risk(
            finding_id, int(get_jwt_identity()), reason=resolution_reason
        )
    elif new_state == LifecycleState.REOPENED:
        success, msg = lifecycle_mgr.reopen_finding(
            finding_id, int(get_jwt_identity()), 
            recurrence_evidence=data.get("recurrence_evidence", [])
        )
    elif new_state == LifecycleState.ACKNOWLEDGED:
        success, msg = lifecycle_mgr.acknowledge_finding(
            finding_id, int(get_jwt_identity()), evidence_refs=evidence_refs
        )
    else:
        return jsonify({"error": f"Transition to {new_state.value} not supported via this endpoint"}), 400
    
    if not success:
        return jsonify({"error": msg}), 400
    
    return jsonify({"success": True, "message": msg})


@app.route("/api/security/findings/<int:finding_id>/reverify", methods=["POST"])
@jwt_required()
def api_security_finding_reverify(finding_id):
    """Request reverification of a finding."""
    from agentqe.security.finding_lifecycle import get_lifecycle_manager
    from agentqe.security.finding_verifier import VerificationState
    
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    
    lifecycle_mgr = get_lifecycle_manager()
    
    new_verification_state = data.get("verification_state", "verified")
    verification_confidence = data.get("verification_confidence", 0.7)
    
    try:
        new_state = VerificationState(new_verification_state)
    except ValueError:
        return jsonify({"error": f"Invalid verification state: {new_verification_state}"}), 400
    
    verification_confidence = float(verification_confidence)
    if not 0 <= verification_confidence <= 1:
        return jsonify({"error": "verification_confidence must be between 0 and 1"}), 400
    
    success, msg = lifecycle_mgr.request_reverification(
        finding_id, int(get_jwt_identity()), 
        new_verification_state=new_state,
        verification_confidence=verification_confidence
    )
    
    if not success:
        return jsonify({"error": msg}), 400
    
    return jsonify({"success": True, "message": msg})


# ---- End Phase 5D: Finding Lifecycle Endpoints ----

# ---- End Phase 5D: Finding Lifecycle Endpoints ----

def review_autonomous_run(run_id):

    user_id = int(
        get_jwt_identity()
    )

    data = request.get_json() or {}

    decision = (
        data.get("decision", "")
        .strip()
        .upper()
    )

    feedback = (
        data.get("feedback", "")
        .strip()
    )

    if decision not in (
        "APPROVE",
        "REPLAN"
    ):
        return jsonify({
            "error":
                "Decision must be APPROVE or REPLAN"
        }), 400

    run = execute_query(
        """
        SELECT *
        FROM autonomous_runs
        WHERE id=? AND user_id=?
        """,
        (run_id, user_id),
        fetch=True
    )

    if not run:
        return jsonify({
            "error": "Run not found"
        }), 404

    execute_query(
        """
        UPDATE autonomous_runs
        SET human_decision=?,
            human_feedback=?
        WHERE id=?
        """,
        (
            decision,
            feedback,
            run_id
        )
    )

    return jsonify({
        "success": True,
        "decision": decision
    })
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5001))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
        reloader_type="stat",
        exclude_patterns=["*/site-packages/*"],
    )