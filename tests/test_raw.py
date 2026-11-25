"""Germany layer, raw sources: Zensus token safety and raw parsing as delivered."""

import io
import json
import zipfile

import pytest

from src.ingestion import static_sources
from src.ingestion.contract import ZENSUS_CONTRACT
from src.ingestion.static_raw_load import (
    ZENSUS_CSV_COLUMNS,
    parse_zensus_flat_csv,
)


FAKE_TOKEN = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------------------
# Token safety: the Zensus API echoes the token in "Username".
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str, body: bytes):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.content = body

    def json(self):
        return json.loads(self.content)


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def _zip_with_csv(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("1000A-1003_1_de_flat.csv", text)
    return buffer.getvalue()


def test_zensus_token_never_leaves_the_request_header() -> None:
    # Observed on 9 Nov 2026: the Zensus API echoes the token in plain text in
    # the "Username" field of its JSON responses.
    extract = ZENSUS_CONTRACT.extracts[0]

    # Sent only as a header: not in the URL, not in the form data.
    csv_text = ";".join(ZENSUS_CSV_COLUMNS) + "\n"
    session = _FakeSession(_FakeResponse(200, "application/zip", _zip_with_csv(csv_text)))
    assert static_sources.download_zensus_extract(session, extract, FAKE_TOKEN) == csv_text.encode()
    (call,) = session.calls
    assert call["headers"]["username"] == FAKE_TOKEN
    assert FAKE_TOKEN not in call["url"] and FAKE_TOKEN not in json.dumps(call["data"])

    # Never in an error message, although the API response contains it.
    body = json.dumps({"Status": {"Code": 98, "Content": "Fehler"}, "Username": FAKE_TOKEN})
    session = _FakeSession(_FakeResponse(200, "application/json", body.encode()))
    with pytest.raises(RuntimeError) as error:
        static_sources.download_zensus_extract(session, extract, FAKE_TOKEN)
    assert FAKE_TOKEN not in str(error.value) and "Fehler" in str(error.value)

    # Redaction also reaches nested fields and lists.
    nested = {"Parameter": {"username": FAKE_TOKEN, "password": "secret"},
              "List": [{"Username": FAKE_TOKEN, "Code": "x"}]}
    redacted = json.dumps(static_sources.redact_api_payload(nested))
    assert FAKE_TOKEN not in redacted and "secret" not in redacted and '"Code": "x"' in redacted


# ---------------------------------------------------------------------------
# Raw parsing keeps values as delivered.
# ---------------------------------------------------------------------------
def _flat_csv(*rows: list[str]) -> str:
    header = "﻿" + ";".join(ZENSUS_CSV_COLUMNS)
    return "\n".join([header, *(";".join(row) for row in rows)]) + "\n"


def _row(region: str, age: str, value: str) -> list[str]:
    return [
        "1000A", "Bevölkerung kompakt (Gebietsstand 15.05.2022)", "STAG",
        "Stichtag", "2022-05-15", "GEOGM4", "Gemeinden", region, "Name",
        "ALTKL1", "Alter (5 Altersklassen)", age, "label", value, "Anzahl",
        "PRS018", "Personen",
    ]


def test_parse_zensus_flat_csv_keeps_signs_and_leading_zeroes() -> None:
    text = _flat_csv(
        _row("010010000000", "ALT065BXXX", "17520"),
        _row("072325005130", "ALT065BXXX", "-"),
    )
    rows = list(parse_zensus_flat_csv(text))
    assert len(rows) == 2
    assert rows[0][7] == "010010000000"
    assert rows[0][13] == "17520"
    assert rows[1][13] == "-"
