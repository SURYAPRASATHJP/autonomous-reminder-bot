import os
from dotenv import load_dotenv
from postgres_db import get_db_connection
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()
TIME_ZONE = os.getenv('TIME_ZONE')

def local_str_to_utc(text, time_zone):
    if not text:
        return None

    dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(time_zone))

    return dt.astimezone(ZoneInfo("UTC"))

def utc_to_local_str(UTC_time, time_zone):
    if not UTC_time:
        return None
    return UTC_time.astimezone(ZoneInfo(time_zone)).strftime("%a %d %b %Y, %I:%M %p")


def create_reminder(user_id, user_request, title, remind_at, recurring_type="NA", recurring_days=None, end_date=None):
    try:
        remind_at_in_utc = local_str_to_utc(remind_at, TIME_ZONE)

    except Exception:
        return {"ok": False, "error": "remind_at is not a valid date and time call this tool again"}
    end_date_in_utc = None
    if end_date:
        try:
            end_date_in_utc = local_str_to_utc(end_date, TIME_ZONE)

        except Exception:
            return {"ok": False, "error": "end_date is not a valid date and time"}

    is_recurring = recurring_type != "NA"

    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        INSERT INTO reminders(user_id, title, user_request, remind_at, next_run_at, timezone, is_recurring, recurring_type, recurring_days, end_date
        )VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        '''

        cur.execute(query, (user_id, title, user_request, remind_at_in_utc, remind_at_in_utc, TIME_ZONE, is_recurring, recurring_type, recurring_days, end_date_in_utc))

        reminder_id= cur.fetchone()[0]
        conn.commit()
        return {"ok": True, "reminder_id": reminder_id, "first_run": utc_to_local_str(remind_at_in_utc, TIME_ZONE)}

    # conn= None skips as there was no connection in the first place
    except (Exception) as error:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(error)}
    # conn= None skips as there was no connection in the first place again lol
    finally:
        if conn:
            conn.close()
    
def list_reminders(user_id):
    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        SELECT id, title, user_request, remind_at, timezone, is_recurring, recurring_type, recurring_days, end_date FROM reminders WHERE user_id= %s
        '''

        cur.execute(query, (user_id,))

        rows= cur.fetchall()
        reminders= []
        for row in rows:
            reminder= {
                "id": row[0],
                "title": row[1],
                "user_request": row[2],
                "remind_at": utc_to_local_str(row[3], row[4]),
                "is_recurring": row[5],
                "recurring_type": row[6],
                "recurring_days": row[7],
                "end_date": utc_to_local_str(row[8], row[4])
            }
            reminders.append(reminder)

        return {"ok": True, "reminders": reminders}
    except (Exception) as error:
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()