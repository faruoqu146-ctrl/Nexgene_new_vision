"""Schema-migration and engine-claim guards, tested at the SQL level with stdlib sqlite3.

The DDL under test is EXTRACTED from backend/app/main.py (not retyped), so these tests exercise the real
statements. They cannot exercise the SQLAlchemy wrapper or the HTTP layer (those need the app's dependencies).
"""
import ast
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "backend" / "app" / "main.py"
MAIN = MAIN_PATH.read_text(encoding="utf-8")
TREE = ast.parse(MAIN)


def _str_constants():
    return [n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _ddl(prefix):
    found = [s for s in _str_constants() if s.startswith(prefix)]
    assert len(found) == 1, (prefix, found)
    return found[0]


ADD_OBSERVED_AT = _ddl("ALTER TABLE observations ADD COLUMN observed_at")
ONE_RUNNING_INDEX = _ddl("CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_runs_one_running")


def legacy_db(path=":memory:"):
    c = sqlite3.connect(path, isolation_level=None, timeout=10)
    c.executescript("""
        CREATE TABLE observations (id INTEGER PRIMARY KEY, user_id INT, kind TEXT, value_numeric FLOAT, value_text TEXT, recorded_at DATETIME);
        CREATE TABLE intelligence_runs (id INTEGER PRIMARY KEY, user_id INT, status TEXT, created_at DATETIME);
        INSERT INTO observations (user_id, kind, value_numeric, recorded_at) VALUES (1,'sleep_duration',7.5,'2026-10-01 08:00:00.000000'),(1,'energy',6,'2026-10-02 08:00:00.000000');
    """)
    return c


def migrate(c):
    """Same guard main.py uses: add the column only if missing; index creation is IF NOT EXISTS."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(observations)")}
    if "observed_at" not in cols:
        c.execute(ADD_OBSERVED_AT)
    c.execute(ONE_RUNNING_INDEX)


class MigrationSafety(unittest.TestCase):
    def test_existing_data_survives_and_legacy_event_time_stays_null(self):
        c = legacy_db(); migrate(c)
        rows = c.execute("SELECT kind, value_numeric, recorded_at, observed_at FROM observations ORDER BY id").fetchall()
        self.assertEqual(rows, [("sleep_duration", 7.5, "2026-10-01 08:00:00.000000", None), ("energy", 6.0, "2026-10-02 08:00:00.000000", None)])

    def test_migration_is_idempotent(self):
        c = legacy_db(); migrate(c); migrate(c); migrate(c)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 2)
        self.assertEqual(sum(1 for r in c.execute("PRAGMA index_list(intelligence_runs)") if r[1] == "uq_intelligence_runs_one_running"), 1)

    def test_a_failing_mandatory_statement_raises_instead_of_being_swallowed(self):
        c = legacy_db(); migrate(c)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute(ADD_OBSERVED_AT)          # duplicate column: must surface, not pass silently

    def test_mandatory_migrations_are_not_wrapped_in_try_except_in_main(self):
        # A swallowed exception around mandatory DDL would let the app start on a broken schema.
        for node in ast.walk(TREE):
            if isinstance(node, ast.Try):
                inner = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
                self.assertNotIn(ONE_RUNNING_INDEX, inner)
                self.assertNotIn(ADD_OBSERVED_AT, inner)

    def test_deploy_files_do_not_mask_failures(self):
        for name in ("Dockerfile", "docker-compose.yml"):
            text = (ROOT / name).read_text()
            self.assertNotIn("|| true", text, name)
            self.assertNotIn("; true", text, name)


class EngineClaim(unittest.TestCase):
    def setUp(self):
        self.c = legacy_db(); migrate(self.c)

    def test_second_running_row_for_the_same_user_is_rejected(self):
        self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 12:00:00')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 12:00:01')")

    def test_history_and_other_users_are_not_blocked(self):
        for st in ("completed", "completed", "failed", "interrupted"):
            self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,?, '2026-10-25 12:00:00')", (st,))
        self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 12:00:00')")
        self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (2,'running','2026-10-25 12:00:00')")

    def test_stale_running_row_can_be_reclaimed_after_marking_interrupted(self):
        self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 10:00:00')")
        self.c.execute("UPDATE intelligence_runs SET status='interrupted' WHERE user_id=1 AND status='running' AND created_at < '2026-10-25 11:45:00'")
        self.c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 12:00:00')")
        self.assertEqual(self.c.execute("SELECT status FROM intelligence_runs WHERE user_id=1 ORDER BY id").fetchall(), [("interrupted",), ("running",)])

    def test_concurrent_claims_yield_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "claim.db")
            legacy_db(db).close()
            c0 = sqlite3.connect(db, isolation_level=None); migrate(c0); c0.close()
            results, barrier = [], threading.Barrier(8)

            def claim():
                c = sqlite3.connect(db, isolation_level=None, timeout=10)
                barrier.wait()
                try:
                    c.execute("INSERT INTO intelligence_runs (user_id,status,created_at) VALUES (1,'running','2026-10-25 12:00:00')")
                    results.append("won")
                except sqlite3.IntegrityError:
                    results.append("busy")
                finally:
                    c.close()

            ts = [threading.Thread(target=claim) for _ in range(8)]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual((results.count("won"), results.count("busy")), (1, 7))


class SourceContracts(unittest.TestCase):
    """Static regression guards: main.py must keep using the temporal contract."""

    def test_event_time_is_used_for_observation_queries(self):
        # Observation.recorded_at may appear only in: the model, the OBS_EVENT_TIME helper, and the
        # intentional ingestion-time max() used for engine staleness.
        allowed = ("recorded_at: Mapped", "OBS_EVENT_TIME = func.coalesce", "func.max(Observation.recorded_at)")
        for i, line in enumerate(MAIN.splitlines(), 1):
            if "Observation.recorded_at" in line:
                self.assertTrue(any(a in line for a in allowed), f"main.py:{i} filters Observation by recorded_at: {line.strip()[:100]}")

    def test_checkin_validates_event_time_and_stores_both_instants(self):
        seg = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "save_checkin"))
        self.assertIn("validate_event_time", seg)
        self.assertIn("observed_at=event_time", seg)
        self.assertIn("recorded_at=recorded", seg)

    def test_weekly_endpoint_delegates_to_the_report_assembler(self):
        seg = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "weekly_report"))
        self.assertIn("build_weekly_report", seg)
        self.assertIn("OBS_EVENT_TIME", seg)                       # period membership by EVENT time
        self.assertNotIn("Observation.recorded_at >=", seg)        # never filter periods by ingestion time
        self.assertNotIn("r.recorded_at", seg)

    def test_engine_run_records_failures(self):
        seg = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "run_intelligence_engine"))
        self.assertIn('status = "failed"', seg)
        self.assertIn("_claim_engine_run", seg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
