# -*- coding: utf-8 -*-

"""Persist GetComics' latest weekly pack with ComicVine metadata."""

from asyncio import run
from datetime import datetime, timedelta
from html import unescape
from json import dumps, loads
from re import IGNORECASE, compile
from time import time
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from backend.base.helpers import Session
from backend.base.logging import LOGGER
from backend.implementations.comicvine import ComicVine
from backend.implementations.matching import match_title
from backend.implementations.metron import Metron
from backend.internals.db import get_db
from backend.internals.settings import Settings

WP_POSTS_URL = "https://getcomics.org/wp-json/wp/v2/posts"
METADATA_VERSION = 11
MAX_RELEASE_DISTANCE_DAYS = 7
MAX_VOLUME_CANDIDATES = 25
issue_suffix_regex = compile(r"\s+#(?:\d+(?:\.\w+)?|[A-Za-z]+).*?$", IGNORECASE)
year_suffix_regex = compile(r"\s*\(\d{4}\)\s*$")
issue_number_regex = compile(r"\s+#([^\s:]+)", IGNORECASE)
series_year_regex = compile(r"\((\d{4})\)")


def _metron_enabled() -> bool:
    settings = Settings().sv
    return bool(settings.metron_username and settings.metron_password)


def _cover_from_post(post: dict) -> str:
    try:
        media = post["_embedded"]["wp:featuredmedia"][0]
        return media.get("source_url", "")
    except (KeyError, IndexError, TypeError):
        return ""


def _fetch_latest_pack(session: Session) -> Optional[dict]:
    pack_response = session.get(WP_POSTS_URL, params={
        "search": "Weekly Pack",
        "orderby": "date",
        "order": "desc",
        "per_page": 1,
        "_embed": 1
    })
    pack_response.raise_for_status()
    packs = pack_response.json()
    if not packs:
        return None
    return packs[0]


def _parse_pack(session: Session, pack: dict) -> dict:
    """Parse the weekly pack and find its GetComics cover URLs."""
    soup = BeautifulSoup(pack["content"]["rendered"], "html.parser")
    comics_by_url = {}
    for item in soup.find_all("li"):
        download_link = next((
            link for link in item.find_all("a", href=True)
            if urlparse(link["href"]).netloc.endswith("getcomics.org")
            and "Download" in link.get_text(" ", strip=True)
        ), None)
        if download_link is None:
            continue
        raw_title = item.get_text(" ", strip=True).split(" : ", 1)[0]
        title = unescape(raw_title).strip()
        query = year_suffix_regex.sub("", issue_suffix_regex.sub("", title)).strip()
        issue_match = issue_number_regex.search(title)
        year_match = series_year_regex.search(title)
        comics_by_url[download_link["href"].rstrip("/")] = {
            "title": title,
            "query": query,
            "issue_number": issue_match.group(1) if issue_match else "",
            "series_year": int(year_match.group(1)) if year_match else None,
            "url": download_link["href"],
            "cover": ""
        }

    pack_date = datetime.fromisoformat(pack["date_gmt"])
    params = {
        "after": (pack_date - timedelta(hours=12)).isoformat(),
        "before": (pack_date + timedelta(days=7)).isoformat(),
        "orderby": "date",
        "order": "asc",
        "per_page": 100,
        "_embed": 1
    }
    page = 1
    while page <= 3:
        params["page"] = page
        posts_response = session.get(WP_POSTS_URL, params=params)
        if posts_response.status_code == 400:
            break
        posts_response.raise_for_status()
        posts: List[dict] = posts_response.json()
        for post in posts:
            key = post["link"].rstrip("/")
            if key in comics_by_url:
                comics_by_url[key]["cover"] = _cover_from_post(post)
        if len(posts) < 100:
            break
        page += 1

    result = {
        "pack_id": str(pack["id"]),
        "metadata_version": METADATA_VERSION,
        "metron_enabled": _metron_enabled(),
        "title": unescape(pack["title"]["rendered"]),
        "source_url": pack["link"],
        "pack_date": pack_date.strftime("%Y-%m-%d"),
        "comics": list(comics_by_url.values())
    }
    return result


def _public_volume(volume: dict) -> dict:
    """Keep only serializable metadata needed by the weekly page."""
    return {
        "comicvine_id": volume["comicvine_id"],
        "title": volume["title"],
        "year": volume["year"],
        "volume_number": volume["volume_number"],
        "publisher": volume["publisher"],
        "cover_link": volume["cover_link"],
        "site_url": volume["site_url"],
        "already_added": volume["already_added"]
    }


def _rank_volume_matches(comic: dict, matches: List[dict]) -> List[dict]:
    """Put exact and recent editions first before limiting validation work."""
    def rank(match: dict):
        exact_penalty = int(not match_title(comic["query"], match["title"]))
        year_penalty = -(match["year"] or 0)
        publisher_penalty = int(
            (match["publisher"] or "").casefold() not in ("marvel", "dc comics")
        )
        return exact_penalty, year_penalty, publisher_penalty

    return sorted(matches, key=rank)[:MAX_VOLUME_CANDIDATES]


def _candidate_matches(comic: dict) -> List[dict]:
    """Return exact series-title matches for release-date validation."""
    return [match for match in comic["matches"]
            if match_title(comic["query"], match["title"])]


def _select_match(
    comic: dict,
    issues_by_volume: Dict[int, List[dict]],
    pack_date: datetime
) -> Optional[dict]:
    """Select the volume whose requested issue went on sale near pack day."""
    ranked = []
    requested_number = comic["issue_number"].casefold()
    for match in _candidate_matches(comic):
        for issue in issues_by_volume.get(match["comicvine_id"], []):
            if issue["issue_number"].casefold() != requested_number:
                continue
            if not issue["date"]:
                continue
            try:
                store_date = datetime.strptime(issue["date"], "%Y-%m-%d")
            except ValueError:
                continue
            distance = abs((store_date - pack_date).days)
            if distance > MAX_RELEASE_DISTANCE_DAYS:
                continue
            year_penalty = int(
                comic["series_year"] is not None
                and match["year"] != comic["series_year"]
            )
            ranked.append((distance, year_penalty, match, issue))

    if not ranked:
        return None
    _, _, selected, issue = min(ranked, key=lambda entry: entry[:2])
    selected = dict(selected)
    selected["issue_comicvine_id"] = issue["comicvine_id"]
    selected["store_date"] = issue["date"]
    return selected


def _add_issue_validation(
    comic: dict,
    issues_by_volume: Dict[int, List[dict]],
    pack_date: datetime
) -> None:
    """Attach issue/date evidence to candidates for the manual-match UI."""
    requested_number = comic["issue_number"].casefold()
    for match in comic["matches"]:
        matching_issues = [
            issue for issue in issues_by_volume.get(match["comicvine_id"], [])
            if issue["issue_number"].casefold() == requested_number
        ]
        dated = []
        for issue in matching_issues:
            try:
                store_date = datetime.strptime(issue["date"], "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            dated.append((abs((store_date - pack_date).days), issue))
        match["issue_found"] = bool(matching_issues)
        match["issue_store_date"] = None
        match["release_distance_days"] = None
        match["issue_comicvine_id"] = None
        if dated:
            distance, issue = min(dated, key=lambda entry: entry[0])
            match["issue_store_date"] = issue["date"]
            match["release_distance_days"] = distance
            match["issue_comicvine_id"] = issue["comicvine_id"]


def refresh_weekly_releases(
    progress: Optional[Callable[[str], None]] = None
) -> Dict[str, object]:
    """Store a new weekly pack, doing nothing when its ID has not changed."""
    session = Session()
    pack = _fetch_latest_pack(session)
    if pack is None:
        return {"updated": False, "reason": "no_pack"}

    cursor = get_db()
    current = cursor.execute(
        "SELECT pack_id, data FROM weekly_releases WHERE id = 1;"
    ).fetchone()
    pack_id = str(pack["id"])
    if current is not None and current["pack_id"] == pack_id:
        try:
            current_data = loads(current["data"])
            current_version = current_data.get("metadata_version", 1)
        except (TypeError, ValueError):
            current_data = {}
            current_version = 1
        if (current_version == METADATA_VERSION
                and current_data.get("metron_enabled", False)
                == _metron_enabled()):
            LOGGER.info("Weekly comics pack %s is already current", pack_id)
            return {"updated": False, "pack_id": pack_id}

    result = _parse_pack(session, pack)
    comicvine = ComicVine()
    for index, comic in enumerate(result["comics"], 1):
        if progress is not None:
            progress(
                "Matching ComicVine metadata "
                f"({index}/{len(result['comics'])}): {comic['title']}"
            )
        LOGGER.debug(
            "Matching weekly comic %d/%d: %s",
            index, len(result["comics"]), comic["query"]
        )
        matches = run(comicvine.search_volumes(comic["query"]))
        public_matches = [_public_volume(match) for match in matches]
        comic["matches"] = _rank_volume_matches(comic, public_matches)

    candidate_ids = {
        match["comicvine_id"]
        for comic in result["comics"]
        for match in _candidate_matches(comic)
    }
    if progress is not None:
        progress("Validating issue in-store dates with ComicVine")
    issues = (
        run(comicvine.fetch_issues(tuple(candidate_ids), date_type="store_date"))
        if candidate_ids else []
    )
    issues_by_volume: Dict[int, List[dict]] = {}
    for issue in issues:
        issues_by_volume.setdefault(issue["volume_id"], []).append(issue)

    pack_day = datetime.strptime(result["pack_date"], "%Y-%m-%d")
    for comic in result["comics"]:
        _add_issue_validation(comic, issues_by_volume, pack_day)
        comic["selected_match"] = _select_match(
            comic, issues_by_volume, pack_day
        )
        if comic["selected_match"]:
            comic["cover"] = comic["selected_match"]["cover_link"]

    unmatched = [comic for comic in result["comics"]
                 if comic["selected_match"] is None]
    if unmatched:
        if progress is not None:
            progress("Checking unmatched weekly comics against Metron")
        metron = Metron()
        metron_matches = metron.find_weekly_issues(unmatched, pack_day)
        for comic in unmatched:
            comic["metron_checked"] = metron.enabled
            metron_match = metron_matches.get(comic["url"])
            if metron_match is None:
                continue
            comic["metron_match_found"] = True
            volumes = run(comicvine.search_volumes(
                f"cv:{metron_match['series_comicvine_id']}"
            ))
            if not volumes:
                continue
            selected = _public_volume(volumes[0])
            selected.update({
                "match_source": "Metron",
                "metron_issue_id": metron_match["metron_issue_id"],
                "issue_comicvine_id": metron_match["issue_comicvine_id"],
                "store_date": metron_match["store_date"],
                "release_distance_days": metron_match[
                    "release_distance_days"
                ],
                "metron_targeted_lookup": metron_match.get(
                    "targeted_lookup", False
                )
            })
            comic["selected_match"] = selected
            comic["cover"] = selected["cover_link"]
            if not any(match["comicvine_id"] == selected["comicvine_id"]
                       for match in comic["matches"]):
                comic["matches"].insert(0, selected)

    # Replace only after both sources have been fetched successfully. This
    # preserves last week's usable snapshot if either service is unavailable.
    cursor.execute("""
        INSERT INTO weekly_releases(id, pack_id, fetched_at, data)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            pack_id = excluded.pack_id,
            fetched_at = excluded.fetched_at,
            data = excluded.data;
        """,
        (pack_id, round(time()), dumps(result, separators=(",", ":")))
    )
    LOGGER.info(
        "Stored weekly comics pack %s with %d entries",
        pack_id, len(result["comics"])
    )
    return {"updated": True, "pack_id": pack_id,
            "comics": len(result["comics"])}


def set_weekly_release_match(comic_url: str, comicvine_id: int) -> dict:
    """Persist a user-corrected ComicVine volume match in the snapshot."""
    cursor = get_db()
    row = cursor.execute(
        "SELECT data FROM weekly_releases WHERE id = 1;"
    ).fetchone()
    if row is None:
        raise ValueError("No weekly release snapshot exists")
    result = loads(row["data"])
    comic = next((entry for entry in result["comics"]
                  if entry["url"] == comic_url), None)
    if comic is None:
        raise ValueError("Weekly comic was not found")
    selected = next((match for match in comic["matches"]
                     if match["comicvine_id"] == comicvine_id), None)
    if selected is None:
        raise ValueError("ComicVine candidate was not found")
    comic["selected_match"] = selected
    comic["cover"] = selected["cover_link"]
    cursor.execute(
        "UPDATE weekly_releases SET data = ? WHERE id = 1;",
        (dumps(result, separators=(",", ":")),)
    )
    return selected


def get_weekly_releases() -> dict:
    """Return the persistent snapshot, creating it on its first request."""
    row = get_db().execute(
        "SELECT data FROM weekly_releases WHERE id = 1;"
    ).fetchone()
    needs_refresh = row is None
    if row is not None:
        try:
            needs_refresh = (
                loads(row["data"]).get("metadata_version", 1)
                != METADATA_VERSION
            )
            if not needs_refresh:
                needs_refresh = (
                    loads(row["data"]).get("metron_enabled", False)
                    != _metron_enabled()
                )
        except (TypeError, ValueError):
            needs_refresh = True
    if needs_refresh:
        refresh_weekly_releases()
        row = get_db().execute(
            "SELECT data FROM weekly_releases WHERE id = 1;"
        ).fetchone()
    if row is None:
        return {"title": "This Week Comics", "source_url": "", "comics": []}
    result = loads(row["data"])
    cursor = get_db()
    for comic in result["comics"]:
        comic["status"] = "unmonitored"
        comic["library_volume_id"] = None
        comic["library_issue_id"] = None
        comic["is_monitored"] = False
        selected = comic.get("selected_match")
        if not selected:
            continue
        issue_condition = "issues.comicvine_id = ?"
        issue_value = selected.get("issue_comicvine_id")
        if issue_value is None:
            issue_condition = "issues.issue_number = ?"
            issue_value = comic.get("issue_number", "")
        library = cursor.execute(f"""
            SELECT
                volumes.id AS volume_id,
                volumes.monitored AS volume_monitored,
                issues.id AS issue_id,
                issues.monitored AS issue_monitored,
                EXISTS(
                    SELECT 1 FROM issues_files
                    WHERE issues_files.issue_id = issues.id
                ) AS downloaded
            FROM volumes
            LEFT JOIN issues
                ON issues.volume_id = volumes.id
               AND {issue_condition}
            WHERE volumes.comicvine_id = ?
            LIMIT 1;
            """,
            (issue_value, selected["comicvine_id"])
        ).fetchone()
        if library is None:
            continue
        comic["library_volume_id"] = library["volume_id"]
        comic["library_issue_id"] = library["issue_id"]
        if library["downloaded"]:
            comic["status"] = "downloaded"
        elif (library["issue_monitored"] if library["issue_id"] is not None
              else library["volume_monitored"]):
            comic["status"] = "missing"
            comic["is_monitored"] = True
    return result
