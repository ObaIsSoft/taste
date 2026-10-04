"""A stand-in for the Supabase client, shared by the API and UI tests.

Filters really filter, and an unknown query method fails, so a query the real
client would reject cannot pass here unnoticed.
"""

from postgrest.exceptions import APIError


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, _columns):
        return self

    def order(self, _column, **_options):
        return self

    def eq(self, column, value):
        self._rows = [row for row in self._rows if row.get(column) == value]
        return self

    def in_(self, column, values):
        self._rows = [row for row in self._rows if row.get(column) in values]
        return self

    def range(self, start, end):
        self._rows = self._rows[start : end + 1]
        return self

    def execute(self):
        return _Result(self._rows)


class _Call:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _Result(self._data)


class FakeSupabase:
    def __init__(self):
        self.calls = []
        self.rpc_results = {
            "voting_facts": {
                "min_reason_chars": 10,
                "max_dimensions": 3,
                "max_own_terms": 5,
                "max_term_chars": 40,
                "idle_cutoff_seconds": 120,
                "rounds": {
                    "visual": {"target_votes": 200, "calibration_pairs": 91, "repeats": 10},
                    "motion": {"target_votes": 100, "calibration_pairs": 28, "repeats": 10},
                },
            }
        }
        self.tables = {
            "dimensions": [
                {
                    "id": "typography",
                    "label": "Typography",
                    "description": "Is the hierarchy clear?",
                    "round": "visual",
                    "position": 1,
                },
                {
                    "id": "pacing",
                    "label": "Pacing",
                    "description": "Is the timing deliberate?",
                    "round": "motion",
                    "position": 1,
                },
            ],
            "voters": [{"name": "Ada", "invite_code": "code-ada"}],
            "captures": [
                {
                    "id": "0001-original",
                    "stills": ["0001-original/screen-1.jpg"],
                    "reel_path": "0001-original/reel.mp4",
                    "final_url": None,
                    "sites": {"url": "https://a.test/"},
                },
                {
                    "id": "0002-original",
                    "stills": ["0002-original/screen-1.jpg"],
                    "reel_path": None,
                    "final_url": "https://b.test/home",
                    "sites": {"url": "https://b.test/"},
                },
            ],
            # the published versions of each capture's media; served pairs pin one
            "capture_media": [
                {
                    "capture_id": "0001-original",
                    "media_id": "m1-0001-original",
                    "stills": ["0001-original/screen-1.jpg"],
                    "reel_path": "0001-original/reel.mp4",
                },
                {
                    "capture_id": "0002-original",
                    "media_id": "m1-0002-original",
                    "stills": ["0002-original/screen-1.jpg"],
                    "reel_path": None,
                },
            ],
        }
        self.storage = self

    def rpc(self, name, params):
        self.calls.append((name, params))
        result = self.rpc_results.get(name)
        if isinstance(result, APIError):
            raise result
        return _Call(result)

    def table(self, name):
        return _Query(self.tables[name])

    def from_(self, _bucket):
        return self

    def create_signed_urls(self, paths, _seconds):
        return [{"path": p, "signedURL": f"https://signed.test/{p}", "error": None} for p in paths]
