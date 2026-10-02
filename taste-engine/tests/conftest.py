import functools
import http.server
import threading
from pathlib import Path

import pytest

from taste_engine.settings import CaptureSettings, ReelSettings, Settings

FIXTURES = Path(__file__).parent / "fixtures"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def fixture_site_url():
    handler = functools.partial(_QuietHandler, directory=str(FIXTURES / "site"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/index.html"
    server.shutdown()


@pytest.fixture
def fast_settings(tmp_path):
    """Real capture behaviour with shorter waits, writing into a temporary data folder."""
    return Settings(
        data_dir=tmp_path,
        capture=CaptureSettings(
            settle_max_s=6.0,
            screen_settle_s=0.4,
            jank_test_s=0.6,
            reel=ReelSettings(
                intro_s=1.0,
                screens=2,
                hover_targets=2,
                pause_per_screen_s=0.2,
                hover_dwell_s=0.2,
                menu_dwell_s=0.4,
            ),
        ),
    )
