# -*- coding: utf-8 -*-

import unittest
from os.path import join
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree.ElementTree import fromstring
from zipfile import BadZipFile, ZipFile

from backend.implementations.comicinfo import (KAPOWARR_NOTE,
                                               build_comicinfo_xml,
                                               write_comicinfo)


METADATA = {
    'Title': 'The <Test> & Escape',
    'Series': 'Example Series',
    'Number': '7',
    'Count': 12,
    'Volume': 2,
    'Summary': 'A summary & more.',
    'Year': 2026,
    'Month': 7,
    'Day': 13,
    'Publisher': 'Example Comics',
    'Web': 'https://example.test/issue/7'
}


class ComicInfoXML(unittest.TestCase):
    def test_generates_valid_escaped_xml(self):
        xml = build_comicinfo_xml(METADATA)
        root = fromstring(xml)
        self.assertEqual(root.findtext('Title'), 'The <Test> & Escape')
        self.assertEqual(root.findtext('Series'), 'Example Series')
        self.assertEqual(root.findtext('Year'), '2026')
        self.assertEqual(root.findtext('Notes'), KAPOWARR_NOTE)
        self.assertEqual(
            [child.tag for child in root],
            ['Title', 'Series', 'Number', 'Count', 'Volume', 'Summary', 'Notes',
             'Year', 'Month', 'Day', 'Publisher', 'Web']
        )
        lines = xml.decode('utf-8').splitlines()
        self.assertEqual(lines[1], '<ComicInfo>')
        self.assertEqual(lines[2], '  <Title>The &lt;Test&gt; &amp; Escape</Title>')
        self.assertEqual(lines[-1], '</ComicInfo>')

    def test_merge_preserves_unowned_and_unknown_fields(self):
        existing = b'''<?xml version="1.0"?>
            <ComicInfo custom="kept">
                <Series>Old Series</Series>
                <Writer>Existing Writer</Writer>
                <CustomField customAttr="yes">Custom Value</CustomField>
                <Notes>User note</Notes>
            </ComicInfo>'''
        root = fromstring(build_comicinfo_xml(METADATA, existing))
        self.assertEqual(root.attrib['custom'], 'kept')
        self.assertEqual(root.findtext('Series'), 'Example Series')
        self.assertEqual(root.findtext('Writer'), 'Existing Writer')
        self.assertEqual(root.findtext('CustomField'), 'Custom Value')
        self.assertEqual(root.find('CustomField').attrib['customAttr'], 'yes')
        self.assertEqual(root.findtext('Notes'), f'User note\n{KAPOWARR_NOTE}')

    def test_merge_is_idempotent(self):
        first = build_comicinfo_xml(METADATA)
        second = build_comicinfo_xml(METADATA, first)
        root = fromstring(second)
        self.assertEqual(len(root.findall('Notes')), 1)
        self.assertEqual(root.findtext('Notes'), KAPOWARR_NOTE)

    def test_merge_preserves_default_namespace(self):
        existing = b'<ComicInfo xmlns="urn:test"><Writer>Writer</Writer></ComicInfo>'
        root = fromstring(build_comicinfo_xml(METADATA, existing))
        self.assertEqual(root.findtext('{urn:test}Series'), 'Example Series')
        self.assertEqual(root.findtext('{urn:test}Writer'), 'Writer')
        self.assertIsNone(root.find('Series'))

    def test_missing_values_preserve_existing_fields(self):
        metadata = dict(METADATA, Title=None, Publisher=None)
        existing = b'<ComicInfo><Title>Stale</Title><Publisher>Old</Publisher></ComicInfo>'
        root = fromstring(build_comicinfo_xml(metadata, existing))
        self.assertEqual(root.findtext('Title'), 'Stale')
        self.assertEqual(root.findtext('Publisher'), 'Old')


class ComicInfoArchive(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.filepath = join(self.temp.name, 'issue.cbz')

    def tearDown(self):
        self.temp.cleanup()

    def _create_archive(self, existing_names=()):
        with ZipFile(self.filepath, 'w') as archive:
            archive.writestr('001.jpg', b'image')
            for name in existing_names:
                archive.writestr(name, b'<ComicInfo><Writer>Writer</Writer></ComicInfo>')

    @patch('backend.implementations.comicinfo.get_db')
    @patch('backend.implementations.comicinfo._metadata_for_file', return_value=METADATA)
    def test_write_replaces_duplicate_case_insensitive_entries(
        self, metadata, get_db
    ):
        self._create_archive(('ComicInfo.xml', 'metadata/COMICINFO.XML'))
        result = write_comicinfo(self.filepath)
        self.assertEqual(result.written, 1)
        with ZipFile(self.filepath) as archive:
            comicinfo_names = [
                name for name in archive.namelist()
                if name.rsplit('/', 1)[-1].casefold() == 'comicinfo.xml'
            ]
            self.assertEqual(comicinfo_names, ['ComicInfo.xml'])
            self.assertEqual(archive.read('001.jpg'), b'image')
            root = fromstring(archive.read('ComicInfo.xml'))
            self.assertEqual(root.findtext('Writer'), 'Writer')
        get_db.return_value.execute.assert_called_once()

    @patch('backend.implementations.comicinfo._metadata_for_file', return_value=METADATA)
    def test_corrupt_archive_fails_without_replacing_file(self, metadata):
        original = b'not a zip file'
        with open(self.filepath, 'wb') as file:
            file.write(original)
        result = write_comicinfo(self.filepath)
        self.assertEqual(result.failed, 1)
        with open(self.filepath, 'rb') as file:
            self.assertEqual(file.read(), original)
        with self.assertRaises(BadZipFile):
            ZipFile(self.filepath).testzip()

    def test_non_cbz_is_skipped(self):
        result = write_comicinfo(join(self.temp.name, 'issue.cbr'))
        self.assertEqual(result.skipped, 1)


if __name__ == '__main__':
    unittest.main()
