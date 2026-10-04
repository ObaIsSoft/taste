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

MIGRATIONS = sorted((Path(__file__).parent.parent / "supabase" / "migrations").glob("*.sql"))

pytestmark = pytest.mark.postgres

# What taste publish does for each capture: register its media as a version, then point at it.
PUBLISH_MEDIA = """
    insert into capture_media (capture_id, media_id, capture_version, stills, reel_path, files)
    select id, 'm1-' || id, capture_version, stills, reel_path, '{}' from captures
     where media_id is null
    on conflict do nothing;
    update captures set media_id = 'm1-' || id where media_id is null;
"""


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
        for migration in MIGRATIONS:  # in order, as they are applied to the live database
            database.file(migration)
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
            """
            + PUBLISH_MEDIA
            + """
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

    [[_, done, total, votes, target]] = db.run(
        "select * from voter_progress('code-ada') where round = 'visual'"
    )
    assert (done, total, votes, target) == ("3", "3", "6", "200")  # from round_targets


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
        """
        + PUBLISH_MEDIA
        + """
        insert into voters (name, invite_code)
        values ('Cy', 'code-cy'), ('Di', 'code-di'), ('Ed', 'code-ed'), ('Fi', 'code-fi'),
               ('Gi', 'code-gi')
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


def test_sides_are_balanced_per_site(db):
    _add_sites_and_voters(db)
    busy, other = _c(7), _c(8)
    keep = ", ".join(f"'{c}'" for c in (busy, other))
    db.run(f"update captures set in_pool = id in ({keep})")
    try:
        for _ in range(3):  # the busy site has been shown on the left three times already
            _serve(db, "code-cy", busy, other, "motion")
        pair = _next(db, code="code-gi", round_kind="motion")
        assert (pair["left"], pair["right"]) == (other, busy)
    finally:
        db.run("update captures set in_pool = true")


def test_how_a_vote_was_cast_is_recorded_and_processed(db):
    _add_sites_and_voters(db)
    client = '{"session": "s1", "index": 1, "layout": "tabs", "viewport_width": 390}'
    pair = _serve(db, "code-gi", _c(5), _c(8))
    db.run(f"insert into vote_events (token, kind) values ('{pair['token']}', 'scroll_left')")
    db.run(
        f"select cast_vote('code-gi', '{pair['token']}', 'left', '{{whitespace}}', 'reason here', "
        f"'{{}}', '{client}')"
    )
    assert db.run("select client ->> 'viewport_width' from votes order by id desc limit 1") == [
        ["390"]
    ]
    # on a phone the voter never opened B, and scrolled only A: both are visible in the bias view
    assert db.run(
        "select layout, votes, left_share, saw_both_share, scrolled_both_share from voter_bias "
        "where voter = 'Gi' and round = 'visual'"
    ) == [["tabs", "1", "1.000", "0.000", "0.000"]]
    assert db.run(
        "select sessions, early_median_seconds is not null from voter_effort "
        "where voter = 'Gi' and round = 'visual'"
    ) == [["1", "t"]]
    pair = _serve(db, "code-gi", _c(6), _c(7))
    assert "small object" in db.error(
        f"select cast_vote('code-gi', '{pair['token']}', 'left', '{{whitespace}}', 'reason', "
        f"'{{}}', '[1, 2]')"
    )


def test_wins_by_language_come_from_the_descriptions(db):
    _add_sites_and_voters(db)
    db.run(
        f"""update captures set description = '{{"description": {{"language": "it"}}}}'
            where id = '{_c(5)}'"""
    )
    rows = dict(
        (language, (appearances, share))
        for language, appearances, share in db.run(
            "select language, appearances, win_share from language_bias where round = 'visual'"
        )
    )
    assert "it" in rows and "unknown" in rows


def test_voting_facts_and_definitions_come_from_one_place(db):
    import json

    [[facts]] = db.run("select voting_facts()")
    facts = json.loads(facts)
    assert facts["max_dimensions"] == 3 and facts["min_reason_chars"] == 10
    assert facts["idle_cutoff_seconds"] == 120  # the voting page counts active time with it
    assert facts["rounds"]["motion"]["target_votes"] == 100
    assert facts["rounds"]["visual"]["target_votes"] == 200
    assert facts["rounds"]["visual"]["calibration_pairs"] >= 3
    assert db.run("select count(*) from dimensions where description = ''") == [["0"]]


def test_time_on_screen_is_processed_apart_from_wall_clock_time(db):
    _add_sites_and_voters(db)
    db.run("insert into voters (name, invite_code) values ('Hu', 'code-hu')")
    # served two hours ago, but on screen and in use for 35 s after leaving the page once
    timed = (
        '{"timing": {"visible_s": 40.5, "active_s": 35.0, "away_count": 1, "longest_idle_s": 12.0}}'
    )
    first = _serve(db, "code-hu", _c(5), _c(6))
    db.run(
        f"update served_pairs set served_at = now() - interval '2 hours' "
        f"where token = '{first['token']}'"
    )
    db.run(
        f"select cast_vote('code-hu', '{first['token']}', 'left', '{{whitespace}}', "
        f"'a calmer grid', '{{}}', '{timed}')"
    )
    assert db.run(
        f"select visible_seconds, active_seconds, away_count, left_page from vote_attention "
        f"where token = '{first['token']}'"
    ) == [["40.5", "35.0", "1", "t"]]
    # a vote from before the page measured time has none, and is left out of active medians
    second = _serve(db, "code-hu", _c(7), _c(8))
    db.run(
        f"select cast_vote('code-hu', '{second['token']}', 'equally_good', '{{}}', null, "
        f"'{{}}', '{{}}')"
    )
    # the first vote was cast a day earlier: the two are separate sittings
    db.run(
        f"update votes set created_at = now() - interval '1 day' where token = '{first['token']}'"
    )
    assert db.run(
        "select votes, timed_votes, median_active_seconds, sittings, sessions, left_page_votes, "
        "idle_votes from voter_effort where voter = 'Hu' and round = 'visual'"
    ) == [["2", "1", "35.0", "2", "0", "1", "1"]]  # no page session ids here, so 0 sessions
    assert db.run(
        "select left_page_share from voter_bias where voter = 'Hu' and round = 'visual'"
    ) == [["1.000"]]


def test_a_vote_keeps_pointing_at_what_it_showed(db):
    _add_sites_and_voters(db)
    db.run("insert into voters (name, invite_code) values ('Io', 'code-io')")
    pair = _serve(db, "code-io", _c(5), _c(6))
    _vote(db, pair, code="code-io")
    pinned = f"select left_media, right_media from votes where token = '{pair['token']}'"
    assert db.run(pinned) == [["m1-0005-original", "m1-0006-original"]]

    # 0005 is captured again and published as a new version
    db.run(
        "insert into capture_media (capture_id, media_id, capture_version, stills, files) "
        "values ('0005-original', 'm2-0005-original', '2.4.0', '{0005-original/m2/screen-1.jpg}', "
        "'{}'); update captures set media_id = 'm2-0005-original' where id = '0005-original'"
    )
    assert db.run(pinned) == [["m1-0005-original", "m1-0006-original"]]  # the vote still points
    later = _serve(db, "code-io", _c(5), _c(7))
    assert db.run(f"select left_media from served_pairs where token = '{later['token']}'") == [
        ["m2-0005-original"]
    ]  # a pair served now shows the new version

    # none of it can be rewritten: pins, published versions, which URL a site is
    for change in (
        f"update votes set left_media = 'm2-0005-original' where token = '{pair['token']}'",
        f"update served_pairs set right_capture = '{_c(8)}' where token = '{pair['token']}'",
        "update capture_media set stills = '{x}' where media_id = 'm1-0005-original'",
        "delete from capture_media where media_id = 'm1-0005-original'",
        "update sites set url = 'https://elsewhere.test/' where id = 5",
        "update captures set site_id = 6 where id = '0005-original'",
    ):
        assert "55000" in db.error(change), change


def test_a_capture_without_published_media_is_never_shown(db):
    db.run(
        "insert into sites (id, url, cohort) values (9, 'https://i.test/', 'award'); "
        "insert into captures (id, site_id, variant, capture_version, qa_passed, stills, "
        "reel_path, in_pool) values ('0009-original', 9, 'original', '2.4.0', true, "
        "'{0009-original/screen-1.jpg}', '0009-original/reel.mp4', true)"
    )
    assert db.run("select servable(c, 'visual') from captures c where id = '0009-original'") == [
        ["f"]
    ]
