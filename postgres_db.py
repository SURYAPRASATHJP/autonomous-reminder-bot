# never run this file more than once as this not idempotent
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
DB_URL = os.getenv("DB_URL")

def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    return conn

def test_connection():
    try: 
        conn = get_db_connection()
        conn.close()
        print("connection successful")
    except Exception as e:
        print(e)
        print("connection failed")

if __name__ == "__main__":
    test_connection()