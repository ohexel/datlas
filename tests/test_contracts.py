"""Germany layer: contracts that hold across all themes.

- No source or generated data is tracked in Git (D8).
- The public map carries the attribution the licences and terms of use
  require, and loads only pinned, integrity-checked libraries without a
  basemap or key (D6).
"""

import re

import pytest

from src.export_germany_dashboard import DASHBOARD_SOURCE, PROJECT_ROOT
from src.ingestion.contract import GERMANY_RAW_ROOT


def _page() -> tuple[str, str]:
    html = (DASHBOARD_SOURCE / "index.html").read_text(encoding="utf-8")
    script = (DASHBOARD_SOURCE / "app.js").read_text(encoding="utf-8")
    return html, script


@pytest.mark.contract
def test_no_germany_data_in_git() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"(?m)^data/$", gitignore)
    assert GERMANY_RAW_ROOT.parts[0] == "data"  # sources are downloaded under data/
    ignore = (DASHBOARD_SOURCE / "data" / ".gitignore").read_text(encoding="utf-8")
    assert ignore.splitlines() == ["*", "!.gitignore"]  # map exports are generated


@pytest.mark.contract
def test_public_page_shows_the_required_attribution() -> None:
    html, script = _page()
    # BKG VG250 and Zensus 2022: dl-de/by-2-0 with the prescribed wording.
    assert "© GeoBasis-DE / BKG 2022 (Daten verändert)" in html
    assert "https://www.bkg.bund.de" in html
    assert "Zensus 2022, © Statistische Ämter des Bundes und der Länder" in html
    assert html.count("dl-de/by-2-0") >= 2
    # DWD forecast.
    assert "Deutscher Wetterdienst" in html
    # BA terms of use: name the source, link its statistics homepage, mark
    # own calculations as such.
    assert "Statistik der Bundesagentur für Arbeit" in html
    assert 'href="https://statistik.arbeitsagentur.de/"' in html
    for product in ("Gemeindedaten", "Regionalreport über Beschäftigte",
                    "Beschäftigte nach Wirtschaftszweigen"):
        assert product in html
    assert "eigene Berechnung" in html and "eigene Berechnung" in script


@pytest.mark.contract
def test_map_libraries_are_pinned_and_there_is_no_basemap() -> None:
    html, script = _page()
    external = re.findall(r'(?:src|href)="(https://cdn[^"]+)"', html)
    assert external, "MapLibre and PMTiles are loaded from a CDN"
    for url in external:
        assert re.search(r"@\d+\.\d+\.\d+/", url), url
    for tag in re.findall(r"<(?:script|link)[^>]+https://cdn[^>]+>", html, flags=re.S):
        assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, tag
    page = (html + script).lower()
    for word in ("api_key", "apikey", "access_token", "mapbox://", "maptiler",
                 "tiles.openstreetmap", "{z}/{x}/{y}", "glyphs", "sprite"):
        assert word not in page, word
