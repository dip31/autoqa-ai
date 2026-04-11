import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "autoqa.db")

def migrate():
    print(f"Migrating database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. Add repo_url to autonomous_runs
        try:
            cursor.execute("ALTER TABLE autonomous_runs ADD COLUMN repo_url TEXT")
            print("Added repo_url to autonomous_runs")
        except sqlite3.OperationalError:
            print("repo_url already exists in autonomous_runs")
            
        # 2. Create autonomous_repo_intelligence table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_repo_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            analysis_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES autonomous_runs(id) ON DELETE CASCADE
        )
        """)
        print("Created autonomous_repo_intelligence table")
        
        conn.commit()
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
