from taste_engine import calibration


def _vectors():
    # a cluster of near-identical sites, plus a few that each differ on something
    vectors = {
        f"{i:04d}-original": {"luminance": 0.5, "edges": 0.2 + i / 1000} for i in range(1, 9)
    }
    vectors["0100-original"] = {"luminance": 0.05, "edges": 0.2}  # very dark
    vectors["0101-original"] = {"luminance": 0.95, "edges": 0.2}  # very light
    vectors["0102-original"] = {"luminance": 0.5, "edges": 0.9}  # very busy
    return vectors


def test_the_pick_spans_the_extremes_and_is_reproducible():
    picked = calibration.pick(_vectors(), 4)
    assert len(set(picked)) == 4
    assert {"0100-original", "0101-original", "0102-original"} <= set(picked)
    assert picked == calibration.pick(_vectors(), 4)


def test_too_few_candidates_is_an_error():
    try:
        calibration.pick(_vectors(), 50)
    except ValueError as error:
        assert "only 11 candidates" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_every_numeric_feature_takes_part():
    flat = calibration._numbers({"a": 1, "b": {"c": 2.5, "d": True}, "e": [0.1, 0.2], "f": "text"})
    assert flat == {".a": 1.0, ".b.c": 2.5, ".b.d": 1.0, ".e[0]": 0.1, ".e[1]": 0.2}
