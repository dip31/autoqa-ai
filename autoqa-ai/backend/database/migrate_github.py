import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "autoqa.db")

def migrate():
    print(f"Migrating database at {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Add columns to users if they don't exist
        # SQLite doesn't support IF NOT EXISTS for columns, so we check first
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "github_id" not in columns:
            print("Adding github_id to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN github_id TEXT")
            
        if "github_token" not in columns:
            print("Adding github_token to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN github_token TEXT")
            
        # Create github_analyses table
        print("Creating github_analyses table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS github_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            repo_url TEXT NOT NULL,
            analysis_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """)
        
        conn.commit()
        print("Migration completed successfully!")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
