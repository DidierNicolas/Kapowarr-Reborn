# -*- coding: utf-8 -*-

import asyncio
import unittest
from unittest.mock import patch

from backend.base.custom_exceptions import EnqueuingDownloadFailure
from backend.base.definitions import EnqueuingDownloadFailureReason
from backend.features.download_queue import DownloadHandler


class BulkEnqueue(unittest.TestCase):
    def test_candidates_are_added_sequentially(self):
        events = []

        class Handler:
            async def add(self, link, volume_id, issue_id, force_match):
                events.append(('start', link))
                await asyncio.sleep(0)
                events.append(('end', link))

        DownloadHandler.add_multiple(Handler(), (
            ('first', 1, None, False),
            ('second', 1, None, False),
        ))

        self.assertEqual(events, [
            ('start', 'first'),
            ('end', 'first'),
            ('start', 'second'),
            ('end', 'second'),
        ])


class TemporaryArticleFailure(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_article_is_not_blocklisted(self):
        class Page:
            def __init__(self, link):
                self.link = link

            async def load_data(self):
                raise EnqueuingDownloadFailure(
                    EnqueuingDownloadFailureReason.WEBPAGE_BROKEN
                )

        class Handler:
            queue = []

            def link_in_queue(self, link):
                return False

            def _DownloadHandler__determine_link_type(self, link):
                return 'gc'

        with (
            patch(
                'backend.features.download_queue.GetComicsPage',
                Page
            ),
            patch(
                'backend.features.download_queue.add_to_blocklist'
            ) as add_to_blocklist
        ):
            result, reason = await DownloadHandler.add(
                Handler(),
                'https://getcomics.org/example/',
                1,
                None,
                False
            )

        self.assertEqual(result, [])
        self.assertEqual(
            reason,
            EnqueuingDownloadFailureReason.WEBPAGE_BROKEN
        )
        add_to_blocklist.assert_not_called()


if __name__ == '__main__':
    unittest.main()
