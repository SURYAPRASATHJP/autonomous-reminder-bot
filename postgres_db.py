# you donot need to run this file more than once but it is safe to run it multiple times.

import os
from dotenv import load_dotenv
import psycopg2


load_dotenv()
DB_URL = os.getenv("DB_URL")

def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    return conn

# to test if the connection is successful
def test_connection():
    try: 
        conn = get_db_connection()
        conn.close()
        print("connection successful")
    except Exception as e:
        print(e)
        print("connection failed")

def create_tables():
    # main table for the reminders
    reminders_table = '''
    CREATE TABLE IF NOT EXISTS reminders (
        id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        user_request TEXT NOT NULL,
        remind_at TIMESTAMPTZ NOT NULL,
        next_run_at TIMESTAMPTZ NOT NULL,
        timezone TEXT NOT NULL,
        is_recurring BOOLEAN NOT NULL DEFAULT FALSE,
        recurring_type TEXT NOT NULL DEFAULT 'NA' CHECK (recurring_type IN ('NA', 'daily', 'weekly', 'monthly','days')),
        recurring_days TEXT,
        end_date TIMESTAMPTZ,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','cancelled')),
        last_sent TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (recurring_type <> 'days' OR recurring_days IS NOT NULL)
    );
    
        ALTER TABLE reminders ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0;
        ALTER TABLE reminders ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;

        ALTER TABLE reminders DROP CONSTRAINT IF EXISTS reminders_status_check;
        ALTER TABLE reminders ADD CONSTRAINT reminders_status_check CHECK (status IN ('pending', 'sent', 'cancelled', 'claimed', 'failed'));

        ALTER TABLE reminders DROP CONSTRAINT IF EXISTS reminders_lease_check;
        ALTER TABLE reminders ADD CONSTRAINT reminders_lease_check 
        CHECK ((status = 'claimed' AND locked_until IS NOT NULL) OR (status <> 'claimed' AND locked_until IS NULL));

'''
     
    notifications_table = '''
        CREATE TABLE IF NOT EXISTS notifications (
            id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            reminder_id INT NOT NULL REFERENCES reminders(id),
            user_id TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            seen_at TIMESTAMPTZ,
            UNIQUE (reminder_id)
        );
        '''
    # for the persistent connection to fetch pending reminders efficiently every time interval
    index_reminders = "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (user_id, status, next_run_at);"

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(reminders_table)
        cur.execute(notifications_table)
        cur.execute(index_reminders)
        conn.commit()
        cur.close()
        conn.close()
        print('tables created successfully')
    except Exception as e:
        print(e)
        print('tables creation failed')

def check_table_exists():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    print("Tables in database:", cur.fetchall())
    conn.close()

if __name__ == "__main__":
    test_connection()
    create_tables()
    check_table_exists()