#!/usr/bin/env python3
"""
Download IBGE municipal mesh shapefiles, convert to GeoJSON, save to data/latest/.

Change detection strategy (cheapest-first):
  1. HTTP HEAD → compare ETag + Last-Modified + Content-Length with stored values.
     Skip download entirely when headers match and the GeoJSON already exists.
  2. SHA256 of the downloaded ZIP → skip conversion when content is identical
     (guards against servers that don't serve reliable cache headers).

Stored state lives in data/checksums.json so subsequent runs are incremental.
"""

import hashlib
import json
import logging
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Configuration ──────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "latest"
CHECKSUMS_FILE = REPO_ROOT / "data" / "checksums.json"

FTP_BASE = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio"
    "/malhas_territoriais/malhas_municipais"
)

# Types available at Brazil (national) level
BR_TYPES = [
    "Municipios",
    "UF",
    "Regioes",
    "RG_Imediatas",
    "RG_Intermediarias",
]

# Types available per state
UF_TYPES = [
    "Municipios",
    "UF",
    "RG_Imediatas",
    "RG_Intermediarias",
]

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── HTTP session with automatic retries ───────────────────────────────────────


def _make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "br-maps-bot/1.0 (+https://github.com)"
    return session


SESSION = _make_session()

# ── Year detection ────────────────────────────────────────────────────────────


def detect_year() -> int:
    """Return the most recent year available on the IBGE FTP server."""
    import datetime

    current_year = datetime.datetime.utcnow().year

    # Try fetching the FTP index page which lists municipio_YYYY directories.
    try:
        resp = SESSION.get(f"{FTP_BASE}/", timeout=30)
        resp.raise_for_status()
        years = sorted(
            {int(y) for y in re.findall(r"municipio_(\d{4})", resp.text)},
            reverse=True,
        )
        if years:
            log.info("Detected year %s from FTP index (available: %s)", years[0], years)
            return years[0]
    except Exception as exc:
        log.warning("FTP index unavailable (%s); falling back to probing …", exc)

    # Fallback: probe recent years with a known URL pattern.
    for year in range(current_year, current_year - 5, -1):
        probe = f"{FTP_BASE}/municipio_{year}/Brasil/BR_UF_{year}.zip"
        try:
            resp = SESSION.head(probe, timeout=15)
            if resp.status_code == 200:
                log.info("Probed and confirmed year: %s", year)
                return year
        except Exception:
            pass

    raise RuntimeError("Could not determine the latest data year from IBGE FTP")


# ── URL list builder ──────────────────────────────────────────────────────────


def build_urls(year: int) -> list[tuple[str, str]]:
    """Return [(url, output_stem), …] for every file to process."""
    entries: list[tuple[str, str]] = []

    # Brazil-level files
    for t in BR_TYPES:
        url = f"{FTP_BASE}/municipio_{year}/Brasil/BR_{t}_{year}.zip"
        entries.append((url, f"BR_{t}"))

    # State-level files (27 UFs × 4 types = 108 files)
    for uf in UFS:
        for t in UF_TYPES:
            url = f"{FTP_BASE}/municipio_{year}/UFs/{uf}/{uf}_{t}_{year}.zip"
            entries.append((url, f"{uf}_{t}"))

    return entries


# ── Checksum helpers ──────────────────────────────────────────────────────────


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_checksums() -> dict:
    if CHECKSUMS_FILE.exists():
        return json.loads(CHECKSUMS_FILE.read_text())
    return {}


def save_checksums(data: dict) -> None:
    CHECKSUMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUMS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ── Change detection ──────────────────────────────────────────────────────────


def head_headers(url: str) -> dict:
    """Return cache-relevant headers from a HEAD request (cheap, no body)."""
    try:
        resp = SESSION.head(url, timeout=20, allow_redirects=True)
        if resp.status_code == 404:
            return {"_404": True}
        resp.raise_for_status()
        return {
            "etag": resp.headers.get("ETag", ""),
            "last-modified": resp.headers.get("Last-Modified", ""),
            "content-length": resp.headers.get("Content-Length", ""),
        }
    except requests.RequestException as exc:
        log.debug("HEAD %s failed: %s", url, exc)
        return {}


def headers_match(remote: dict, stored: dict) -> bool:
    """True when remote cache headers strongly indicate no change."""
    # ETag is the most reliable indicator.
    if remote.get("etag") and remote["etag"] == stored.get("etag"):
        return True
    # Last-Modified + Content-Length together are a reliable proxy.
    if (
        remote.get("last-modified")
        and remote["last-modified"] == stored.get("last-modified")
        and remote.get("content-length")
        and remote["content-length"] == stored.get("content-length")
    ):
        return True
    return False


# ── Download ──────────────────────────────────────────────────────────────────


def download(url: str, dest: Path) -> bool:
    """Stream-download url to dest. Returns False for 404, raises on other errors."""
    resp = SESSION.get(url, stream=True, timeout=300)
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            fh.write(chunk)
    return True


# ── Shapefile → GeoJSON conversion ────────────────────────────────────────────


def convert(zip_path: Path, out_path: Path) -> None:
    """Extract the first .shp found in a ZIP archive and write GeoJSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmpdir)

        shp_files = list(Path(tmpdir).rglob("*.shp"))
        if not shp_files:
            raise FileNotFoundError(f"No .shp file found inside {zip_path.name}")

        if len(shp_files) > 1:
            log.warning(
                "Multiple .shp in %s; using %s", zip_path.name, shp_files[0].name
            )

        gdf = gpd.read_file(shp_files[0])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(out_path, driver="GeoJSON")
        log.info(
            "  saved → %s  (%d features)",
            out_path.relative_to(REPO_ROOT),
            len(gdf),
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    year = detect_year()
    log.info("Using year: %s", year)

    urls = build_urls(year)
    log.info("Total files to check: %d", len(urls))

    checksums = load_checksums()
    checksums_changed = False
    geojson_changed = False
    errors: list[tuple[str, str]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for url, stem in urls:
            zip_path = Path(tmpdir) / f"{stem}.zip"
            out_path = DATA_DIR / f"{stem}.geojson"
            stored = checksums.get(url, {})

            log.info("[%s]", stem)

            try:
                # 1. Cheap header check — avoids downloading unchanged files.
                remote_hdr = head_headers(url)

                if remote_hdr.get("_404"):
                    log.info("  404 — skipping")
                    continue

                if stored and out_path.exists() and headers_match(remote_hdr, stored):
                    log.info("  unchanged (headers match)")
                    continue

                # 2. Download the ZIP.
                log.info("  downloading …")
                if not download(url, zip_path):
                    log.warning("  404 on GET — skipping")
                    continue

                # 3. SHA256 check — guards against unreliable cache headers.
                new_sha256 = sha256_of(zip_path)
                if new_sha256 == stored.get("sha256") and out_path.exists():
                    log.info("  SHA256 unchanged — updating metadata only")
                    checksums[url] = {**remote_hdr, "sha256": new_sha256}
                    checksums_changed = True
                    continue

                # 4. Convert shapefile to GeoJSON.
                log.info("  converting shapefile → GeoJSON …")
                convert(zip_path, out_path)
                checksums[url] = {**remote_hdr, "sha256": new_sha256}
                checksums_changed = True
                geojson_changed = True

            except Exception as exc:
                log.error("  ERROR: %s", exc)
                errors.append((stem, str(exc)))

    if checksums_changed:
        save_checksums(checksums)
        log.info("Checksums saved to %s", CHECKSUMS_FILE.relative_to(REPO_ROOT))

    log.info(
        "Done — GeoJSON updated: %s | Errors: %d",
        geojson_changed,
        len(errors),
    )

    if errors:
        log.error("Failed files (%d):", len(errors))
        for stem, msg in errors:
            log.error("  %s: %s", stem, msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
