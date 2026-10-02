"""A stand-in for the Supabase client, shared by the API and UI tests."""

from postgrest.exceptions import APIError


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, _name):  # select, order, eq, in_ ... all chain
        return lambda *args, **kwargs: self

    def execute(self):
        return _Result(self._data)


class FakeSupabase:
    def __init__(self):
        self.calls = []
        self.rpc_results = {}
        self.tables = {
            "dimensions": [
                {"id": "typography", "label": "Typography", "round": "visual", "position": 1},
                {"id": "pacing", "label": "Pacing", "round": "motion", "position": 1},
            ],
            "voting_config": [{"min_reason_chars": 10, "max_dimensions": 3}],
            "voters": [{"name": "Ada"}],
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
        }
        self.storage = self

    def rpc(self, name, params):
        self.calls.append((name, params))
        result = self.rpc_results.get(name)
        if isinstance(result, APIError):
            raise result
        return _Query(result)

    def table(self, name):
        return _Query(self.tables[name])

    def from_(self, _bucket):
        return self

    def create_signed_urls(self, paths, _seconds):
        return [{"path": p, "signedURL": f"https://signed.test/{p}", "error": None} for p in paths]
