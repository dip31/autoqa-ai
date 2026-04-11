import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "autoqa.db")

def init_db():
    print(f"Initializing SQLite database at {DB_PATH}...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Schema for SQLite
        # Note: AUTO_INCREMENT -> AUTOINCREMENT (requires INTEGER PRIMARY KEY)
        # Note: %s -> ? (but we are executing raw SQL here)
        queries = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                user_id INTEGER,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                testcase TEXT NOT NULL,
                review_result TEXT,
                score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS code_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code TEXT NOT NULL,
                language TEXT,
                result TEXT,
                score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS website_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT NOT NULL,
                result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                report_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                module_name TEXT,
                requirement_text TEXT,
                url TEXT,
                execution_mode TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_scope (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                feature_summary TEXT,
                scope_items TEXT,
                assumptions TEXT,
                priority_plan TEXT,
                estimated_coverage REAL,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                case_id TEXT,
                scenario TEXT,
                case_type TEXT,
                expected_result TEXT,
                priority TEXT,
                generated_by TEXT,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                action_type TEXT,
                action_detail TEXT,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                title TEXT,
                description TEXT,
                severity TEXT,
                probable_cause TEXT,
                page_reference TEXT,
                screenshot_path TEXT,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_risk_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                module_risk_score REAL,
                release_readiness TEXT,
                confidence_score REAL,
                high_risk_areas TEXT,
                recommendations TEXT,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                executive_summary TEXT,
                final_verdict TEXT,
                report_json TEXT,
                exported_pdf_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS autonomous_healing_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                test_case_id TEXT,
                step_detail TEXT,
                original_selector TEXT,
                suggested_selector TEXT,
                failure_reason TEXT,
                confidence_score REAL,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
            )
            """,
            # ── Developer Portal tables ───────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS dev_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                requirements_text TEXT,
                tech_stack TEXT,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dev_diagrams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                user_id INTEGER NOT NULL,
                diagram_type TEXT NOT NULL,
                title TEXT,
                mermaid_code TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES dev_projects(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dev_code (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                user_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                title TEXT,
                code_content TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES dev_projects(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS platform_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                project_id INTEGER,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS message_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES platform_messages(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS github_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                repo_url TEXT,
                analysis_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        ]

        for query in queries:
            cursor.execute(query)

        conn.commit()
        cursor.close()
        conn.close()
        print("SQLite database initialized successfully!")

        # ── Additive Migrations (safe to re-run, silent on duplicates) ──────
        conn2 = sqlite3.connect(DB_PATH)
        cur2 = conn2.cursor()
        migrations = [
            # Autonomous QA columns
            "ALTER TABLE autonomous_test_cases ADD COLUMN title TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN objective TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN module_name TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN preconditions TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN input_data TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN steps TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN category TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN tags TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN automatable INTEGER DEFAULT 1",
            "ALTER TABLE autonomous_test_cases ADD COLUMN blocked_reason TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN status TEXT DEFAULT 'Pending'",
            "ALTER TABLE autonomous_test_cases ADD COLUMN action TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN selector TEXT",
            "ALTER TABLE autonomous_test_cases ADD COLUMN action_value TEXT",
            "ALTER TABLE autonomous_execution_logs ADD COLUMN test_case_id TEXT",
            "ALTER TABLE autonomous_execution_logs ADD COLUMN step_number INTEGER",
            "ALTER TABLE autonomous_execution_logs ADD COLUMN current_url TEXT",
            # Developer Portal: role on users
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'qa_engineer'",
            # Developer Portal: new tables (CREATE IF NOT EXISTS — safe)
            """CREATE TABLE IF NOT EXISTS dev_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                requirements_text TEXT,
                tech_stack TEXT,
                status TEXT DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS dev_diagrams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                user_id INTEGER NOT NULL,
                diagram_type TEXT NOT NULL,
                title TEXT,
                mermaid_code TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES dev_projects(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS dev_code (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                user_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                title TEXT,
                code_content TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES dev_projects(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS platform_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                project_id INTEGER,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS message_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES platform_messages(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
        ]
        for m in migrations:
            try:
                cur2.execute(m)
            except Exception:
                pass  # Column/table already exists
        conn2.commit()
        cur2.close()
        conn2.close()
        print("Migrations applied successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_db()
