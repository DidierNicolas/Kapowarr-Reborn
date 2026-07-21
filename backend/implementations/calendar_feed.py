# -*- coding: utf-8 -*-

"""Calendar queries and RFC 5545 iCalendar feed generation."""

from datetime import datetime, timedelta, timezone
from hashlib import sha1
from typing import List, Optional

from backend.internals.db import get_db


def get_calendar_entries(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> List[dict]:
    """Return library issues and non-duplicated tentative releases."""
    date_filter = ''
    parameters = []
    if start is not None and end is not None:
        date_filter = 'AND issues.date >= ? AND issues.date < ?'
        parameters = [start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')]

    issues = get_db().execute(f"""
        SELECT
            issues.id, issues.volume_id, issues.issue_number,
            issues.title, issues.date, issues.monitored,
            volumes.title AS volume_title,
            EXISTS(
                SELECT 1 FROM issues_files
                WHERE issues_files.issue_id = issues.id
            ) AS downloaded,
            NULL AS source, NULL AS source_url, 0 AS tentative
        FROM issues
        INNER JOIN volumes ON volumes.id = issues.volume_id
        WHERE issues.date IS NOT NULL {date_filter}
        ORDER BY issues.date, volumes.title, issues.calculated_issue_number;
        """, tuple(parameters)).fetchalldict()

    upcoming_filter = ''
    if start is not None and end is not None:
        upcoming_filter = (
            'AND upcoming_releases.release_date >= ? '
            'AND upcoming_releases.release_date < ?'
        )
    upcoming = get_db().execute(f"""
        SELECT
            NULL AS id, upcoming_releases.volume_id,
            upcoming_releases.issue_number, NULL AS title,
            upcoming_releases.release_date AS date, volumes.monitored,
            volumes.title AS volume_title, 0 AS downloaded,
            upcoming_releases.source, upcoming_releases.source_url,
            1 AS tentative
        FROM upcoming_releases
        INNER JOIN volumes ON volumes.id = upcoming_releases.volume_id
        WHERE 1 = 1 {upcoming_filter}
          AND NOT EXISTS (
              SELECT 1 FROM issues
              WHERE issues.volume_id = upcoming_releases.volume_id
                AND issues.issue_number = upcoming_releases.issue_number
          )
        ORDER BY upcoming_releases.release_date, volumes.title;
        """, tuple(parameters)).fetchalldict()

    issues.extend(upcoming)
    issues.sort(key=lambda issue: (
        issue['date'], issue['volume_title'], issue['issue_number']
    ))
    return issues


def _escape(value: object) -> str:
    return (str(value or '')
            .replace('\r\n', '\n')
            .replace('\r', '\n')
            .replace('\\', '\\\\')
            .replace('\n', '\\n')
            .replace(';', '\\;')
            .replace(',', '\\,'))


def _fold(line: str) -> List[str]:
    """Fold an iCalendar content line to the required 75-byte limit."""
    result = []
    current = ''
    for character in line:
        candidate = current + character
        if current and len(candidate.encode('utf-8')) > 75:
            result.append(current)
            current = ' ' + character
        else:
            current = candidate
    result.append(current)
    return result


def build_icalendar(entries: List[dict], base_url: str) -> bytes:
    """Build an iCalendar 2.0 feed from calendar entry dictionaries."""
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        'PRODID:-//Kapowarr//Comic Release Calendar//EN',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
        'X-WR-CALNAME:Kapowarr Releases',
        'REFRESH-INTERVAL;VALUE=DURATION:PT1H',
        'X-PUBLISHED-TTL:PT1H'
    ]
    for entry in entries:
        date = datetime.strptime(entry['date'], '%Y-%m-%d')
        identity = '|'.join(str(entry.get(key) or '') for key in (
            'id', 'volume_id', 'issue_number', 'date', 'tentative'
        ))
        uid = sha1(identity.encode('utf-8')).hexdigest() + '@kapowarr'
        title = f"{entry['volume_title']} #{entry['issue_number']}"
        if entry.get('title'):
            title += f" - {entry['title']}"
        state = ('Downloaded' if entry.get('downloaded') else
                 'Monitored - Missing' if entry.get('monitored') else
                 'Not monitored')
        description = state
        if entry.get('tentative'):
            description += f"; Tentative {entry.get('source') or 'publisher'} date"
        event_url = (
            entry.get('source_url')
            if entry.get('tentative') and entry.get('source_url')
            else f"{base_url.rstrip('/')}/volumes/{entry['volume_id']}"
        )
        lines.extend((
            'BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{now}',
            f'DTSTART;VALUE=DATE:{date.strftime("%Y%m%d")}',
            f'DTEND;VALUE=DATE:{(date + timedelta(days=1)).strftime("%Y%m%d")}',
            f'SUMMARY:{_escape(title)}',
            f'DESCRIPTION:{_escape(description)}',
            f'URL:{_escape(event_url)}',
            f'STATUS:{"TENTATIVE" if entry.get("tentative") else "CONFIRMED"}',
            'TRANSP:TRANSPARENT', 'END:VEVENT'
        ))
    lines.append('END:VCALENDAR')
    folded = [part for line in lines for part in _fold(line)]
    return ('\r\n'.join(folded) + '\r\n').encode('utf-8')
