from types import SimpleNamespace

import pytest

from taste_engine import cli
from taste_engine.cli import main, parse_ids, parse_variants
from taste_engine.schemas import Variant
from taste_engine.settings import Settings


def test_ids_and_variants_parse():
    assert parse_ids("1,4, 10-12") == [1, 4, 10, 11, 12]
    assert parse_variants("original, colour") == [Variant.ORIGINAL, Variant.COLOUR]


@pytest.mark.parametrize(
    "argv",
    [
        ["capture", "--ids", "abc"],
        ["capture", "--ids", "1-2-3"],
        ["capture", "--ids", "1", "--variants", "bogus"],
    ],
)
def test_bad_input_is_a_usage_error_not_a_traceback(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2
    assert "invalid" in capsys.readouterr().err


def test_an_id_missing_from_the_manifest_is_a_clean_error(caplog):
    assert main(["capture", "--ids", "99999"]) == 2
    assert "ids not in manifest: [99999]" in caplog.text


class _VoterTable:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return self

    def select(self, _columns):
        return self

    def order(self, _column):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def test_voters_list_prints_links_or_codes(monkeypatch, capsys):
    rows = [
        {"name": "Ada", "invite_code": "abc", "active": True, "created_at": "2026-10-01"},
        {"name": "Bo", "invite_code": "def", "active": False, "created_at": "2026-10-02"},
    ]
    monkeypatch.setattr(cli.db, "connect", lambda _settings: _VoterTable(rows))
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(voting_url="https://votes.test"))
    assert main(["voters", "list"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Ada: https://votes.test/#invite=abc",
        "Bo (inactive): https://votes.test/#invite=def",
    ]

    monkeypatch.setattr(cli, "get_settings", lambda: Settings(voting_url=None))
    main(["voters", "list"])
    out = capsys.readouterr().out
    assert "Ada: abc" in out and "TASTE_VOTING_URL" in out


class _Updates:
    """Records update calls; rows match when the filtered value is in ``existing``."""

    def __init__(self, existing):
        self.existing, self.updates = set(existing), []

    def table(self, name):
        self.name = name
        return self

    def update(self, values):
        self.values = values
        return self

    def eq(self, column, value):
        self.match = value
        return self

    def execute(self):
        hit = self.match in self.existing
        if hit:
            self.updates.append((self.name, self.match, self.values))
        return SimpleNamespace(data=[{"id": self.match}] if hit else [])


def test_captures_exclude_keeps_them_out_with_a_reason(monkeypatch, capsys):
    fake = _Updates({"0234-original", "0852-original"})
    monkeypatch.setattr(cli.db, "connect", lambda _settings: fake)
    argv = ["captures", "exclude", "0234-original", "0852-original", "--reason", "offer pop-up"]
    assert main(argv) == 0
    assert fake.updates == [
        ("captures", "0234-original", {"in_pool": False, "qa_note": "offer pop-up"}),
        ("captures", "0852-original", {"in_pool": False, "qa_note": "offer pop-up"}),
    ]
    assert main(["captures", "exclude", "9999-original", "--reason", "x"]) == 1


def test_voters_disable(monkeypatch):
    fake = _Updates({"Frida"})
    monkeypatch.setattr(cli.db, "connect", lambda _settings: fake)
    assert main(["voters", "disable", "Frida"]) == 0
    assert fake.updates == [("voters", "Frida", {"active": False})]
    assert main(["voters", "disable", "Nobody"]) == 1


def test_describe_without_an_api_key_is_a_clear_error(monkeypatch, caplog):
    settings = Settings()
    settings.anthropic_api_key = None
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert main(["describe", "--ids", "1"]) == 1
    assert "ANTHROPIC_API_KEY" in caplog.text
