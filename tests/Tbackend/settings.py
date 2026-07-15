# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.internals.settings import Settings


class SettingsPersistence(unittest.TestCase):
    @patch('backend.internals.settings.commit')
    @patch('backend.internals.settings.get_db')
    def test_comicinfo_setting_is_upserted_and_committed(
        self, get_db, commit
    ):
        cursor = get_db.return_value
        settings = object.__new__(Settings)
        settings._Settings__format_value = MagicMock(
            side_effect=lambda _key, value, _public: value
        )
        settings._Settings__validate_settings = MagicMock()
        settings.get_settings = MagicMock(
            return_value=SimpleNamespace(log_level=20)
        )
        settings.clear_cache = MagicMock()

        settings.update({'write_comicinfo': True}, from_public=True)

        values = list(cursor.executemany.call_args.args[1])
        self.assertEqual(values, [('write_comicinfo', True)])
        commit.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
