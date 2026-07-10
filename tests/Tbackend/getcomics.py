# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from backend.base.definitions import GCDownloadSource
from backend.implementations.getcomics import (
    __extract_button_links as extract_button_links,
)


class ExtractGetComicsLinks(unittest.TestCase):
    @patch(
        'backend.implementations.getcomics.blocklist_contains',
        return_value=False
    )
    def test_current_aio_pulse_buttons(self, _blocklist_contains):
        body = BeautifulSoup("""
            <section class="post-contents">
                <p><strong>Absolute Batman #22</strong><br>
                <strong>Language :</strong> English |
                <strong>Image Format :</strong> JPG |
                <strong>Year :</strong>&nbsp;2026 |
                <strong>Size :</strong> 57 MB</p>
                <div class="aio-pulse">
                    <a href="https://getcomics.org/dls/direct-link">
                        DOWNLOAD NOW
                    </a>
                </div>
                <div class="aio-pulse">
                    <a href="https://getcomics.org/dls/pixeldrain-link">
                        PIXELDRAIN
                    </a>
                </div>
                <hr>
            </section>
        """, "html.parser").section

        groups = extract_button_links(body, False)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['web_sub_title'], 'Absolute Batman #22')
        self.assertEqual(groups[0]['info']['issue_number'], 22.0)
        self.assertEqual(groups[0]['info']['year'], 2026)
        self.assertEqual(
            groups[0]['links'],
            {
                GCDownloadSource.GETCOMICS: [
                    'https://getcomics.org/dls/direct-link'
                ],
                GCDownloadSource.PIXELDRAIN: [
                    'https://getcomics.org/dls/pixeldrain-link'
                ]
            }
        )

    @patch(
        'backend.implementations.getcomics.blocklist_contains',
        return_value=False
    )
    def test_legacy_aio_button_center_buttons(self, _blocklist_contains):
        body = BeautifulSoup("""
            <section class="post-contents">
                <p>Batman #1<br>Language : English | Year : 2025</p>
                <div class="aio-button-center">
                    <a href="https://getcomics.org/dls/direct-link">
                        DOWNLOAD NOW
                    </a>
                </div>
                <hr>
            </section>
        """, "html.parser").section

        groups = extract_button_links(body, False)

        self.assertEqual(len(groups), 1)
        self.assertEqual(
            groups[0]['links'][GCDownloadSource.GETCOMICS],
            ['https://getcomics.org/dls/direct-link']
        )


if __name__ == '__main__':
    unittest.main()
