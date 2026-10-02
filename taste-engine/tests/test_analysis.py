from PIL import Image, ImageDraw

from taste_engine.analysis.layout import layout_features
from taste_engine.analysis.pixels import pixel_features
from taste_engine.settings import AnalysisSettings

CFG = AnalysisSettings()


def _page(tmp_path, background, ink, name):
    image = Image.new("RGB", (1440, 900), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 300, 1240, 600), fill=ink)  # a block covering about 27% of the page
    path = tmp_path / name
    image.save(path)
    return path


def test_whitespace_is_relative_to_the_background(tmp_path):
    light = pixel_features(_page(tmp_path, "#ffffff", "#111111", "light.png"), CFG)
    dark = pixel_features(_page(tmp_path, "#0a0a0a", "#f5f5f5", "dark.png"), CFG)
    for features in (light, dark):
        assert 0.70 < features["whitespace_ratio"] < 0.76  # black ink is not whitespace
    assert light["background_luminance"] > 0.9 > dark["background_luminance"]


def test_palette_and_contrast(tmp_path):
    features = pixel_features(_page(tmp_path, "#ffffff", "#c2410c", "accent.png"), CFG)
    assert features["palette"][0]["hex"].startswith("#f")
    assert features["colourfulness"] > 0
    assert features["edge_density"] > 0


def _box(x, w, text=0, size=16, y=100, h=100, tag="p"):
    return {"x": x, "y": y, "w": w, "h": h, "text_length": text, "font_size": size, "tag": tag}


def test_wrappers_are_ignored_and_centred_content_is_balanced():
    dom = {
        "viewport": {"width": 1440, "height": 900},
        "page_height": 3600,
        "elements": [
            _box(0, 1440, y=0, h=900, tag="section"),  # a wrapper: ignored
            _box(420, 600, text=40, size=96, tag="h1"),  # centred headline: half on each side
        ],
    }
    features = layout_features(dom, {}, CFG)
    assert features["layout_imbalance"] == 0
    assert features["page_height_screens"] == 4.0
    assert features["text_quadrants"][1] == 1.0  # all text sits in the top-middle cell
    assert features["media_coverage"] == 0


def test_left_aligned_content_reads_as_imbalanced():
    dom = {
        "viewport": {"width": 1440, "height": 900},
        "page_height": 900,
        "elements": [_box(80, 400, text=40, tag="h1"), _box(80, 300, tag="img")],
    }
    features = layout_features(dom, {}, CFG)
    assert features["layout_imbalance"] == 1.0
    assert features["media_coverage"] == round(300 * 100 / (1440 * 900), 4)


def test_missing_inputs_are_none_not_zero():
    dom = {"viewport": {"width": 1440, "height": 900}, "page_height": 900, "elements": []}
    features = layout_features(dom, {}, CFG)
    assert features["layout_imbalance"] is None
    assert features["display_ratio"] is None
    assert features["spacing_regularity"] is None


def test_type_scale_and_spacing_regularity():
    dom = {
        "viewport": {"width": 1440, "height": 900},
        "page_height": 900,
        "elements": [_box(100, 300, 10, 96), _box(100, 300, 50, 16), _box(100, 300, 40, 16)],
    }
    tokens = {
        "spacing": [{"px": 16, "count": 6}, {"px": 13, "count": 2}],
        "fonts": [{"family": "A"}],
    }
    features = layout_features(dom, tokens, CFG)
    assert features["display_ratio"] == 6.0
    assert features["spacing_regularity"] == 0.75
    assert features["font_families"] == 1
