from types import SimpleNamespace

from taste_engine import agreement, db
from taste_engine.cli import build_parser


class PagedView:
    """A table or view behind the REST API, which returns at most PAGE_ROWS rows a request."""

    def __init__(self, rows):
        self.rows, self.tables, self.orders = rows, [], []

    def table(self, name):
        self.tables.append(name)
        return self

    def select(self, _columns):
        self.orders.append([])
        return self

    def order(self, column):
        self.orders[-1].append(column)
        return self

    def range(self, start, end):
        self.page = self.rows[start : end + 1]
        return self

    def execute(self):
        return SimpleNamespace(data=self.page)


def test_every_page_is_read_in_a_stable_order():
    view = PagedView([{"n": i} for i in range(db.PAGE_ROWS * 2 + 5)])
    rows = db.select_all(view, "voter_consistency", ("round", "voter_id"))
    assert rows == view.rows
    assert view.orders == [["round", "voter_id"]] * 3


def test_fetch_reads_each_agreement_view():
    view = PagedView([])
    assert agreement.fetch(view) == {name: [] for name in agreement.VIEWS}
    assert view.tables == list(agreement.VIEWS)


def test_summary_counts_agreement_and_differences():
    views = {
        "pair_agreement": [
            {"round": "visual", "judged": 2, "agreement": 0.5, "split": True},
            {"round": "visual", "judged": 3, "agreement": "1.000", "split": False},
            {"round": "visual", "judged": 1, "agreement": 1, "split": False},  # one voter: skipped
        ],
        "voter_agreement": [
            {
                "round": "visual",
                "voter_a": "Ada",
                "voter_b": "Bo",
                "shared_pairs": 4,
                "same_verdict": 3,
                "opposite": 1,
            }
        ],
        "voter_effort": [
            {
                "round": "visual",
                "voter": "Ada",
                "votes": 120,
                "fast_votes": 3,
                "median_seconds": 8.5,
            }
        ],
        "voter_consistency": [
            {
                "round": "visual",
                "voter": "Ada",
                "repeated_pairs": 10,
                "same_verdict": 9,
                "flipped": 1,
            }
        ],
        "round_differences": [
            {"differs": True, "opposite": True},
            {"differs": True, "opposite": False},
            {"differs": False, "opposite": False},
        ],
    }
    assert agreement.summary(views) == [
        "Visual round",
        "  panel: 75% mean agreement on 2 pairs judged by 2 or more voters; split on 1",
        "  Ada and Bo: same verdict on 3 of 4 shared pairs (75%), opposite on 1",
        "  Ada: 120 votes, median 8.5 s, 3 faster than the low-effort limit",
        "  Ada on repeats: same verdict on 9 of 10, flipped on 1",
        "Motion round",
        "  panel: no pair judged by 2 or more voters yet",
        "Visual against motion, same voter and pair: verdict differs on 2 of 3, opposite on 1",
    ]


def test_calibration_covers_both_rounds_unless_told_otherwise():
    parser = build_parser()
    assert parser.parse_args(["calibrate", "--ids", "1-14"]).round == "both"
    assert parser.parse_args(["calibrate", "--ids", "1-14", "--round", "motion"]).round == "motion"
