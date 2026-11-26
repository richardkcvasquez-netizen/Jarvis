"""The built-in Sentinel Ring look (docs/looks.md, ADR-0048)."""

from __future__ import annotations

from dodaios.ui.looks import loader


def _folder():
    return loader.builtin_root() / "sentinel-ring"


def test_sentinel_ring_is_a_valid_builtin_look_credited_to_its_author() -> None:
    manifest = loader.read_manifest(_folder(), builtin=True)
    assert manifest.builtin
    assert manifest.name == "Sentinel Ring"
    assert manifest.author == "Richard Vasquez"
    assert manifest.license == "Apache-2.0"


def test_sentinel_ring_loads_nothing_from_the_network_and_reports_ready() -> None:
    folder = _folder()
    for path in folder.iterdir():
        if path.suffix in {".html", ".js", ".css"}:
            text = path.read_text(encoding="utf-8")
            assert "http://" not in text and "https://" not in text, path.name
    html = (folder / "index.html").read_text(encoding="utf-8")
    assert "look:ready" in html


def test_sentinel_ring_is_listed_among_the_looks(tmp_path) -> None:
    ids = [look.id for look in loader.list_looks(data_dir=tmp_path)]
    assert "sentinel-ring" in ids
