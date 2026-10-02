import json
from types import SimpleNamespace

from PIL import Image

from taste_engine import describe
from taste_engine.settings import ClaudeSettings

CFG = ClaudeSettings()


def test_request_is_factual_structured_and_downscaled(tmp_path):
    hero = tmp_path / "screen-1.jpg"
    Image.new("RGB", (1440, 900), "white").save(hero)
    request = describe.build_request("0001-original", hero, CFG)
    params = request["params"]

    assert request["custom_id"] == "0001-original"
    assert params["model"] == CFG.describe_model
    assert params["output_config"]["format"]["schema"] is describe.SCHEMA
    assert params["output_config"]["effort"] == CFG.describe_effort
    assert "Never judge quality" in params["system"]
    image = params["messages"][0]["content"][0]
    assert image["source"]["media_type"] == "image/jpeg"


def test_schema_has_no_place_for_a_verdict():
    fields = set(describe.SCHEMA["properties"])
    assert not fields & {"quality", "score", "rating", "taste", "verdict", "rationale"}
    assert set(describe.SCHEMA["required"]) == fields


def test_chunks_respect_the_size_limit():
    requests = [{"custom_id": str(i), "params": {"pad": "x" * 100}} for i in range(10)]
    chunks = describe.chunk_requests(requests, max_bytes=400)
    assert sum(len(c) for c in chunks) == 10
    assert all(len(json.dumps(c)) <= 400 + 150 for c in chunks)


def _result(stop_reason="end_turn", text='{"density": "sparse"}', kind="succeeded"):
    message = SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)], model="m"
    )
    return SimpleNamespace(
        custom_id="0001-original", result=SimpleNamespace(type=kind, message=message)
    )


def test_parse_result_outcomes():
    assert describe.parse_result(_result()) == ({"density": "sparse"}, None)
    assert describe.parse_result(_result(stop_reason="refusal")) == (None, "refusal")
    assert describe.parse_result(_result(kind="errored")) == (None, "errored")
