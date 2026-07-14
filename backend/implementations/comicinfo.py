# -*- coding: utf-8 -*-

"""Create and update ComicInfo.xml metadata inside CBZ archives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from os import chmod, close, replace, stat, unlink
from os.path import basename, dirname, splitext
from shutil import copystat
from stat import S_IMODE
from tempfile import mkstemp
from typing import Dict, Iterable, Optional
from xml.etree.ElementTree import (Element, ParseError, SubElement, TreeBuilder,
                                   XMLParser, fromstring, tostring)
from zipfile import ZIP_DEFLATED, ZipFile

from backend.base.logging import LOGGER
from backend.internals.db import commit, get_db
from backend.internals.db_models import FilesDB


COMICINFO_FILENAME = 'ComicInfo.xml'
KAPOWARR_NOTE = 'Metadata written by Kapowarr.'

# ComicInfo 2.0 requires elements to follow schema order.
COMICINFO_ORDER = (
    'Title', 'Series', 'Number', 'Count', 'Volume', 'AlternateSeries',
    'AlternateNumber', 'AlternateCount', 'Summary', 'Notes', 'Year', 'Month',
    'Day', 'Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer', 'CoverArtist',
    'Editor', 'Publisher', 'Imprint', 'Genre', 'Web', 'PageCount',
    'LanguageISO', 'Format', 'BlackAndWhite', 'Manga', 'Characters', 'Teams',
    'Locations', 'ScanInformation', 'StoryArc', 'SeriesGroup',
    'AgeRating', 'Pages', 'CommunityRating', 'MainCharacterOrTeam', 'Review'
)
OWNED_FIELDS = {
    'Title', 'Series', 'Number', 'Count', 'Volume', 'Summary', 'Notes', 'Year',
    'Month', 'Day', 'Publisher', 'Web'
}


@dataclass
class ComicInfoResult:
    written: int = 0
    skipped: int = 0
    failed: int = 0

    def add(self, other: 'ComicInfoResult') -> None:
        self.written += other.written
        self.skipped += other.skipped
        self.failed += other.failed


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ''
    return tag.rsplit('}', 1)[-1]


def _parse_existing(xml: Optional[bytes]) -> Element:
    if not xml:
        return Element('ComicInfo')
    parser = XMLParser(target=TreeBuilder(insert_comments=True))
    root = fromstring(xml, parser=parser)
    if _local_name(root.tag).casefold() != 'comicinfo':
        raise ParseError('Root element is not ComicInfo')
    return root


def _set_field(root: Element, name: str, value: Optional[object]) -> None:
    matches = [
        child for child in list(root)
        if _local_name(child.tag).casefold() == name.casefold()
    ]
    if value is None or value == '':
        return

    namespace = (
        root.tag.split('}', 1)[0] + '}'
        if isinstance(root.tag, str) and root.tag.startswith('{')
        else ''
    )
    child = matches[0] if matches else SubElement(root, namespace + name)
    child.text = str(value)
    for duplicate in matches[1:]:
        root.remove(duplicate)


def _merge_notes(root: Element) -> str:
    for child in root:
        if _local_name(child.tag).casefold() == 'notes':
            current = (child.text or '').strip()
            if KAPOWARR_NOTE.casefold() in current.casefold():
                return current
            return f'{current}\n{KAPOWARR_NOTE}' if current else KAPOWARR_NOTE
    return KAPOWARR_NOTE


def _sort_elements(root: Element) -> None:
    order = {name.casefold(): index for index, name in enumerate(COMICINFO_ORDER)}
    children = list(root)
    indexed = list(enumerate(children))
    indexed.sort(key=lambda pair: (
        order.get(_local_name(pair[1].tag).casefold(), len(order)), pair[0]
    ))
    root[:] = [child for _, child in indexed]


def _indent_xml(element: Element, level: int = 0) -> None:
    """Indent XML without requiring ElementTree.indent from Python 3.9."""
    indentation = '\n' + ('  ' * level)
    child_indentation = '\n' + ('  ' * (level + 1))
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = child_indentation
        for child in children:
            _indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = child_indentation
        children[-1].tail = indentation


def build_comicinfo_xml(
    metadata: Dict[str, object],
    existing_xml: Optional[bytes] = None
) -> bytes:
    """Merge Kapowarr-owned fields into a ComicInfo 2.0 XML document."""
    root = _parse_existing(existing_xml)
    metadata = dict(metadata)
    metadata['Notes'] = _merge_notes(root)
    for field in OWNED_FIELDS:
        _set_field(root, field, metadata.get(field))
    _sort_elements(root)
    _indent_xml(root)
    return tostring(root, encoding='utf-8', xml_declaration=True)


def _metadata_for_file(filepath: str) -> Optional[Dict[str, object]]:
    row = get_db().execute("""
        SELECT
            i.comicvine_id AS issue_comicvine_id,
            i.issue_number,
            i.title AS issue_title,
            i.date AS issue_date,
            i.description AS issue_description,
            v.title AS series,
            v.volume_number,
            v.publisher,
            v.site_url,
            (SELECT COUNT(*) FROM issues WHERE volume_id = v.id) AS issue_count
        FROM files f
        INNER JOIN issues_files map ON map.file_id = f.id
        INNER JOIN issues i ON i.id = map.issue_id
        INNER JOIN volumes v ON v.id = i.volume_id
        WHERE f.filepath = ?
        ORDER BY i.calculated_issue_number, i.id
        LIMIT 1;
    """, (filepath,)).fetchone()
    if not row:
        return None

    release_date = None
    if row['issue_date']:
        try:
            release_date = date.fromisoformat(row['issue_date'])
        except ValueError:
            LOGGER.warning(
                f'Invalid issue date while writing ComicInfo.xml: {row["issue_date"]}'
            )

    issue_cv_id = row['issue_comicvine_id']
    web = (
        f'https://comicvine.gamespot.com/issue/4000-{issue_cv_id}/'
        if issue_cv_id and issue_cv_id > 0
        else row['site_url']
    )
    return {
        'Title': row['issue_title'],
        'Series': row['series'],
        'Number': row['issue_number'],
        'Count': row['issue_count'],
        'Volume': row['volume_number'],
        'Summary': row['issue_description'],
        'Year': release_date.year if release_date else None,
        'Month': release_date.month if release_date else None,
        'Day': release_date.day if release_date else None,
        'Publisher': row['publisher'],
        'Web': web
    }


def _existing_comicinfo(archive: ZipFile) -> Optional[bytes]:
    entries = [
        info for info in archive.infolist()
        if basename(info.filename).casefold() == COMICINFO_FILENAME.casefold()
    ]
    return archive.read(entries[0]) if entries else None


def write_comicinfo(filepath: str) -> ComicInfoResult:
    """Write ComicInfo.xml to one CBZ, returning an isolated result count."""
    if splitext(filepath)[1].casefold() != '.cbz':
        return ComicInfoResult(skipped=1)

    metadata = _metadata_for_file(filepath)
    if metadata is None:
        LOGGER.debug(f'Skipping ComicInfo.xml for unmatched file: {filepath}')
        return ComicInfoResult(skipped=1)

    temp_fd = -1
    temp_path = ''
    try:
        temp_fd, temp_path = mkstemp(prefix='.kapowarr-comicinfo-',
                                     suffix='.cbz', dir=dirname(filepath))
        close(temp_fd)
        temp_fd = -1
        original_mode = S_IMODE(stat(filepath).st_mode)

        with ZipFile(filepath, 'r') as source:
            xml = build_comicinfo_xml(metadata, _existing_comicinfo(source))
            with ZipFile(temp_path, 'w') as target:
                target.comment = source.comment
                for info in source.infolist():
                    if basename(info.filename).casefold() == COMICINFO_FILENAME.casefold():
                        continue
                    target.writestr(info, source.read(info))
                target.writestr(COMICINFO_FILENAME, xml, compress_type=ZIP_DEFLATED)

        copystat(filepath, temp_path)
        chmod(temp_path, original_mode)
        replace(temp_path, filepath)
        temp_path = ''
        get_db().execute(
            'UPDATE files SET size = ? WHERE filepath = ?;',
            (stat(filepath).st_size, filepath)
        )
        return ComicInfoResult(written=1)
    except Exception as exc:
        # One inaccessible or unusual archive must not abort a library task.
        LOGGER.warning(f'Failed to write ComicInfo.xml to {filepath}: {exc}')
        return ComicInfoResult(failed=1)
    finally:
        if temp_fd >= 0:
            close(temp_fd)
        if temp_path:
            try:
                unlink(temp_path)
            except FileNotFoundError:
                pass


def write_comicinfo_for_files(filepaths: Iterable[str]) -> ComicInfoResult:
    result = ComicInfoResult()
    for filepath in dict.fromkeys(filepaths):
        result.add(write_comicinfo(filepath))
    commit()
    return result


def write_comicinfo_for_volume(volume_id: int) -> ComicInfoResult:
    return write_comicinfo_for_files(
        file['filepath'] for file in FilesDB.fetch(volume_id=volume_id)
    )
