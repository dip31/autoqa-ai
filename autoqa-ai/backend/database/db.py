import sqlite3
import mysql.connector
import os
import re
from datetime import datetime

# Local SQLite fallback
DB_PATH = os.path.join(os.path.dirname(__file__), "autoqa.db")

def get_connection():
    # Check if we should use MySQL (GCP / Production)
    db_host = os.getenv("DB_HOST")
    if db_host and db_host != "localhost":
        # MySQL / Cloud SQL connection
        return mysql.connector.connect(
            host=db_host,
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            # Cloud SQL often uses unix_socket in Cloud Run, but we'll stick to TCP/IP or SSL
            # depending on the instance setup.
            get_warnings=True,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci'
        )
    
    # SQLite connects to a file
    conn = sqlite3.connect(DB_PATH)
    # Enable dictionary-like access
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(query, params=None, fetch=False):
    db_host = os.getenv("DB_HOST")
    is_mysql = db_host and db_host != "localhost"
    
    conn = get_connection()
    # For MySQL, we use dictionary=True if available or manual conversion
    cursor = conn.cursor(dictionary=True) if is_mysql else conn.cursor()
    
    try:
        # SQLite uses '?' as placeholder, MySQL as '%s'
        if is_mysql:
            query = query.replace('?', '%s')
            # sqlite AUTOINCREMENT -> mysql AUTO_INCREMENT is likely handled in schema
        
        cursor.execute(query, params or ())
        
        if fetch:
            rows = cursor.fetchall()
            # If SQLite, convert row to dict. If MySQL (dictionary=True already), just return
            result = rows if is_mysql else [dict(row) for row in rows]
            cursor.close()
            conn.close()
            return result
        
        conn.commit()
        last_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return last_id
    except Exception as e:
        if conn: conn.close()
        raise e
