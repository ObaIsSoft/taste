from types import SimpleNamespace

from PIL import Image

from taste_engine import describe
from taste_engine.settings import ClaudeSettings

CFG = ClaudeSettings()


def test_request_sends_every_still_and_the_domain(tmp_path):
    stills = []
    for i in range(1, 5):
        still = tmp_path / f"screen-{i}.jpg"
        Image.new("RGB", (1440, 900), "white").save(still)
        stills.append(still)
    request = describe.build_request("0001-original", stills, "studio.test", CFG)
    params = request["params"]
    content = params["messages"][0]["content"]

    assert request["custom_id"] == "0001-original"
    assert params["model"] == CFG.describe_model
    assert params["output_config"]["format"]["schema"] is describe.SCHEMA
    assert "Never judge quality" in params["system"]
    assert [block["type"] for block in content] == ["image"] * 4 + ["text"]
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert "studio.test" in content[-1]["text"]


def test_only_a_live_uncovered_page_is_clean():
    assert describe.is_clean(
        {"obstruction": "none", "page_state": "live_site", "density": "sparse"}
    )
    assert not describe.is_clean(
        {"obstruction": "newsletter_or_offer_popup", "page_state": "live_site"}
    )
    assert not describe.is_clean({"obstruction": "none", "page_state": "closed_or_unavailable"})
    assert not describe.is_clean(None)


def test_schema_has_no_place_for_a_verdict():
    fields = set(describe.SCHEMA["properties"])
    assert not fields & {"quality", "score", "rating", "taste", "verdict", "rationale"}
    assert set(describe.SCHEMA["required"]) == fields


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
