# -*- coding: utf-8 -*-

"""Small, rate-conscious client for weekly issue lookups in Metron."""

from datetime import datetime, timedelta
from re import compile
from typing import Dict, List, Optional

from backend.base.helpers import Session
from backend.base.helpers import normalise_query_string
from backend.base.logging import LOGGER
from backend.implementations.matching import match_title
from backend.internals.settings import Settings

METRON_API = "https://metron.cloud/api"
TARGETED_MAX_DISTANCE_DAYS = 70
title_separator_regex = compile(r"[^\w\s']+")


def _search_title(title: str) -> str:
    """Use normalized words because Metron's title filter is punctuation-strict."""
    normalized = normalise_query_string(title)
    return " ".join(title_separator_regex.sub(" ", normalized).split())


class Metron:
    def __init__(self) -> None:
        settings = Settings().sv
        self.enabled = bool(settings.metron_username and settings.metron_password)
        self.session = Session()
        if self.enabled:
            self.session.auth = (
                settings.metron_username,
                settings.metron_password
            )
        self.series_cache: Dict[int, dict] = {}

    def _get_pages(self, endpoint: str, params: dict) -> List[dict]:
        results: List[dict] = []
        url: Optional[str] = METRON_API + endpoint
        while url:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("results", []))
            url = data.get("next")
            params = {}
        return results

    @staticmethod
    def _series(issue: dict) -> dict:
        series = issue.get("series") or {}
        return series if isinstance(series, dict) else {}

    def _series_cv_id(self, series: dict) -> Optional[int]:
        cv_id = series.get("cv_id")
        if cv_id:
            return int(cv_id)
        series_id = series.get("id")
        if not series_id:
            return None
        series_id = int(series_id)
        if series_id not in self.series_cache:
            response = self.session.get(f"{METRON_API}/series/{series_id}/")
            response.raise_for_status()
            self.series_cache[series_id] = response.json()
        cv_id = self.series_cache[series_id].get("cv_id")
        return int(cv_id) if cv_id else None

    def find_weekly_issues(
        self,
        comics: List[dict],
        pack_date: datetime
    ) -> Dict[str, dict]:
        """Match unmatched weekly entries against one date-window query."""
        if not self.enabled or not comics:
            return {}
        after = (pack_date - timedelta(days=7)).strftime("%Y-%m-%d")
        before = (pack_date + timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            issues = self._get_pages("/issue/", {
                "store_date_range_after": after,
                "store_date_range_before": before
            })
        except Exception:
            LOGGER.exception("Failed to query Metron weekly issues")
            return {}

        LOGGER.info(
            "Metron returned %d issues for weekly window %s through %s",
            len(issues), after, before
        )

        matches: Dict[str, dict] = {}

        def find_candidate(comic: dict, source_issues: List[dict],
                           max_distance: int) -> Optional[dict]:
            candidates = []
            for issue in source_issues:
                series = self._series(issue)
                name = series.get("name") or issue.get("series_name") or ""
                number = str(issue.get("number") or issue.get("issue_number") or "")
                if not match_title(comic["query"], name):
                    continue
                if number.casefold() != comic["issue_number"].casefold():
                    continue
                date_text = issue.get("store_date")
                try:
                    distance = abs((
                        datetime.strptime(date_text, "%Y-%m-%d") - pack_date
                    ).days)
                except (TypeError, ValueError):
                    continue
                if distance > max_distance:
                    continue
                series_cv_id = issue.get("series_cv_id")
                if not series_cv_id:
                    try:
                        series_cv_id = self._series_cv_id(series)
                    except Exception:
                        LOGGER.exception(
                            "Failed to resolve Metron series %s", series.get("id")
                        )
                if not series_cv_id:
                    continue
                candidates.append((distance, issue, series, int(series_cv_id)))
            if candidates:
                distance, issue, series, series_cv_id = min(
                    candidates, key=lambda entry: entry[0]
                )
                return {
                    "metron_issue_id": issue.get("id"),
                    "issue_comicvine_id": issue.get("cv_id"),
                    "series_comicvine_id": series_cv_id,
                    "store_date": issue.get("store_date"),
                    "release_distance_days": distance
                }
            return None

        for comic in comics:
            candidate = find_candidate(comic, issues, 7)
            if candidate is not None:
                matches[comic["url"]] = candidate

        # GetComics sometimes includes delayed releases. For entries absent
        # from the strict weekly window, make one precise series+number query
        # and accept an exact issue up to ten weeks away.
        for comic in comics:
            if comic["url"] in matches or not comic["issue_number"]:
                continue
            try:
                targeted_issues = self._get_pages("/issue/", {
                    "series_name": _search_title(comic["query"]),
                    "number": comic["issue_number"]
                })
            except Exception:
                LOGGER.exception(
                    "Failed targeted Metron lookup for %s", comic["title"]
                )
                continue
            candidate = find_candidate(
                comic, targeted_issues, TARGETED_MAX_DISTANCE_DAYS
            )
            if candidate is not None:
                candidate["targeted_lookup"] = True
                matches[comic["url"]] = candidate
        LOGGER.info(
            "Metron matched %d of %d unmatched weekly comics",
            len(matches), len(comics)
        )
        return matches
