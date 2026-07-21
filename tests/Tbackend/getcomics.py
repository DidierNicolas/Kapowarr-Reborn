# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from backend.base.definitions import GCDownloadSource
from backend.implementations.getcomics import (
    _fetch_search_page,
    __extract_button_links as extract_button_links,
    search_getcomics,
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


class GetComicsSearchRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_429_starts_cooldown_for_following_searches(self):
        class Response:
            status = 429
            headers = {}
            ok = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class Session:
            calls = 0

            def get(self, url, params=None):
                self.calls += 1
                return Response()

        session = Session()
        with (
            patch(
                'backend.implementations.getcomics.'
                '_next_getcomics_search_request',
                0.0
            ),
            patch(
                'backend.implementations.getcomics.'
                '_getcomics_search_cooldown_until',
                0.0
            ),
            patch(
                'backend.implementations.getcomics.'
                'GETCOMICS_RATE_LIMIT_COOLDOWN',
                60.0
            )
        ):
            first = await _fetch_search_page(session, 'https://example', 'x')
            second = await _fetch_search_page(session, 'https://example', 'y')

        self.assertEqual(first, '')
        self.assertEqual(second, '')
        self.assertEqual(session.calls, 1)

    async def test_page_limit_prevents_deep_automatic_pagination(self):
        class Response:
            status = 200
            headers = {}
            ok = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def text(self):
                return (
                    '<a class="page-numbers">1</a>'
                    '<a class="page-numbers">2</a>'
                    '<a class="page-numbers">10</a>'
                )

        class Session:
            calls = 0

            def get(self, url, params=None):
                self.calls += 1
                return Response()

        session = Session()
        with (
            patch(
                'backend.implementations.getcomics.'
                '_next_getcomics_search_request',
                0.0
            ),
            patch(
                'backend.implementations.getcomics.'
                '_getcomics_search_cooldown_until',
                0.0
            )
        ):
            await search_getcomics(session, 'X-Men #10', max_pages=1)

        self.assertEqual(session.calls, 1)


if __name__ == '__main__':
    unittest.main()
