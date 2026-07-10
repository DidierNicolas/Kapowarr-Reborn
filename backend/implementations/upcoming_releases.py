# -*- coding: utf-8 -*-

"""Fetch tentative future comic releases from publisher calendars."""

from datetime import datetime, timedelta
from json import JSONDecodeError, JSONDecoder
from re import IGNORECASE, compile, sub
from time import time
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from bs4 import BeautifulSoup

from backend.base.definitions import Constants
from backend.base.helpers import Session
from backend.base.logging import LOGGER
from backend.implementations.matching import match_title
from backend.internals.db import get_db

MARVEL_URL = "https://www.marvel.com/comics/calendar"
IMAGE_URL = "https://imagecomics.com/comics/releases/{year}/{month:02d}"

issue_title_regex = compile(r"^(.+?)\s+#([\w.\-/]+)(?:\s|$)", IGNORECASE)
year_suffix_regex = compile(r"\s*\(\d{4}(?:-|–)?\)\s*$")
marvel_assignment_regex = compile(r"=\s*(?=\{)")
image_date_regex = compile(r"Arriving:\s*([^<]+)", IGNORECASE)


def _months_ahead(count: int = 4) -> Iterable[Tuple[int, int]]:
    now = datetime.now()
    for offset in range(count):
        month_index = now.month - 1 + offset
        yield now.year + month_index // 12, month_index % 12 + 1


def _split_issue_title(
    headline: str
) -> Union[Tuple[str, str], Tuple[None, None]]:
    headline = sub(r"\s*\(Variant\)\s*$", "", headline).strip()
    match = issue_title_regex.match(headline)
    if not match:
        return None, None
    title = year_suffix_regex.sub("", match.group(1)).strip()
    return title, match.group(2)


def _find_calendar_entries(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if all(k in value for k in ("headline", "releaseDate", "link")):
            yield value
        for child in value.values():
            yield from _find_calendar_entries(child)
    elif isinstance(value, list):
        for child in value:
            yield from _find_calendar_entries(child)


def _extract_marvel_entries(script: str) -> List[Dict[str, Any]]:
    """Extract the calendar from Marvel's multi-assignment state script."""
    decoder = JSONDecoder()
    best_entries: List[Dict[str, Any]] = []
    for assignment in marvel_assignment_regex.finditer(script):
        try:
            data, _ = decoder.raw_decode(script[assignment.end():])
        except JSONDecodeError:
            continue
        entries = list(_find_calendar_entries(data))
        if len(entries) > len(best_entries):
            best_entries = entries
    return best_entries


def _match_volume(
    title: str,
    volumes: List[Dict[str, Any]]
) -> Optional[int]:
    for volume in volumes:
        if match_title(volume["title"], title):
            return volume["id"]
        if volume["alt_title"] and match_title(volume["alt_title"], title):
            return volume["id"]
    return None


def _fetch_marvel(session: Session, volumes: List[Dict[str, Any]]) -> List[dict]:
    start = datetime.now().strftime("%Y-%m-%d")
    year, month = list(_months_ahead(5))[-1]
    end = (datetime(year, month, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
    response = session.get(
        MARVEL_URL,
        params={
            "dateStart": start,
            "dateEnd": end,
            "tab": "comic",
            "variants": "false"
        },
        headers={
            "User-Agent": Constants.BROWSER_USERAGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.marvel.com/comics"
        }
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    data_script = next(
        (script.string for script in soup.find_all("script")
         if script.string and '"releaseDate"' in script.string),
        None
    )
    entries = _extract_marvel_entries(data_script or "")
    if not entries:
        raise ValueError("Marvel calendar data was not found")

    results = []
    seen = set()
    for entry in entries:
        title, issue_number = _split_issue_title(entry["headline"])
        if not title or not issue_number or entry.get("isVariant"):
            continue
        source_url = entry["link"].get("link", "")
        key = (title.lower(), issue_number, entry["releaseDate"])
        volume_id = _match_volume(title, volumes)
        if volume_id is None or key in seen:
            continue
        seen.add(key)
        results.append({
            "volume_id": volume_id,
            "source": "Marvel",
            "source_url": source_url,
            "title": title,
            "issue_number": issue_number,
            "release_date": entry["releaseDate"]
        })
    LOGGER.debug(
        "Marvel calendar parsed %d entries and matched %d library releases",
        len(entries), len(results)
    )
    return results


def _fetch_image(session: Session, volumes: List[Dict[str, Any]]) -> List[dict]:
    candidates = {}
    for year, month in _months_ahead(4):
        response = session.get(IMAGE_URL.format(year=year, month=month))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select("section.comics-grid a.cover-image[href]"):
            image = link.find("img", alt=True)
            headline = image.get("alt", "") if image else ""
            if headline.endswith(" cover"):
                headline = headline[:-6]
            title, issue_number = _split_issue_title(headline)
            if not title or not issue_number:
                continue
            volume_id = _match_volume(title, volumes)
            if volume_id is not None:
                candidates[link["href"]] = (volume_id, title, issue_number)

    results = []
    for source_url, (volume_id, title, issue_number) in candidates.items():
        response = session.get(source_url)
        response.raise_for_status()
        date_match = image_date_regex.search(response.text)
        if not date_match:
            continue
        release_date = datetime.strptime(
            date_match.group(1).strip(), "%B %d, %Y"
        ).strftime("%Y-%m-%d")
        results.append({
            "volume_id": volume_id,
            "source": "Image",
            "source_url": source_url,
            "title": title,
            "issue_number": issue_number,
            "release_date": release_date
        })
    return results


def refresh_upcoming_releases() -> Dict[str, int]:
    """Refresh matched Marvel and Image releases for library volumes."""
    cursor = get_db()
    volumes = cursor.execute(
        "SELECT id, title, alt_title FROM volumes;"
    ).fetchalldict()
    session = Session()
    counts = {}
    fetched_at = round(time())

    for source, fetcher in (("Marvel", _fetch_marvel), ("Image", _fetch_image)):
        try:
            releases = fetcher(session, volumes)
        except Exception:
            LOGGER.exception("Failed to refresh %s upcoming releases", source)
            counts[source] = 0
            continue

        cursor.execute("DELETE FROM upcoming_releases WHERE source = ?;", (source,))
        cursor.executemany(
            """
            INSERT INTO upcoming_releases(
                volume_id, source, source_url, title,
                issue_number, release_date, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            ((r["volume_id"], r["source"], r["source_url"], r["title"],
              r["issue_number"], r["release_date"], fetched_at)
             for r in releases)
        )
        counts[source] = len(releases)

    LOGGER.info("Upcoming release refresh complete: %s", counts)
    return counts
