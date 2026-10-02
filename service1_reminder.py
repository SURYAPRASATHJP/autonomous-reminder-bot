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

    if recurring_type == "days" and not recurring_days:

        return {"ok": False, "error": "recurring_days is required when recurring_type is days, for example mon,wed,thu"}

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

    except (Exception) as error:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()
    
def list_reminders(user_id):
    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        SELECT id, title, user_request, next_run_at, timezone, is_recurring, recurring_type, recurring_days, end_date, times_sent FROM reminders WHERE user_id= %s AND status= 'pending' ORDER BY next_run_at LIMIT 20
        '''

        cur.execute(query, (user_id,))

        rows= cur.fetchall()
        reminders= []
        for row in rows:
            reminder= {
                "id": row[0],
                "title": row[1],
                "user_request": row[2],
                "next_run": utc_to_local_str(row[3], row[4]),
                "is_recurring": row[5],
                "recurring_type": row[6],
                "recurring_days": row[7],
                "end_date": utc_to_local_str(row[8], row[4]),
                "times_sent": row[9]
            }
            reminders.append(reminder)

        return {"ok": True, "reminders": reminders}
    except (Exception) as error:
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()
    
def delete_reminder(user_id, reminder_id):
    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        DELETE FROM reminders WHERE user_id= %s AND id= %s AND status = 'pending' RETURNING id
        '''

        cur.execute(query, (user_id, reminder_id))

        deleted_reminder_id= cur.fetchone()

        conn.commit()

        if deleted_reminder_id:
            return {"ok": True, "message": f"Reminder {deleted_reminder_id} deleted sucessfully"}
        else:
            return {"ok": False, "error": f"No reminder found with the given id {reminder_id}"}

    except (Exception) as error:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(error)}
    
    finally:
        if conn:
            conn.close()

def update_reminder(user_id, reminder_id, title=None, remind_at=None, recurring_type=None, recurring_days=None, end_date=None, status=None):
    conn= None

    try:
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = %s")
            params.append(title)
            
        if remind_at is not None:
            try:
                remind_at_utc = local_str_to_utc(remind_at, TIME_ZONE)
                updates.append("remind_at = %s")
                params.append(remind_at_utc)
                updates.append("next_run_at = %s") 
                params.append(remind_at_utc)
            except Exception:
                return {"ok": False, "error": "remind_at is not a valid date and time."}
                
        if recurring_type is not None:
            updates.append("recurring_type = %s")
            params.append(recurring_type)
            updates.append("is_recurring = %s")
            params.append(recurring_type != "NA")
            if recurring_type != 'days':
                updates.append("recurring_days = NULL")
                recurring_days = None
            
        if recurring_days is not None:
            updates.append("recurring_days = %s")
            params.append(recurring_days)
            
        if end_date is not None:
            try:
                end_date_utc = local_str_to_utc(end_date, TIME_ZONE)
                updates.append("end_date = %s")
                params.append(end_date_utc)
            except Exception:
                return {"ok": False, "error": "end_date is not a valid date and time."}
                
        if status is not None:
            updates.append("status = %s")
            params.append(status)
            
        if not updates:
            return {"ok": False, "error": "No fields provided to update."}
            
        updates.append("updated_at = NOW()")
        
        query = f"UPDATE reminders SET {', '.join(updates)} WHERE id = %s AND status = 'pending' AND user_id = %s RETURNING id"
        params.extend([reminder_id, user_id])
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        
        updated_row = cur.fetchone()
        conn.commit()
        
        if updated_row:
            return {"ok": True, "message": f"Reminder {reminder_id} updated successfully."}
        else:
            return {"ok": False, "error": f"no pending reminders with id {reminder_id}"}
            
    except Exception as error:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()


def get_unseen_notifications(user_id):
    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        SELECT id, message, created_at FROM notifications WHERE user_id= %s AND seen_at IS NULL ORDER BY created_at LIMIT 20
        '''

        cur.execute(query, (user_id,))

        rows= cur.fetchall()
        notifications= [{"id": row[0], "message": row[1], "created_at": row[2]} for row in rows]

        return {"ok": True, "notifications": notifications}
    except (Exception) as error:
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()


def mark_notifications_seen(notification_ids):
    conn= None

    try:
        conn= get_db_connection()
        cur= conn.cursor()

        query= '''
        UPDATE notifications SET seen_at = NOW() WHERE id = ANY(%s) AND seen_at IS NULL
        '''

        cur.execute(query, (notification_ids,))
        conn.commit()

        return {"ok": True}
    except (Exception) as error:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(error)}
    finally:
        if conn:
            conn.close()
