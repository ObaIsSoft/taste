"""Repository rules that keep ghost code and hardcoding out of the package."""

import importlib
import pkgutil
import re
from pathlib import Path

import taste_engine

PACKAGE_DIR = Path(taste_engine.__file__).parent
SOURCES = sorted(PACKAGE_DIR.rglob("*.py"))

FORBIDDEN = {
    "absolute user path": re.compile(r"/Users/|/home/\w"),
    "working-directory relative path": re.compile(r"""["']\.\.?/"""),
}
MODEL_ID = re.compile(r"claude-(?:opus|sonnet|haiku|fable)-")


def test_every_module_imports():
    """A renamed setting or a missing optional dependency must fail here, not in production."""
    for info in pkgutil.walk_packages([str(PACKAGE_DIR)], prefix="taste_engine."):
        if info.name.endswith("__main__"):
            continue
        importlib.import_module(info.name)


def test_no_hardcoded_paths():
    offenders = [
        f"{path.relative_to(PACKAGE_DIR)}: {label}"
        for path in SOURCES
        for label, pattern in FORBIDDEN.items()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "resolve paths from settings instead: " + ", ".join(offenders)


def test_model_ids_only_in_settings():
    offenders = [
        str(path.relative_to(PACKAGE_DIR))
        for path in SOURCES
        if path.name != "settings.py" and MODEL_ID.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "model ids belong in settings.py: " + ", ".join(offenders)
