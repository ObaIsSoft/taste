"""The voting schema and functions, run against a throwaway local Postgres.

Set PG_BIN to a Postgres bin directory if pg_ctl is not on PATH. Skipped when
no Postgres is available.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

MIGRATION = Path(__file__).parent.parent / "supabase" / "migrations" / "0001_v2_voting.sql"

pytestmark = pytest.mark.postgres


def _bin(name):
    directory = os.environ.get("PG_BIN")
    path = Path(directory) / name if directory else shutil.which(name)
    return str(path) if path and Path(path).exists() else None


class Database:
    def __init__(self, psql, socket_dir):
        self.base = [psql, "-h", socket_dir, "-U", "postgres", "-d", "taste", "-At", "-F", "|"]
        self.base += ["-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose"]

    def run(self, query):
        result = subprocess.run([*self.base, "-c", query], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return [line.split("|") for line in result.stdout.strip().splitlines() if line]

    def error(self, query):
        result = subprocess.run([*self.base, "-c", query], capture_output=True, text=True)
        assert result.returncode != 0, "expected an error"
        return result.stderr

    def file(self, path):
        result = subprocess.run([*self.base, "-f", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def db():
    pg_ctl, initdb, psql = _bin("pg_ctl"), _bin("initdb"), _bin("psql")
    if not (pg_ctl and initdb and psql):
        pytest.skip("Postgres binaries not found; set PG_BIN")
    root = tempfile.mkdtemp(prefix="tpg")
    data = Path(root) / "data"
    subprocess.run(
        [initdb, "-D", str(data), "-U", "postgres", "-A", "trust", "--no-locale", "-E", "UTF8"],
        check=True,
        capture_output=True,
    )
    options = f"-k {root} -c listen_addresses=''"
    log = str(
        Path(root) / "server.log"
    )  # the server must not inherit our pipes, or run() never returns
    subprocess.run(
        [pg_ctl, "-D", str(data), "-l", log, "-o", options, "-w", "start"],
        check=True,
        capture_output=True,
    )
    try:
        admin = [psql, "-h", root, "-U", "postgres", "-d", "postgres", "-c"]
        subprocess.run([*admin, "create database taste"], check=True, capture_output=True)
        database = Database(psql, root)
        database.run("create role anon nologin; create role authenticated nologin;")
        database.file(MIGRATION)
        database.run(
            """
            insert into sites (id, url, cohort) values
              (1, 'https://a.test/', 'award'), (2, 'https://b.test/', 'award'),
              (3, 'https://c.test/', 'award'), (4, 'https://d.test/', 'award');
            insert into captures (id, site_id, variant, capture_version, qa_passed, stills,
                                  reel_path, in_pool)
            select format('%s-original', lpad(i::text, 4, '0')), i, 'original', '2.0.0', true,
                   array[format('%s-original/screen-1.jpg', lpad(i::text, 4, '0'))],
                   format('%s-original/reel.mp4', lpad(i::text, 4, '0')), true
              from generate_series(1, 4) i;
            insert into voters (name, invite_code) values ('Ada', 'code-ada'), ('Bo', 'code-bo');
            insert into calibration_pairs (round, capture_a, capture_b) values
              ('visual', '0001-original', '0002-original'),
              ('visual', '0001-original', '0003-original'),
              ('visual', '0002-original', '0003-original');
            update voting_config set repeat_count = 2, overlap_share = 0, reason_every = 1;
            """
        )
        yield database
    finally:
        subprocess.run([pg_ctl, "-D", str(data), "-m", "immediate", "stop"], capture_output=True)
        shutil.rmtree(root, ignore_errors=True)


def _next(db, code="code-ada", round_kind="visual"):
    [[token, source, left, right, reason]] = db.run(
        f"select token, source, left_capture, right_capture, reason_requested "
        f"from next_pair('{code}', '{round_kind}')"
    )
    return {"token": token, "source": source, "left": left, "right": right, "reason": reason}


def _vote(
    db,
    pair,
    outcome="left",
    dims="{whitespace}",
    reason="the type scale is calmer",
    code="code-ada",
):
    return db.run(
        f"select cast_vote('{code}', '{pair['token']}', '{outcome}', '{dims}', '{reason}')"
    )


def test_calibration_then_swapped_repeats_then_adaptive(db):
    first_sides = {}
    for _ in range(3):
        pair = _next(db)
        assert pair["source"] == "calibration"
        assert pair["token"] == _next(db)["token"]  # a refresh serves the same pair again
        first_sides[frozenset((pair["left"], pair["right"]))] = pair["left"]
        _vote(db, pair)

    for _ in range(2):
        pair = _next(db)
        assert pair["source"] == "repeat"
        assert first_sides[frozenset((pair["left"], pair["right"]))] == pair["right"]  # swapped
        _vote(db, pair)

    pair = _next(db)
    assert pair["source"] == "adaptive"
    assert "0004-original" in (pair["left"], pair["right"])  # the only pairs Ada has not judged
    _vote(db, pair, outcome="equally_good", dims="{}")

    [[_, done, total, votes]] = db.run(
        "select * from voter_progress('code-ada') where round = 'visual'"
    )
    assert (done, total, votes) == ("3", "3", "6")


def test_vote_rules_are_enforced_by_the_database(db):
    pair = _next(db, code="code-bo")
    assert "28000" in db.error("select * from next_pair('nobody', 'visual')")
    assert "22023" in db.error(
        f"select cast_vote('code-ada', '{pair['token']}', 'left', '{{whitespace}}', 'good reason!')"
    )
    assert "pick at least one dimension" in db.error(
        f"select cast_vote('code-bo', '{pair['token']}', 'left', '{{}}', 'good reason!')"
    )
    assert "unknown dimension" in db.error(
        f"select cast_vote('code-bo', '{pair['token']}', 'left', '{{smoothness}}', 'good reason!')"
    )
    assert "at most 3 dimensions" in db.error(
        f"select cast_vote('code-bo', '{pair['token']}', 'left', "
        f"'{{whitespace,colour,layout,imagery}}', 'good reason!')"
    )
    assert "at least 10 characters" in db.error(
        f"select cast_vote('code-bo', '{pair['token']}', 'right', '{{colour}}', 'meh')"
    )
    _vote(db, pair, outcome="cant_decide", dims="{}", reason="", code="code-bo")
    assert "23505" in db.error(
        f"select cast_vote('code-bo', '{pair['token']}', 'left', '{{colour}}', 'changed my mind')"
    )


def test_a_broken_report_pulls_the_capture_from_the_pool(db):
    pair = _next(db, code="code-bo")
    _vote(db, pair, outcome="broken_left", dims="{}", reason="", code="code-bo")
    [[in_pool, note]] = db.run(f"select in_pool, qa_note from captures where id = '{pair['left']}'")
    assert in_pool == "f" and note == "reported broken by a voter"
    db.run(f"update captures set in_pool = true, qa_note = null where id = '{pair['left']}'")


def test_motion_rounds_use_motion_dimensions(db):
    pair = _next(db, round_kind="motion")
    assert pair["source"] == "adaptive"  # no motion calibration set in this fixture
    _vote(db, pair, outcome="right", dims="{smoothness,pacing}")


def test_browsers_cannot_touch_the_tables(db):
    assert "42501" in db.error("set role anon; select * from votes")
    assert "42501" in db.error("set role anon; select * from next_pair('code-ada', 'visual')")
