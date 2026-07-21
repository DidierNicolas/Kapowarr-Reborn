# -*- coding: utf-8 -*-

import unittest
from unittest.mock import Mock, patch

from backend.base.definitions import BlocklistReasonID
from backend.implementations.blocklist import blocklist_contains


class BlocklistMatching(unittest.TestCase):
    def test_automatic_page_failures_do_not_suppress_search_results(self):
        database = Mock()
        database.execute.return_value.exists.return_value = None

        with patch(
            'backend.implementations.blocklist.get_db',
            return_value=database
        ):
            blocklist_contains('https://getcomics.org/example/')

        sql, parameters = database.execute.call_args.args
        self.assertIn('reason = :added_by_user', sql)
        self.assertEqual(
            parameters['added_by_user'],
            BlocklistReasonID.ADDED_BY_USER.value
        )


if __name__ == '__main__':
    unittest.main()
