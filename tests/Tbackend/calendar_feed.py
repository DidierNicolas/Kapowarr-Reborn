# -*- coding: utf-8 -*-

import unittest

from backend.implementations.calendar_feed import build_icalendar


class CalendarFeed(unittest.TestCase):
    def test_builds_all_day_issue_and_tentative_events(self):
        content = build_icalendar([
            {
                'id': 10,
                'volume_id': 2,
                'issue_number': '5',
                'title': 'Part One',
                'date': '2026-07-08',
                'monitored': 1,
                'downloaded': 0,
                'volume_title': 'Black Cat',
                'source': None,
                'source_url': None,
                'tentative': 0
            },
            {
                'id': None,
                'volume_id': 3,
                'issue_number': '1',
                'title': None,
                'date': '2026-07-15',
                'monitored': 1,
                'downloaded': 0,
                'volume_title': 'New Series',
                'source': 'Marvel',
                'source_url': 'https://example.test/release',
                'tentative': 1
            }
        ], 'https://kapowarr.test')
        text = content.decode('utf-8')

        self.assertTrue(text.startswith('BEGIN:VCALENDAR\r\n'))
        self.assertTrue(text.endswith('END:VCALENDAR\r\n'))
        self.assertEqual(text.count('BEGIN:VEVENT'), 2)
        self.assertIn('DTSTART;VALUE=DATE:20260708', text)
        self.assertIn('DTEND;VALUE=DATE:20260709', text)
        self.assertIn('SUMMARY:Black Cat #5 - Part One', text)
        self.assertIn('URL:https://kapowarr.test/volumes/2', text)
        self.assertIn('STATUS:TENTATIVE', text)
        self.assertIn('URL:https://example.test/release', text)

    def test_event_uid_is_stable(self):
        entry = {
            'id': 10,
            'volume_id': 2,
            'issue_number': '5',
            'title': None,
            'date': '2026-07-08',
            'monitored': 0,
            'downloaded': 0,
            'volume_title': 'Black Cat',
            'tentative': 0
        }
        first = build_icalendar([entry], 'https://one.test').decode()
        second = build_icalendar([entry], 'https://two.test').decode()
        first_uid = next(line for line in first.splitlines() if line.startswith('UID:'))
        second_uid = next(line for line in second.splitlines() if line.startswith('UID:'))

        self.assertEqual(first_uid, second_uid)


if __name__ == '__main__':
    unittest.main()
