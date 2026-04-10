import mysql.connector
import os
from dotenv import load_dotenv

def get_connection():
    load_dotenv(override=True)  # always reload so password changes take effect
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "autoqa_db")
    )

def execute_query(query, params=None, fetch=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params or ())
    if fetch:
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result
    conn.commit()
    last_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return last_id
