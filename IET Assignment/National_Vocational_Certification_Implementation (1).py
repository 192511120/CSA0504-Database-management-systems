import sqlite3
import random
import json
import time
import threading
from datetime import date, timedelta
from pathlib import Path

# ============================================================
# National Vocational Certification and Exam Slot-Booking System
# Integrated implementation:
# File Organization, Indexing, Hashing, Query Optimization,
# Transaction Management, and Concurrency Control
# ============================================================

BASE = Path(__file__).resolve().parent
DB = BASE / "exam_system.db"
N = 10007

# ------------------------------------------------------------
# 1. DATABASE CREATION
# ------------------------------------------------------------

SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS Result;
DROP TABLE IF EXISTS Booking;
DROP TABLE IF EXISTS Slot;
DROP TABLE IF EXISTS ExamAttempt;
DROP TABLE IF EXISTS Candidate;
DROP TABLE IF EXISTS Center;

CREATE TABLE Candidate (
    candidate_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT
);

CREATE TABLE Center (
    center_id INTEGER PRIMARY KEY,
    center_name TEXT NOT NULL,
    city TEXT NOT NULL,
    total_seats INTEGER NOT NULL
);

CREATE TABLE ExamAttempt (
    attempt_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    center_id INTEGER NOT NULL,
    exam_date TEXT NOT NULL,
    slot_time TEXT NOT NULL,
    responses_json TEXT,
    time_taken_sec INTEGER,
    raw_score REAL,
    PRIMARY KEY (center_id, exam_date, attempt_id),
    FOREIGN KEY (candidate_id) REFERENCES Candidate(candidate_id),
    FOREIGN KEY (center_id) REFERENCES Center(center_id)
) WITHOUT ROWID;

CREATE INDEX idx_attempt_candidate
ON ExamAttempt(candidate_id);

CREATE INDEX idx_attempt_date
ON ExamAttempt(exam_date);

CREATE TABLE Slot (
    slot_id INTEGER PRIMARY KEY,
    center_id INTEGER NOT NULL,
    exam_date TEXT NOT NULL,
    slot_time TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    booked_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (center_id, exam_date, slot_time),
    CHECK (booked_count >= 0 AND booked_count <= capacity),
    FOREIGN KEY (center_id) REFERENCES Center(center_id)
);

CREATE INDEX idx_slot_center_date
ON Slot(center_id, exam_date);

CREATE TABLE Booking (
    booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    booking_time TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL CHECK (status IN ('CONFIRMED','CANCELLED')),
    UNIQUE (candidate_id, slot_id),
    FOREIGN KEY (candidate_id) REFERENCES Candidate(candidate_id),
    FOREIGN KEY (slot_id) REFERENCES Slot(slot_id)
);

CREATE INDEX idx_booking_slot
ON Booking(slot_id);

CREATE TABLE Result (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    center_id INTEGER NOT NULL,
    exam_date TEXT NOT NULL,
    final_score REAL NOT NULL,
    grade TEXT,
    published_by TEXT NOT NULL,
    published_on TEXT NOT NULL DEFAULT (datetime('now')),
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (candidate_id) REFERENCES Candidate(candidate_id)
);

CREATE INDEX idx_result_candidate
ON Result(candidate_id);
"""

def create_and_seed_database():
    random.seed(42)

    if DB.exists():
        DB.unlink()

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)

    # 20 centers
    for center_id in range(1, 21):
        con.execute(
            """INSERT INTO Center(center_id, center_name, city, total_seats)
               VALUES (?, ?, ?, ?)""",
            (center_id, f"Vocational Center {center_id}", f"City-{center_id}", 150)
        )

    # 5000 candidates
    for candidate_id in range(1, 5001):
        con.execute(
            """INSERT INTO Candidate(candidate_id, full_name, email, phone)
               VALUES (?, ?, ?, ?)""",
            (
                candidate_id,
                f"Candidate {candidate_id}",
                f"candidate{candidate_id}@example.com",
                str(9000000000 + candidate_id)
            )
        )

    # 720 slots = 20 centers x 12 dates x 3 slots
    slot_id = 1
    start = date(2026, 9, 1)

    for center_id in range(1, 21):
        for d in range(12):
            exam_date = (start + timedelta(days=d)).isoformat()

            for slot_time in ("09:00", "13:00", "16:00"):
                con.execute(
                    """INSERT INTO Slot
                       (slot_id, center_id, exam_date, slot_time, capacity)
                       VALUES (?, ?, ?, ?, ?)""",
                    (slot_id, center_id, exam_date, slot_time, 50)
                )
                slot_id += 1

    # 50,000 attempts
    for attempt_id in range(1, 50001):
        center_id = random.randint(1, 20)
        exam_date = (start + timedelta(days=random.randint(0, 11))).isoformat()
        slot_time = random.choice(("09:00", "13:00", "16:00"))
        candidate_id = random.randint(1, 5000)

        responses = json.dumps({
            "q1": random.choice(["A","B","C","D"]),
            "q2": random.choice(["A","B","C","D"]),
            "q3": random.choice(["A","B","C","D"])
        })

        con.execute(
            """INSERT INTO ExamAttempt
               (attempt_id, candidate_id, center_id, exam_date,
                slot_time, responses_json, time_taken_sec, raw_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attempt_id,
                candidate_id,
                center_id,
                exam_date,
                slot_time,
                responses,
                random.randint(1800, 3600),
                round(random.uniform(35, 100), 2)
            )
        )

    # Seed one result row
    row = con.execute(
        """SELECT attempt_id, candidate_id, center_id, exam_date, raw_score
           FROM ExamAttempt
           ORDER BY attempt_id
           LIMIT 1"""
    ).fetchone()

    con.execute(
        """INSERT INTO Result
           (attempt_id, candidate_id, center_id, exam_date,
            final_score, grade, published_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (row[0], row[1], row[2], row[3], row[4], "A", "Seed Examiner")
    )

    con.commit()
    con.close()

    print("Database created successfully.")
    print("Centers: 20")
    print("Candidates: 5000")
    print("Exam Attempts: 50000")
    print("Slots: 720")


# ------------------------------------------------------------
# 2. HASHING IMPLEMENTATION
# ------------------------------------------------------------

def hash_demo():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT candidate_id, attempt_id FROM ExamAttempt"
    ).fetchall()
    con.close()

    # Static hash table with separate chaining
    table = [[] for _ in range(N)]

    for candidate_id, attempt_id in rows:
        table[candidate_id % N].append((candidate_id, attempt_id))

    def hash_lookup(candidate_id):
        bucket = table[candidate_id % N]
        return [
            attempt_id
            for cid, attempt_id in bucket
            if cid == candidate_id
        ]

    def scan_lookup(candidate_id):
        return [
            attempt_id
            for cid, attempt_id in rows
            if cid == candidate_id
        ]

    candidate_id = 1001

    t0 = time.perf_counter()
    for _ in range(100):
        scan_result = scan_lookup(candidate_id)
    scan_time = (time.perf_counter() - t0) / 100

    t0 = time.perf_counter()
    for _ in range(100):
        hash_result = hash_lookup(candidate_id)
    hash_time = (time.perf_counter() - t0) / 100

    print("\nHASHING DEMO")
    print("Candidate ID:", candidate_id)
    print("Matching attempts:", len(hash_result))
    print("Scan time :", f"{scan_time:.8f}", "seconds")
    print("Hash time :", f"{hash_time:.8f}", "seconds")
    print("Correctness:", sorted(scan_result) == sorted(hash_result))


# ------------------------------------------------------------
# 3. QUERY OPTIMIZATION / EXECUTION PLAN
# ------------------------------------------------------------

def query_optimization_demo():
    con = sqlite3.connect(DB)

    queries = [
        (
            "Candidate History",
            """SELECT attempt_id, center_id, exam_date, slot_time, raw_score
               FROM ExamAttempt
               WHERE candidate_id = ?""",
            (1001,)
        ),
        (
            "Center-Date Audit",
            """SELECT attempt_id, candidate_id, exam_date, slot_time, raw_score
               FROM ExamAttempt
               WHERE center_id = ? AND exam_date = ?""",
            (5, "2026-09-05")
        ),
        (
            "Booking Window",
            """SELECT slot_id, slot_time, capacity, booked_count
               FROM Slot
               WHERE center_id = ? AND exam_date = ?""",
            (5, "2026-09-05")
        ),
        (
            "Result Summary",
            """SELECT center_id, exam_date,
                      COUNT(*) AS attempts,
                      ROUND(AVG(final_score), 2) AS avg_score
               FROM Result
               GROUP BY center_id, exam_date""",
            ()
        )
    ]

    print("\nQUERY OPTIMIZATION DEMO")

    for name, sql, params in queries:
        print("\n", name)

        plan = con.execute(
            "EXPLAIN QUERY PLAN " + sql,
            params
        ).fetchall()

        print("Execution Plan:")
        for row in plan:
            print(row)

        t0 = time.perf_counter()

        for _ in range(100):
            result = con.execute(sql, params).fetchall()

        elapsed = (time.perf_counter() - t0) / 100

        print("Rows returned:", len(result))
        print("Average time:", f"{elapsed:.8f}", "seconds")

    con.close()


# ------------------------------------------------------------
# 4. ACID BOOKING TRANSACTION
# ------------------------------------------------------------

def book_slot(candidate_id, slot_id):
    con = sqlite3.connect(DB, timeout=10)

    try:
        con.execute("BEGIN IMMEDIATE")

        row = con.execute(
            """SELECT capacity, booked_count
               FROM Slot
               WHERE slot_id = ?""",
            (slot_id,)
        ).fetchone()

        if row is None:
            con.rollback()
            return "SLOT_NOT_FOUND"

        capacity, booked_count = row

        con.execute("SAVEPOINT capacity_check")

        if booked_count >= capacity:
            con.execute("ROLLBACK TO capacity_check")
            con.execute("RELEASE capacity_check")
            con.rollback()
            return "SLOT_FULL"

        con.execute("RELEASE capacity_check")

        con.execute(
            """INSERT INTO Booking(candidate_id, slot_id, status)
               VALUES (?, ?, 'CONFIRMED')""",
            (candidate_id, slot_id)
        )

        cur = con.execute(
            """UPDATE Slot
               SET booked_count = booked_count + 1
               WHERE slot_id = ?
                 AND booked_count < capacity""",
            (slot_id,)
        )

        if cur.rowcount != 1:
            con.rollback()
            return "SLOT_FULL"

        con.commit()
        return "BOOKED"

    except sqlite3.IntegrityError:
        con.rollback()
        return "BOOKING_REJECTED"

    except Exception:
        con.rollback()
        raise

    finally:
        con.close()


def rollback_demo():
    con = sqlite3.connect(DB)

    try:
        slot_id = 1

        before = con.execute(
            "SELECT booked_count FROM Slot WHERE slot_id = ?",
            (slot_id,)
        ).fetchone()[0]

        con.execute("BEGIN")

        con.execute(
            """INSERT INTO Booking(candidate_id, slot_id, status)
               VALUES (?, ?, 'CONFIRMED')""",
            (4998, slot_id)
        )

        con.execute(
            """UPDATE Slot
               SET booked_count = booked_count + 1
               WHERE slot_id = ?""",
            (slot_id,)
        )

        raise RuntimeError("SIMULATED_FAILURE")

    except RuntimeError:
        con.rollback()

        after = con.execute(
            "SELECT booked_count FROM Slot WHERE slot_id = ?",
            (slot_id,)
        ).fetchone()[0]

        print("\nROLLBACK DEMO")
        print("Before:", before)
        print("After :", after)
        print("Rollback successful:", before == after)

    finally:
        con.close()


# ------------------------------------------------------------
# 5. OPTIMISTIC RESULT UPDATE
# ------------------------------------------------------------

def publish_result(result_id, score, grade, examiner, expected_version):
    con = sqlite3.connect(DB)

    try:
        con.execute("BEGIN")

        cur = con.execute(
            """UPDATE Result
               SET final_score = ?,
                   grade = ?,
                   published_by = ?,
                   published_on = datetime('now'),
                   version = version + 1
               WHERE result_id = ?
                 AND version = ?""",
            (
                score,
                grade,
                examiner,
                result_id,
                expected_version
            )
        )

        if cur.rowcount != 1:
            con.rollback()
            return "VERSION_CONFLICT"

        con.commit()
        return "UPDATED"

    finally:
        con.close()


def result_concurrency_demo():
    con = sqlite3.connect(DB)

    result_id, version = con.execute(
        """SELECT result_id, version
           FROM Result
           ORDER BY result_id
           LIMIT 1"""
    ).fetchone()

    con.close()

    examiner_a_version = version
    examiner_b_version = version

    first = publish_result(
        result_id,
        82.0,
        "A",
        "Examiner-A",
        examiner_a_version
    )

    second = publish_result(
        result_id,
        95.0,
        "A+",
        "Examiner-B",
        examiner_b_version
    )

    print("\nOPTIMISTIC RESULT CONCURRENCY DEMO")
    print("Examiner A:", first)
    print("Examiner B:", second)


# ------------------------------------------------------------
# 6. CONCURRENT BOOKING TEST
# ------------------------------------------------------------

def concurrency_test():
    slot_id = 3
    capacity = 1
    thread_count = 20

    con = sqlite3.connect(DB)

    con.execute(
        """UPDATE Slot
           SET capacity = ?, booked_count = 0
           WHERE slot_id = ?""",
        (capacity, slot_id)
    )

    con.execute(
        "DELETE FROM Booking WHERE slot_id = ?",
        (slot_id,)
    )

    con.commit()
    con.close()

    results = []
    lock = threading.Lock()

    def worker(candidate_id):
        result = book_slot(candidate_id, slot_id)

        with lock:
            results.append(result)

    threads = []

    for candidate_id in range(1, thread_count + 1):
        t = threading.Thread(
            target=worker,
            args=(candidate_id,)
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    con = sqlite3.connect(DB)

    actual_rows = con.execute(
        """SELECT COUNT(*)
           FROM Booking
           WHERE slot_id = ?
             AND status = 'CONFIRMED'""",
        (slot_id,)
    ).fetchone()[0]

    booked_count = con.execute(
        """SELECT booked_count
           FROM Slot
           WHERE slot_id = ?""",
        (slot_id,)
    ).fetchone()[0]

    con.close()

    print("\nCONCURRENCY TEST")
    print("Concurrent requests:", thread_count)
    print("Slot capacity:", capacity)
    print("Successful bookings:", results.count("BOOKED"))
    print("Rejected:", results.count("SLOT_FULL"))
    print("Actual booking rows:", actual_rows)
    print("Final booked_count:", booked_count)
    print(
        "Capacity respected:",
        actual_rows <= capacity and booked_count <= capacity
    )


# ------------------------------------------------------------
# 7. MAIN
# ------------------------------------------------------------

def main():
    print("=" * 70)
    print("NATIONAL VOCATIONAL CERTIFICATION AND EXAM SLOT-BOOKING SYSTEM")
    print("=" * 70)

    create_and_seed_database()

    hash_demo()

    query_optimization_demo()

    print("\nTRANSACTION DEMO")
    print("Booking candidate 4999 into slot 1:",
          book_slot(4999, 1))

    rollback_demo()

    result_concurrency_demo()

    concurrency_test()

    print("\nALL DEMONSTRATIONS COMPLETED.")
    print("Database file:", DB)


if __name__ == "__main__":
    main()
