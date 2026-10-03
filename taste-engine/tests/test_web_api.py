"""The voting API's contract, with Supabase replaced by a fake."""

import importlib.util
from pathlib import Path

import pytest
from fakes import FakeSupabase
from postgrest.exceptions import APIError

API_PATH = Path(__file__).parent.parent / "web" / "api" / "index.py"


@pytest.fixture
def api(monkeypatch):
    spec = importlib.util.spec_from_file_location("voting_api", API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fake = FakeSupabase()
    monkeypatch.setattr(module, "db", lambda: fake)
    monkeypatch.setenv("TASTE_STORAGE_BUCKET", "captures")
    client = module.app.test_client()
    client.environ_base["HTTP_X_INVITE_CODE"] = "code-ada"
    return client, fake


def test_requests_without_an_invite_code_are_refused(api):
    client, _ = api
    response = client.get("/api/progress", headers={"X-Invite-Code": ""})
    assert response.status_code == 401


def test_pair_sends_signed_media_and_no_capture_ids(api):
    client, fake = api
    fake.rpc_results["next_pair"] = {
        "token": "t-1",
        "left_capture": "0002-original",
        "right_capture": "0001-original",
        "reason_requested": True,
    }
    body = client.get("/api/pair?round=motion").get_json()

    assert body["token"] == "t-1" and body["reason_requested"] is True
    assert body["left"]["stills"] == ["https://signed.test/0002-original/screen-1.jpg"]
    assert body["left"]["live_url"] == "https://b.test/home"
    assert body["right"]["reel"] == "https://signed.test/0001-original/reel.mp4"
    assert "0001-original" not in str({k: v for k, v in body.items() if k != "right"})
    assert fake.calls[-1] == ("next_pair", {"p_code": "code-ada", "p_round": "motion"})


def test_visual_rounds_do_not_sign_reels(api):
    client, fake = api
    fake.rpc_results["next_pair"] = {
        "token": "t-2",
        "left_capture": "0001-original",
        "right_capture": "0002-original",
        "reason_requested": False,
    }
    assert client.get("/api/pair?round=visual").get_json()["left"]["reel"] is None


def test_database_rule_errors_become_client_errors(api):
    client, fake = api
    fake.rpc_results["cast_vote"] = APIError(
        {"code": "22023", "message": "pick at least one dimension that decided it"}
    )
    response = client.post("/api/vote", json={"token": "t-1", "outcome": "left", "dimensions": []})
    assert response.status_code == 400
    assert response.get_json()["error"] == "pick at least one dimension that decided it"

    fake.rpc_results["cast_vote"] = APIError({"code": "23505", "message": "already voted"})
    assert client.post("/api/vote", json={"token": "t-1", "outcome": "left"}).status_code == 409

    fake.rpc_results["cast_vote"] = APIError({"code": "XX000", "message": "internal detail"})
    response = client.post("/api/vote", json={"token": "t-1", "outcome": "left"})
    assert response.status_code == 500 and "internal detail" not in response.get_data(as_text=True)


def test_vote_input_is_type_checked_before_the_database(api):
    client, fake = api
    assert (
        client.post("/api/vote", json={"token": "t", "dimensions": "typography"}).status_code == 400
    )
    assert client.post("/api/vote", data="not json").status_code == 400
    assert client.post("/api/event", json={"token": "t", "kind": "hack"}).status_code == 400
    assert not fake.calls


def test_config_comes_from_the_database(api):
    client, fake = api
    body = client.get("/api/config").get_json()
    assert body["min_reason_chars"] == 10 and body["max_dimensions"] == 3
    assert [d["id"] for d in body["dimensions"]["motion"]] == ["pacing"]


def test_a_vote_too_fast_to_be_real_is_429(api):
    client, fake = api
    fake.rpc_results["cast_vote"] = APIError(
        {"code": "P0429", "message": "take a moment to look at both sites"}
    )
    response = client.post("/api/vote", json={"token": "t-1", "outcome": "cant_decide"})
    assert response.status_code == 429


def test_own_words_pass_through_and_must_be_words(api):
    client, fake = api
    fake.rpc_results["cast_vote"] = 7
    body = {"token": "t-1", "outcome": "left", "terms": ["editorial pacing"]}
    assert client.post("/api/vote", json=body).status_code == 200
    assert fake.calls[-1][1]["p_terms"] == ["editorial pacing"]
    body["terms"] = "editorial pacing"
    assert client.post("/api/vote", json=body).status_code == 400


def test_terms_are_the_voters_own(api):
    client, fake = api
    fake.rpc_results["voter_terms"] = [{"term": "editorial pacing", "uses": 2}]
    assert client.get("/api/terms?round=visual").get_json() == {"terms": ["editorial pacing"]}
    assert fake.calls[-1] == ("voter_terms", {"p_code": "code-ada", "p_round": "visual"})
