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
            cursor.execute(
                "ALTER TABLE autonomous_runs ADD COLUMN repo_url TEXT"
            )
            print("Added repo_url to autonomous_runs")
        except sqlite3.OperationalError:
            print("repo_url already exists in autonomous_runs")

        # 2. Add human-review and cycle-management fields
        new_columns = [
            ("human_decision", "TEXT"),
            ("human_feedback", "TEXT"),
            ("cycle", "INTEGER DEFAULT 1"),
            ("max_cycles", "INTEGER DEFAULT 3"),
            ("strategy_json", "TEXT"),
        ]

        for column_name, column_definition in new_columns:
            try:
                cursor.execute(
                    f"ALTER TABLE autonomous_runs "
                    f"ADD COLUMN {column_name} {column_definition}"
                )
                print(f"Added {column_name} to autonomous_runs")
            except sqlite3.OperationalError:
                print(f"{column_name} already exists in autonomous_runs")

        # 3. Create autonomous_repo_intelligence table
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
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()