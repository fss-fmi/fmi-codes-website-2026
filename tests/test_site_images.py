"""Site images: size budgets, and every image is referenced and every reference exists."""

import gzip
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
SRC = ROOT / "frontend" / "src"

RASTER = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".avif"}
RASTER_BUDGET = 100 * 1024
SVG_GZIP_BUDGET = 128 * 1024

LITERAL_PATH = re.compile(r"""["'(](/[\w\-./]+\.(?:svg|webp|png|jpe?g|gif|avif))["')]""")
LOGO_FILE = re.compile(r"file: '([^']+)'")


def _images():
    return sorted(
        p for p in PUBLIC.rglob("*") if p.is_file() and p.suffix.lower() in RASTER | {".svg"}
    )


def _public(url_path):
    return PUBLIC / url_path.lstrip("/")


def _literal_refs():
    sources = [ROOT / "frontend" / "index.html"]
    sources += [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]
    refs = set()
    for path in sources:
        refs.update(LITERAL_PATH.findall(path.read_text(encoding="utf-8")))
    return refs


def _mentor_refs():
    seeds = ROOT / "backend" / "database" / "seeds" / "mentors.json"
    mentors = json.loads(seeds.read_text(encoding="utf-8"))
    return {m["picture_url"] for m in mentors if m.get("picture_url")}


def _logo_refs():
    home_data = (SRC / "components" / "home" / "homeData.ts").read_text(encoding="utf-8")
    return {f"/companyLogos/{name}" for name in LOGO_FILE.findall(home_data)}


@pytest.mark.parametrize("path", _images(), ids=lambda p: p.relative_to(PUBLIC).as_posix())
def test_image_within_budget(path):
    data = path.read_bytes()
    if path.suffix.lower() == ".svg":
        size = len(gzip.compress(data, compresslevel=9))
        assert size <= SVG_GZIP_BUDGET, f"{size} bytes gzipped; run SVGO"
    else:
        assert len(data) <= RASTER_BUDGET, f"{len(data)} bytes; resize it or convert to WebP"


def test_mentor_seed_pictures_exist():
    missing = sorted(u for u in _mentor_refs() if not _public(u).is_file())
    assert not missing


def test_mentor_pictures_are_served_by_the_frontend():
    assert all(u.startswith("/mentorPictures/") for u in _mentor_refs())


def test_logos_exist():
    missing = sorted(u for u in _logo_refs() if not _public(u).is_file())
    assert not missing


def test_literal_image_paths_exist():
    missing = sorted(u for u in _literal_refs() if not _public(u).is_file())
    assert not missing


def test_every_image_is_used():
    used = {_public(u).resolve() for u in _literal_refs() | _mentor_refs() | _logo_refs()}
    unused = [p.relative_to(PUBLIC).as_posix() for p in _images() if p.resolve() not in used]
    assert not unused, "delete unused images instead of shipping them"
