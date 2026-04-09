#!/usr/bin/env python3
"""
Crawl doctor listings from Vinmec chuyên gia y tế.

Website analysis (Step 1):
- Doctor cards are present in the static HTML (e.g. "Đỗ Tất Cường" in
  ul#doctor-list). Use requests + BeautifulSoup on each list URL.
- Pagination: page 1 is /vie/chuyen-gia-y-te/, page N>=2 is
  /vie/chuyen-gia-y-te/page_N.
- POST /api/v3/doctor returns JSON with HTML fragments, but those fragments omit
  part of the degree line (e.g. ", Bác sĩ") compared to the static pages, so
  this script GETs static list pages for extraction and uses the API only to read
  pageCount/total for pagination.

Usage:
  pip install -r requirements.txt
  python crawl_vinmec_doctors.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.vinmec.com"
LIST_URL = f"{BASE}/vie/chuyen-gia-y-te/"
API_URL = f"{BASE}/api/v3/doctor"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi,en;q=0.9",
    "Referer": LIST_URL,
}

HEADERS_JSON = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": BASE,
}

HEADERS_HTML = {**HEADERS, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

REQUEST_DELAY_SEC = float(os.environ.get("VINMEC_REQUEST_DELAY_SEC", "2.0"))

OUT_JSON = Path("doctors_data.json")
IMAGES_DIR = Path("images")


def build_api_payload(page: int) -> dict:
    return {
        "hospitals": [],
        "specialties": [],
        "languages": [],
        "occupations": [],
        "educational_tiles": [],
        "education_levels": [],
        "name": "",
        "page": page,
        "locale": "vi",
        "rating": [],
    }


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Safe filename stem (no path separators); strip problematic characters."""
    s = name.strip()
    for ch in r'\/:*?"<>|':
        s = s.replace(ch, "_")
    s = re.sub(r"[\x00-\x1f]", "", s)
    # User asked to avoid problematic punctuation including dots in names
    s = s.replace(".", "_")
    s = re.sub(r"_+", "_", s).strip("._ ")
    if not s:
        s = "doctor"
    if len(s) > max_len:
        s = s[:max_len]
    return s


def extension_from_url(url: str) -> str:
    path = urlparse(url).path
    lower = path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lower.endswith(ext):
            return ext
    return ".jpg"


def normalize_space(text: str | None) -> str | None:
    if text is None:
        return None
    t = " ".join(text.split())
    return t if t else None


def cleanup_degree_title(text: str | None) -> str | None:
    """Normalize commas/spaces in degree lines from multi-line HTML."""
    if not text:
        return text
    t = re.sub(r"\s+,", ",", text)
    t = re.sub(r",\s*", ", ", t)
    return t.strip()


def parse_doctor_li(li) -> dict | None:
    name_el = li.select_one("a.list_name_doctor")
    if not name_el:
        return None
    full_name = normalize_space(name_el.get_text())
    if not full_name:
        return None

    deg = li.select_one(".icon_list_doctor.degree")
    spec = li.select_one(".icon_list_doctor.special")
    hosp = li.select_one(".icon_list_doctor.hospital")

    title = cleanup_degree_title(normalize_space(deg.get_text())) if deg else None
    specialty = normalize_space(spec.get_text()) if spec else None
    if hosp:
        link = hosp.select_one("a")
        workplace = normalize_space(link.get_text() if link else hosp.get_text())
    else:
        workplace = None

    img = li.select_one("a.thumbblock img") or li.select_one("img")
    src = img.get("src") if img else None
    profile_image_url = urljoin(BASE, src) if src else None

    return {
        "full_name": full_name,
        "title": title if title is not None else "",
        "specialty": specialty,
        "workplace": workplace,
        "profile_image_url": profile_image_url,
    }


def list_page_url(page: int) -> str:
    if page <= 1:
        return LIST_URL
    return f"{BASE}/vie/chuyen-gia-y-te/page_{page}"


def fetch_pagination_meta(session: requests.Session) -> dict:
    """POST /api/v3/doctor page=1 to obtain pageCount and total doctor count."""
    r = session.post(
        API_URL,
        json=build_api_payload(1),
        headers=HEADERS_JSON,
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("status") is False:
        raise RuntimeError(f"API error: {body}")
    data = body.get("data") or {}
    return data.get("total") or {}


def fetch_static_doctor_list(session: requests.Session, page: int) -> list[dict]:
    url = list_page_url(page)
    r = session.get(url, headers=HEADERS_HTML, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    ul = soup.select_one("#doctor-list")
    if not ul:
        return []
    out: list[dict] = []
    for li in ul.select("li.flex"):
        rec = parse_doctor_li(li)
        if rec:
            out.append(rec)
    return out


def download_image(
    session: requests.Session, url: str, dest: Path
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = session.get(url, headers=HEADERS, timeout=60, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Vinmec doctor directory.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Only fetch the first N list pages (default: all pages).",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Do not download profile images (still saves URLs in JSON).",
    )
    args = parser.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    all_doctors: list[dict] = []
    used_names: dict[str, int] = {}

    with requests.Session() as session:
        time.sleep(REQUEST_DELAY_SEC)

        meta = fetch_pagination_meta(session)
        page_count = int(meta.get("pageCount") or 1)
        total_reported = meta.get("total")
        last_page = page_count
        if args.max_pages is not None:
            last_page = min(last_page, max(1, args.max_pages))

        print(
            f"Pagination (API meta): pageCount={page_count}, "
            f"total doctors (reported)={total_reported}, "
            f"static GET list pages 1–{last_page}"
        )

        time.sleep(REQUEST_DELAY_SEC)

        def process_records(records: list[dict]) -> None:
            for rec in records:
                local = dict(rec)
                stem = sanitize_filename(local["full_name"])
                if stem in used_names:
                    used_names[stem] += 1
                    stem = f"{stem}_{used_names[stem]}"
                else:
                    used_names[stem] = 0

                img_url = local.get("profile_image_url")
                local["profile_image_file"] = None
                if img_url and not args.skip_images:
                    ext = extension_from_url(img_url)
                    img_path = IMAGES_DIR / f"{stem}{ext}"
                    try:
                        time.sleep(REQUEST_DELAY_SEC)
                        download_image(session, img_url, img_path)
                        local["profile_image_file"] = str(img_path).replace("\\", "/")
                    except Exception as e:
                        local["profile_image_download_error"] = str(e)

                for k in ("specialty", "workplace"):
                    if local.get(k) is None:
                        local[k] = None
                all_doctors.append(local)

        for page in range(1, last_page + 1):
            if page > 1:
                time.sleep(REQUEST_DELAY_SEC)
            batch = fetch_static_doctor_list(session, page)
            if not batch:
                print(f"Warning: no doctors parsed at list page {page}")
            process_records(batch)
            if page % 20 == 0 or page == last_page:
                print(
                    f"Fetched list page {page}/{last_page} ({len(all_doctors)} doctors so far)"
                )

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_doctors, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(all_doctors)} records to {OUT_JSON.resolve()}")


if __name__ == "__main__":
    main()
