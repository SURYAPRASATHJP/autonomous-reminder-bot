import argparse
import logging
import threading
import time

from postgres_db import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")
logger = logging.getLogger("poller")


BATCH_SIZE = 10
LEASE_SECONDS = 600
MAX_ATTEMPTS = 3
IDLE_SLEEP = 0.5
ERROR_SLEEP = 1.0


def claim_batch(conn, n, lease_seconds):
    # lock the row for the worker to send
    with conn.cursor() as cur:
        query = """
            UPDATE reminders
            SET status = 'claimed',
                locked_until = NOW() + (%s * INTERVAL '1 second'),
                attempts = attempts + 1,
                updated_at = NOW()
            WHERE id IN (
                SELECT id FROM reminders
                WHERE status = 'pending'
                  AND next_run_at <= NOW()
                  AND is_recurring = FALSE
                ORDER BY next_run_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, title, user_request, attempts, user_id;
        """
        cur.execute(query, (lease_seconds, n))
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        batch = [dict(zip(columns, row)) for row in rows]

   
    conn.commit()
    return batch


def deliver(conn, row):
    # deliver to the notification table
    with conn.cursor() as cur:
        query = """
            INSERT INTO notifications (reminder_id, user_id, message)
            VALUES (%s, %s, %s)
            ON CONFLICT (reminder_id) DO NOTHING
        """
        cur.execute(query, (row["id"], row["user_id"], row["title"]))
    conn.commit()


def mark_sent(conn, row_id):
    # mark the reminder as sent
    with conn.cursor() as cur:

        query = """ 
          UPDATE reminders
            SET status = 'sent',
                last_sent = NOW(),
                locked_until = NULL,
                updated_at = NOW()
            WHERE id = %s AND status = 'claimed'
        """
        cur.execute(query, (row_id,))
        changed = cur.rowcount > 0
    conn.commit()
    return changed


def release_or_fail(conn, row_id):
    # set as failed if max attempts or back to pending if less.
    with conn.cursor() as cur:
        query = """
            UPDATE reminders
            SET status = CASE WHEN attempts >= %s THEN 'failed' ELSE 'pending' END,
                locked_until = NULL,
                updated_at = NOW()
            WHERE id = %s AND status = 'claimed'
        """
        cur.execute(query, (MAX_ATTEMPTS, row_id))
    conn.commit()


def release_unprocessed(conn, row_id):

    with conn.cursor() as cur:
        query = """
            UPDATE reminders
            SET status = 'pending',
                locked_until = NULL,
                attempts = GREATEST(attempts - 1, 0),
                updated_at = NOW()
            WHERE id = %s AND status = 'claimed'
        """

        cur.execute(query, (row_id,))

    conn.commit()


def process_row(conn, row, deliver_fn):
    
    # delivery process. Only a failed delivery releases the row.
    try:
        deliver_fn(conn, row)
    except Exception as e:
        conn.rollback()  # the failed statement left the transaction aborted and lock release
        logger.error(f"failed to deliver reminder {row['id']}: {e}")
        try:
            release_or_fail(conn, row["id"])
        except Exception as db_err:
            conn.rollback()
            logger.error(f"DB errored while releasing reminder {row['id']} after failed delivery: {db_err}")
        return

    # mark it sent and this fails the message was already delivered, 
    # so leave the row claimed (do not release it, that would send it again after the lease expires so a another worker takes it and delivers it again).
    try:
        if not mark_sent(conn, row["id"]):
            logger.warning(f"reminder {row['id']} delivered but could not be marked sent (no longer claimed).")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error while marking reminder {row['id']} sent: {e}. Row left claimed.")


def worker(worker_id, deliver_fn, stop_event):
    #one connection persistant
    conn = None
    try:
        conn = get_db_connection()
        logger.info(f"worker {worker_id} started.")

        while not stop_event.is_set():
            try:
                batch = claim_batch(conn, n=BATCH_SIZE, lease_seconds=LEASE_SECONDS)

                if not batch:
                    time.sleep(IDLE_SLEEP)
                    continue

                for i, row in enumerate(batch):
                    if stop_event.is_set():
                        logger.info(f"Worker {worker_id} stopping and releasing {len(batch) - i} unprocessed rows.")
                        for unproc_row in batch[i:]:
                            try:
                                release_unprocessed(conn, unproc_row["id"])
                            except Exception as e:
                                conn.rollback()
                                logger.error(f"failed to release row {unproc_row['id']} on shutdown: {e}")
                        break

                    process_row(conn, row, deliver_fn)

            except Exception as e:
                logger.error(f"worker {worker_id} had a loop error: {e}")
                if conn:
                    conn.rollback()
                time.sleep(ERROR_SLEEP)

    except Exception as e:
        logger.error(f"worker {worker_id} got a fatal error: {e}")
    finally:
        if conn:
            conn.close()
        logger.info(f"worker {worker_id} got shut down.")


def run(workers=3, deliver_fn=None):
    # start the worker threads
    if deliver_fn is None:
        deliver_fn = deliver

    stop_event = threading.Event()
    threads = []
    for i in range(workers):
        t = threading.Thread(target=worker, args=(i + 1, deliver_fn, stop_event), name=f"Worker-{i + 1}")
        t.start()
        threads.append(t)
    return threads, stop_event


def main():
    ap = argparse.ArgumentParser(description="Reminder poller: claims due reminders and delivers them to the UI.")
    ap.add_argument("--workers", type=int, default=3, help="number of worker threads (default 3)")
    args = ap.parse_args()

    threads, stop_event = run(workers=args.workers)
    logger.info(f"Poller running with {args.workers} workers. Press Ctrl+C to stop.")

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping workers...")
        stop_event.set()

    for t in threads:
        t.join()
    logger.info("All workers stopped.")


if __name__ == "__main__":
    main()
