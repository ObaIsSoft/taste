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
            update voting_config
               set repeat_count = 2, overlap_share = 0, reason_every = 1, min_vote_seconds = 0;
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
    terms="{}",
):
    return db.run(
        f"select cast_vote('{code}', '{pair['token']}', '{outcome}', '{dims}', '{reason}', "
        f"'{terms}')"
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
    assert "say what decided it" in db.error(
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
    assert "42501" in db.error("set role anon; select * from voter_agreement")
    assert "42501" in db.error("set role anon; select * from next_pair('code-ada', 'visual')")


def _add_sites_and_voters(db):
    db.run(
        """
        insert into sites (id, url, cohort)
        select i, format('https://%s.test/', i), 'award' from generate_series(5, 8) i
        on conflict do nothing;
        insert into captures (id, site_id, variant, capture_version, qa_passed, stills,
                              reel_path, in_pool)
        select format('%s-original', lpad(i::text, 4, '0')), i, 'original', '2.0.0', true,
               array[format('%s-original/screen-1.jpg', lpad(i::text, 4, '0'))],
               format('%s-original/reel.mp4', lpad(i::text, 4, '0')), true
          from generate_series(5, 8) i
        on conflict do nothing;
        insert into voters (name, invite_code)
        values ('Cy', 'code-cy'), ('Di', 'code-di'), ('Ed', 'code-ed'), ('Fi', 'code-fi')
        on conflict do nothing;
        """
    )


def _serve(db, code, left, right, round_kind="visual"):
    """Serve a chosen pair, as next_pair would, so a test can script who saw what."""
    [[token]] = db.run(
        f"with s as (insert into served_pairs (voter_id, round, left_capture, right_capture, "
        f"source, reason_requested) select id, '{round_kind}', '{left}', '{right}', "
        f"'adaptive', false from voters where invite_code = '{code}' returning token) "
        f"select token from s"
    )
    return {"token": token, "left": left, "right": right}


def _c(number):
    return f"{number:04d}-original"


def test_agreement_views_line_up_votes_whatever_side_sites_were_on(db):
    _add_sites_and_voters(db)
    p, q = (_c(5), _c(6)), (_c(7), _c(8))
    # Cy prefers 5 over 6 twice (sides swapped the second time), and flips on 7 vs 8.
    _vote(db, _serve(db, "code-cy", p[0], p[1]), "left", code="code-cy")
    _vote(db, _serve(db, "code-cy", p[1], p[0]), "right", code="code-cy")
    _vote(db, _serve(db, "code-cy", q[0], q[1]), "right", code="code-cy")
    _vote(db, _serve(db, "code-cy", q[1], q[0]), "right", code="code-cy")
    # Di disagrees with Cy on 5 vs 6, and agrees on 7 vs 8.
    _vote(db, _serve(db, "code-di", p[1], p[0]), "left", code="code-di")
    _vote(db, _serve(db, "code-di", q[0], q[1]), "right", code="code-di")
    # In the motion round Cy prefers 6, and finds 7 and 8 equally good.
    motion = {"dims": "{smoothness}", "code": "code-cy"}
    _vote(db, _serve(db, "code-cy", p[0], p[1], "motion"), "right", **motion)
    _vote(db, _serve(db, "code-cy", q[1], q[0], "motion"), "equally_good", **motion)

    assert db.run(
        "select repeated_pairs, same_verdict, flipped, consistency from voter_consistency "
        "where voter = 'Cy' and round = 'visual'"
    ) == [["2", "1", "1", "0.500"]]
    assert db.run(
        "select shared_pairs, same_verdict, opposite, agreement from voter_agreement "
        "where round = 'visual' and 'Cy' in (voter_a, voter_b) and 'Di' in (voter_a, voter_b)"
    ) == [["2", "1", "1", "0.500"]]
    assert db.run(
        f"select pair_low, judged, low_better, high_better, split, agreement "
        f"from pair_agreement where round = 'visual' and pair_low in ('{p[0]}', '{q[0]}') "
        f"order by pair_low"
    ) == [[p[0], "2", "1", "1", "t", "0.500"], [q[0], "2", "0", "2", "f", "1.000"]]
    assert db.run(
        "select pair_low, visual, motion, differs, opposite, visual_dimensions, "
        "motion_dimensions from round_differences where voter = 'Cy' order by pair_low"
    ) == [
        [p[0], "low", "high", "t", "t", "{whitespace}", "{smoothness}"],
        [q[0], "high", "tie", "t", "f", "{whitespace}", "{smoothness}"],
    ]


def test_reasons_are_asked_where_they_explain_a_difference(db):
    _add_sites_and_voters(db)
    contested = (_c(5), _c(6))  # Cy and Di split on it in the test above
    db.run(
        f"""
        update voting_config set reason_every = 1000000;  -- no reasons at random
        insert into calibration_pairs (round, capture_a, capture_b) values
          ('visual', '{contested[0]}', '{contested[1]}'),
          ('motion', '{_c(1)}', '{_c(2)}'), ('motion', '{contested[0]}', '{contested[1]}');
        update captures set in_pool = false where id = '{_c(3)}';  -- reported broken
        """
    )
    try:
        asked = {}
        for _ in range(2):
            pair = _next(db, code="code-ed")
            assert pair["source"] == "calibration"
            asked[frozenset((pair["left"], pair["right"]))] = pair["reason"]
            _vote(db, pair, code="code-ed")
        # Pairs with the pulled capture are skipped; the split pair asks for a reason.
        assert asked == {frozenset((_c(1), _c(2))): "f", frozenset(contested): "t"}
        assert db.run(
            "select calibration_done, calibration_total from voter_progress('code-ed') "
            "where round = 'visual'"
        ) == [["2", "2"]]

        # In the motion round Ed is asked exactly where the visual round asked.
        for _ in range(2):
            pair = _next(db, code="code-ed", round_kind="motion")
            assert pair["source"] == "calibration"
            assert pair["reason"] == asked[frozenset((pair["left"], pair["right"]))]
            _vote(db, pair, dims="{pacing}", code="code-ed")
    finally:
        db.run(
            f"update voting_config set reason_every = 1; "
            f"update captures set in_pool = true where id = '{_c(3)}'"
        )


def test_votes_faster_than_a_person_can_look_are_refused(db):
    _add_sites_and_voters(db)
    db.run("update voting_config set min_vote_seconds = 60")
    try:
        pair = _serve(db, "code-fi", _c(7), _c(8))
        assert "P0429" in db.error(
            f"select cast_vote('code-fi', '{pair['token']}', 'cant_decide', '{{}}', null)"
        )
    finally:
        db.run("update voting_config set min_vote_seconds = 0")
    assert db.run("select count(*) from voter_effort where voter = 'Cy'") == [["2"]]


def test_a_voter_who_paired_the_rarest_capture_with_everything_still_gets_pairs(db):
    _add_sites_and_voters(db)
    rare, others = _c(4), (_c(7), _c(8))
    keep = ", ".join(f"'{c}'" for c in (rare, *others))
    db.run(f"update captures set in_pool = id in ({keep})")
    try:
        for other in others:  # Fi has judged the rarest capture against both others
            _vote(db, _serve(db, "code-fi", rare, other), "left", code="code-fi")
        for _ in range(3):  # and other voters made the two others the most compared
            _vote(db, _serve(db, "code-cy", *others), "left", code="code-cy")
        pair = _next(db, code="code-fi")
        assert pair["source"] == "adaptive"
        assert {pair["left"], pair["right"]} == set(others)
    finally:
        db.run("update captures set in_pool = true")


def test_voters_can_say_it_in_their_own_words(db):
    _add_sites_and_voters(db)
    words = '{"tension between serif and grotesk", " editorial pacing ", "editorial pacing"}'
    _vote(db, _serve(db, "code-ed", _c(5), _c(7)), "left", dims="{}", code="code-ed", terms=words)
    [[stored]] = db.run("select own_terms from votes order by id desc limit 1")
    assert stored == '{"editorial pacing","tension between serif and grotesk"}'  # trimmed, once

    pair = _serve(db, "code-ed", _c(6), _c(8))
    assert "say what decided it" in db.error(
        f"select cast_vote('code-ed', '{pair['token']}', 'left', '{{}}', 'reason', '{{}}')"
    )
    assert "under 40 characters" in db.error(
        f"select cast_vote('code-ed', '{pair['token']}', 'left', '{{}}', 'reason', "
        f"'{{\"{'x' * 41}\"}}')"
    )
    _vote(db, pair, "right", dims="{colour}", code="code-ed", terms="{editorial pacing}")
    assert db.run("select term, uses from voter_terms('code-ed', 'visual') limit 2") == [
        ["editorial pacing", "2"],
        ["tension between serif and grotesk", "1"],
    ]
    assert db.run("select count(*) from voter_terms('code-cy', 'visual')") == [["0"]]
