# -*- coding: utf-8 -*-

import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.base.custom_exceptions import CVRateLimitReached
from backend.implementations.comicvine import ComicVine


class ComicVineSearchCache(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cv = object.__new__(ComicVine)

    async def test_fresh_cache_avoids_api_request(self):
        cached = [{'id': 1}]
        with (
            patch.object(
                self.cv,
                '_ComicVine__get_cached_search',
                return_value=cached
            ),
            patch.object(
                self.cv,
                '_ComicVine__search_query',
                new=AsyncMock()
            ) as api_search,
            patch.object(
                self.cv,
                '_ComicVine__format_search_output',
                return_value=['cached']
            )
        ):
            result = await self.cv.search_volumes('  Absolute   Batman  ')

        self.assertEqual(result, ['cached'])
        api_search.assert_not_awaited()

    async def test_rate_limit_uses_stale_cache(self):
        cached = [{'id': 1}]
        with (
            patch.object(
                self.cv,
                '_ComicVine__get_cached_search',
                side_effect=(None, cached)
            ),
            patch.object(
                self.cv,
                '_ComicVine__search_query',
                new=AsyncMock(side_effect=CVRateLimitReached())
            ),
            patch.object(
                self.cv,
                '_ComicVine__format_search_output',
                return_value=['stale']
            )
        ):
            result = await self.cv.search_volumes('Absolute Batman')

        self.assertEqual(result, ['stale'])

    async def test_api_result_is_cached(self):
        api_result = [{'id': 1}]
        store = Mock()
        with (
            patch.object(
                self.cv,
                '_ComicVine__get_cached_search',
                return_value=None
            ),
            patch.object(
                self.cv,
                '_ComicVine__search_query',
                new=AsyncMock(return_value=api_result)
            ),
            patch.object(
                self.cv,
                '_ComicVine__store_cached_search',
                store
            ),
            patch.object(
                self.cv,
                '_ComicVine__format_search_output',
                return_value=['live']
            )
        ):
            result = await self.cv.search_volumes('Absolute Batman')

        self.assertEqual(result, ['live'])
        store.assert_called_once_with('Absolute Batman', api_result)


if __name__ == '__main__':
    unittest.main()
