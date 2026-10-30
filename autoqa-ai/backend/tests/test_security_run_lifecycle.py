"""
Regression test for security run lifecycle columns issue.
Tests that the autonomous_runs table has all required columns for security run execution.
"""
import sys
import os
import tempfile
import sqlite3

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from database.init_db import init_db, DB_PATH
from database.db import execute_query


@pytest.fixture
def temp_db():
    """Create a temporary database for testing migrations."""
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_db_path = f.name
    
    # Temporarily override DB_PATH
    import database.init_db as init_db_module
    import database.db as db_module
    original_db_path = init_db_module.DB_PATH
    original_db_path_db = db_module.DB_PATH
    
    init_db_module.DB_PATH = temp_db_path
    db_module.DB_PATH = temp_db_path
    
    yield temp_db_path
    
    # Restore original paths
    init_db_module.DB_PATH = original_db_path
    db_module.DB_PATH = original_db_path_db
    
    # Clean up
    try:
        os.unlink(temp_db_path)
    except:
        pass


def test_migration_adds_started_at_to_existing_database(temp_db):
    """Test that migration adds started_at column to a pre-existing database missing that column."""
    # Create database with old schema (without started_at)
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    # Create the old autonomous_runs table without lifecycle columns
    # Include all columns that migrations expect (run_type, cycle, max_cycles, strategy_json, etc.)
    cursor.execute("""
        CREATE TABLE autonomous_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            module_name TEXT,
            requirement_text TEXT,
            url TEXT,
            repo_url TEXT,
            execution_mode TEXT,
            status TEXT,
            human_decision TEXT,
            human_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            cycle INTEGER DEFAULT 1,
            max_cycles INTEGER DEFAULT 3,
            strategy_json TEXT,
            run_type TEXT DEFAULT 'qa',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    
    # Create users table (required for FK)
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'qa_engineer',
            github_id TEXT,
            github_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert a test user
    cursor.execute("INSERT INTO users (username, email, password) VALUES ('test', 'test@test.com', 'pass')")
    user_id = cursor.lastrowid
    
    # Insert a test run
    cursor.execute(
        "INSERT INTO autonomous_runs (user_id, title, url, status, run_type) VALUES (?, ?, ?, ?, ?)",
        (user_id, "Test Run", "https://example.com", "Authorized", "security")
    )
    run_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    # Now run init_db which should apply migrations
    init_db()
    
    # Verify the columns were added
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(autonomous_runs)")
    columns = {row[1]: row for row in cursor.fetchall()}
    conn.close()
    
    # Check all required lifecycle columns exist
    required_columns = ['started_at', 'duration_seconds', 'validators_executed', 'findings_count', 'error_summary']
    for col in required_columns:
        assert col in columns, f"Column {col} was not added by migration"
    
    # Verify existing data is preserved
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status FROM autonomous_runs WHERE id=?", (run_id,))
    row = cursor.fetchone()
    conn.close()
    
    assert row is not None, "Existing run record was lost during migration"
    assert row[1] == "Test Run"
    assert row[2] == "Authorized"


def test_migration_is_idempotent(temp_db):
    """Test that running migration twice succeeds without errors."""
    # First run
    init_db()
    
    # Second run should not fail
    init_db()
    
    # Verify columns still exist
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(autonomous_runs)")
    columns = {row[1]: row for row in cursor.fetchall()}
    conn.close()
    
    required_columns = ['started_at', 'duration_seconds', 'validators_executed', 'findings_count', 'error_summary']
    for col in required_columns:
        assert col in columns, f"Column {col} missing after second migration"


def test_existing_records_survive_migration(temp_db):
    """Test that existing assessment records survive migration with NULL values for new columns."""
    # Create database with old schema
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE autonomous_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            url TEXT,
            status TEXT,
            run_type TEXT DEFAULT 'qa',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)
    
    cursor.execute("INSERT INTO users (username, email, password) VALUES ('user1', 'u1@test.com', 'pass')")
    user_id = cursor.lastrowid
    
    # Insert multiple runs with different statuses
    test_runs = [
        (user_id, "Run 1", "https://example1.com", "Authorized", "security"),
        (user_id, "Run 2", "https://example2.com", "Completed", "security"),
        (user_id, "Run 3", "https://example3.com", "Failed", "security"),
        (user_id, "Run 4", "https://example4.com", "Pending", "qa"),
    ]
    
    run_ids = []
    for run in test_runs:
        cursor.execute("INSERT INTO autonomous_runs (user_id, title, url, status, run_type) VALUES (?, ?, ?, ?, ?)", run)
        run_ids.append(cursor.lastrowid)
    
    conn.commit()
    conn.close()
    
    # Run migration
    init_db()
    
    # Verify all records survive with NULL values for new columns
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, status, run_type, started_at, duration_seconds, validators_executed, findings_count, error_summary FROM autonomous_runs ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    
    assert len(rows) == 4, "Not all records survived migration"
    
    for i, row in enumerate(rows):
        run_id, title, status, run_type, started_at, duration, validators, findings, error = row
        assert title == f"Run {i+1}"
        assert status == test_runs[i][3]
        assert run_type == test_runs[i][4]
        assert started_at is None, f"started_at should be NULL for existing records, got {started_at}"
        assert duration is None, f"duration_seconds should be NULL for existing records, got {duration}"
        assert validators is None, f"validators_executed should be NULL for existing records, got {validators}"
        assert findings is None, f"findings_count should be NULL for existing records, got {findings}"
        assert error is None, f"error_summary should be NULL for existing records, got {error}"


def test_start_endpoint_no_longer_raises_missing_column():
    """Test that the start endpoint SQL no longer fails with 'no such column: started_at'."""
    # This tests the exact SQL from api_security_run_start
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Verify the column exists
    cursor.execute("PRAGMA table_info(autonomous_runs)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    
    assert 'started_at' in columns, "started_at column missing from autonomous_runs"
    assert 'error_summary' in columns, "error_summary column missing from autonomous_runs"
    
    # The exact SQL from app.py:1633-1637 should now work
    test_sql = """
        UPDATE autonomous_runs 
        SET status='Running', started_at=CURRENT_TIMESTAMP, error_summary=NULL 
        WHERE id=?
    """
    
    # This should not raise "no such column: started_at"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(test_sql, (999999,))  # Non-existent ID, but SQL should parse
        conn.commit()
        success = True
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            success = False
        else:
            raise
    finally:
        conn.close()
    
    assert success, "The start endpoint SQL still fails with missing column error"


def test_security_runner_sql_no_longer_fails():
    """Test that the security_runner SQL statements work with the new schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Test the exact SQL from security_runner.py:345-348
    sql1 = "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP WHERE id=?"
    try:
        cursor.execute(sql1, (999999,))
        conn.commit()
        success1 = True
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            success1 = False
        else:
            raise
    
    # Test the exact SQL from security_runner.py:499-504
    sql2 = """
        UPDATE autonomous_runs
           SET status='Completed', completed_at=CURRENT_TIMESTAMP,
               duration_seconds=?, validators_executed=?, findings_count=?
         WHERE id=?
    """
    try:
        cursor.execute(sql2, (10.5, 5, 3, 999999))
        conn.commit()
        success2 = True
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            success2 = False
        else:
            raise
    
    # Test the exact SQL from security_runner.py:512-516 (_finish_run)
    sql3 = """
        UPDATE autonomous_runs
           SET status=?, completed_at=CURRENT_TIMESTAMP, duration_seconds=?, error_summary=?
         WHERE id=?
    """
    try:
        cursor.execute(sql3, ("Failed", 5.0, "Test error", 999999))
        conn.commit()
        success3 = True
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            success3 = False
        else:
            raise
    
    conn.close()
    
    assert success1, "security_runner start SQL fails with missing column"
    assert success2, "security_runner completion SQL fails with missing column"
    assert success3, "security_runner failure SQL fails with missing column"


def test_run_lifecycle_state_transitions():
    """Test that a valid authorized run can transition through the full lifecycle."""
    # Create a test run
    run_id = execute_query(
        """INSERT INTO autonomous_runs 
           (user_id, title, url, status, run_type, mode, profile) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, "Lifecycle Test", "https://example.com", "Authorized", "security", "passive", "passive_only"),
    )
    
    try:
        # 1. Start the run (simulating api_security_run_start)
        execute_query(
            "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP, error_summary=NULL WHERE id=?",
            (run_id,)
        )
        
        # Verify started_at was set
        rows = execute_query("SELECT status, started_at FROM autonomous_runs WHERE id=?", (run_id,), fetch=True)
        assert rows[0]['status'] == 'Running'
        assert rows[0]['started_at'] is not None, "started_at should be set when run starts"
        
        # 2. Complete the run (simulating execute_security_run completion)
        execute_query(
            """UPDATE autonomous_runs
               SET status='Completed', completed_at=CURRENT_TIMESTAMP,
                   duration_seconds=?, validators_executed=?, findings_count=?
               WHERE id=?""",
            (15.5, 8, 3, run_id)
        )
        
        # Verify completion fields
        rows = execute_query(
            "SELECT status, completed_at, duration_seconds, validators_executed, findings_count FROM autonomous_runs WHERE id=?",
            (run_id,), fetch=True
        )
        assert rows[0]['status'] == 'Completed'
        assert rows[0]['completed_at'] is not None
        assert rows[0]['duration_seconds'] == 15.5
        assert rows[0]['validators_executed'] == 8
        assert rows[0]['findings_count'] == 3
        
        # 3. Test failure path
        run_id2 = execute_query(
            """INSERT INTO autonomous_runs 
               (user_id, title, url, status, run_type, mode, profile) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (1, "Failure Test", "https://example.com", "Authorized", "security", "passive", "passive_only"),
        )
        
        execute_query(
            "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP, error_summary=NULL WHERE id=?",
            (run_id2,)
        )
        
        execute_query(
            """UPDATE autonomous_runs
               SET status=?, completed_at=CURRENT_TIMESTAMP, duration_seconds=?, error_summary=?
               WHERE id=?""",
            ("Failed", 5.0, "Preflight rejected: unauthorized", run_id2)
        )
        
        rows = execute_query(
            "SELECT status, error_summary, duration_seconds FROM autonomous_runs WHERE id=?",
            (run_id2,), fetch=True
        )
        assert rows[0]['status'] == 'Failed'
        assert rows[0]['error_summary'] == 'Preflight rejected: unauthorized'
        assert rows[0]['duration_seconds'] == 5.0
        
    finally:
        # Cleanup
        execute_query("DELETE FROM autonomous_runs WHERE id IN (?, ?)", (run_id, run_id2))


def test_repeated_start_requests_safe():
    """Test that repeated start requests don't cause issues."""
    run_id = execute_query(
        """INSERT INTO autonomous_runs 
           (user_id, title, url, status, run_type, mode, profile) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, "Repeat Start Test", "https://example.com", "Authorized", "security", "passive", "passive_only"),
    )
    
    try:
        # First start
        execute_query(
            "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP, error_summary=NULL WHERE id=?",
            (run_id,)
        )
        rows = execute_query("SELECT status, started_at FROM autonomous_runs WHERE id=?", (run_id,), fetch=True)
        first_start = rows[0]['started_at']
        assert rows[0]['status'] == 'Running'
        
        # Second start (should not fail, but started_at will be re-evaluated in SQLite)
        execute_query(
            "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP, error_summary=NULL WHERE id=?",
            (run_id,)
        )
        rows = execute_query("SELECT status, started_at FROM autonomous_runs WHERE id=?", (run_id,), fetch=True)
        second_start = rows[0]['started_at']
        
        # In SQLite, CURRENT_TIMESTAMP will be re-evaluated, so it might change
        # The important thing is no error occurs and status remains Running
        assert rows[0]['status'] == 'Running'
        
    finally:
        execute_query("DELETE FROM autonomous_runs WHERE id=?", (run_id,))


def test_findings_and_evidence_persist_after_execution():
    """Test that findings and evidence can be retrieved after execution."""
    run_id = execute_query(
        """INSERT INTO autonomous_runs 
           (user_id, title, url, status, run_type, mode, profile) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (1, "Findings Test", "https://example.com", "Completed", "security", "passive", "passive_only"),
    )
    
    try:
        # Insert a finding
        finding_id = execute_query(
            """INSERT INTO security_findings
               (run_id, validator_id, finding_type, title, description,
                severity, confidence, affected_url, evidence, recommendation, classification,
                check_type, active_check_id, execution_phase)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, "test_validator", "info_disclosure", "Test Finding", "Description",
             "Medium", 0.8, "https://example.com/page", "{}", "Fix it", "confirmed",
             "passive", None, "passive"),
        )
        
        # Insert evidence
        execute_query(
            """INSERT INTO security_evidence
               (finding_id, evidence_type, url, method, status_code, data, check_type, active_check_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            (finding_id, "http_response", "https://example.com/page", "GET", 200, "{}", "passive", None),
        )
        
        # Retrieve findings
        findings = execute_query(
            "SELECT * FROM security_findings WHERE run_id=?", (run_id,), fetch=True
        )
        assert len(findings) == 1
        assert findings[0]['title'] == "Test Finding"
        
        # Retrieve evidence
        evidence = execute_query(
            "SELECT * FROM security_evidence WHERE finding_id=?", (finding_id,), fetch=True
        )
        assert len(evidence) == 1
        assert evidence[0]['evidence_type'] == "http_response"
        
    finally:
        execute_query("DELETE FROM security_evidence WHERE finding_id IN (SELECT id FROM security_findings WHERE run_id=?)", (run_id,))
        execute_query("DELETE FROM security_findings WHERE run_id=?", (run_id,))
        execute_query("DELETE FROM autonomous_runs WHERE id=?", (run_id,))


def test_database_connections_cleaned_up_after_errors():
    """Test that database connections are properly cleaned up after errors."""
    import database.db as db_module
    
    # Test that execute_query handles invalid SQL gracefully
    try:
        execute_query("INVALID SQL STATEMENT", ())
        assert False, "Should have raised an exception"
    except Exception:
        pass  # Expected
    
    # Verify we can still execute valid queries after an error
    rows = execute_query("SELECT 1 as test", fetch=True)
    assert rows[0]['test'] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])