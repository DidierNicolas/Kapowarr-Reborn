# -*- coding: utf-8 -*-

import unittest
from datetime import datetime

from backend.implementations.weekly_releases import (
    _add_issue_validation,
    _select_match,
    _weekly_title_alias,
    _weekly_title_matches,
)


class WeeklyIssueCover(unittest.TestCase):
    def test_selected_match_keeps_actual_issue_cover(self):
        comic = {
            'query': 'Absolute Batman',
            'issue_number': '22',
            'series_year': 2024,
            'matches': [{
                'comicvine_id': 1,
                'title': 'Absolute Batman',
                'year': 2024,
                'cover_link': 'https://example/series.jpg'
            }]
        }
        issues = {1: [{
            'comicvine_id': 22,
            'issue_number': '22',
            'date': '2026-07-08',
            'cover_link': 'https://example/issue-22.jpg'
        }]}
        pack_date = datetime(2026, 7, 8)

        _add_issue_validation(comic, issues, pack_date)
        selected = _select_match(comic, issues, pack_date)

        self.assertIsNotNone(selected)
        self.assertEqual(
            selected['issue_cover_link'],
            'https://example/issue-22.jpg'
        )


class WeeklyCrossoverAliases(unittest.TestCase):
    def test_amazing_spider_man_branding_matches_canonical_crossover(self):
        solicit = 'Punisher vs. The Amazing Spider-Man'

        self.assertEqual(
            _weekly_title_alias(solicit),
            'Punisher vs. Spider-Man'
        )
        self.assertTrue(_weekly_title_matches(
            solicit,
            'Punisher vs. Spider-Man'
        ))

    def test_regular_amazing_spider_man_is_not_aliased(self):
        self.assertFalse(_weekly_title_matches(
            'The Amazing Spider-Man',
            'Spider-Man'
        ))


if __name__ == '__main__':
    unittest.main()
