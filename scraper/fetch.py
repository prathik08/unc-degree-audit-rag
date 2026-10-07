"""Fetches catalog.unc.edu pages, caching raw HTML to data/raw/ so repeated
runs during development don't re-hit the server."""

import hashlib
from pathlib import Path

import requests

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
USER_AGENT = "Mozilla/5.0 (student project; degree-audit-rag)"


def fetch(url: str) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    if cache_path.exists():
        return cache_path.read_text()

    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    cache_path.write_text(response.text)
    return response.text
