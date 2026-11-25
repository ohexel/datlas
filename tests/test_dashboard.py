"""Germany map: export helper for maxima and minima, local Range server.
(Page contracts are in test_contracts.py.)"""

from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from src.export_germany_dashboard import (
    EXPECTED_LEAD_COUNT,
    SUMMARY_FIELDS,
    summary_records,
)
from src.preview_server import RangeRequestHandler


# ---------------------------------------------------------------------------
# Values export: maxima and minima for the Höchst-/Tiefstwerte switch
# ---------------------------------------------------------------------------


def test_summary_records_keeps_maxima_and_minima_apart() -> None:
    pairs = []
    for index, _field in enumerate(SUMMARY_FIELDS):
        pairs += [float(index), index]  # value, lead hour
    rows = [("01001", "Flensburg", "01", EXPECTED_LEAD_COUNT, *pairs, 95015, 1)]
    record = summary_records(rows)["01001"]
    for index, field in enumerate(SUMMARY_FIELDS):
        assert record[field] == float(index)
        assert record[field.removesuffix("_c") + "_lead_hour"] == index
    assert record["min_temperature_area_weighted_c"] == 4.0
    assert (record["population_total"], record["gemeinde_count"]) == (95015, 1)


# ---------------------------------------------------------------------------
# Range parsing and the local preview server
# ---------------------------------------------------------------------------


def test_preview_server_answers_range_requests(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 40
    (tmp_path / "tiles.pmtiles").write_bytes(payload)
    class QuietHandler(RangeRequestHandler):
        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(tmp_path))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/tiles.pmtiles"
    try:
        request = urllib.request.Request(base, headers={"Range": "bytes=100-163"})
        with urllib.request.urlopen(request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == f"bytes 100-163/{len(payload)}"
            assert response.read() == payload[100:164]

        request = urllib.request.Request(base, headers={"Range": "bytes=-16"})
        with urllib.request.urlopen(request) as response:
            assert response.read() == payload[-16:]

        with urllib.request.urlopen(base) as response:  # no Range: whole file
            assert response.status == 200
            assert response.read() == payload

        request = urllib.request.Request(base, headers={"Range": f"bytes={len(payload)}-"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 416
    finally:
        server.shutdown()
        server.server_close()
