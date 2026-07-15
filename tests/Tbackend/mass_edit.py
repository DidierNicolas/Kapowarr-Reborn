# -*- coding: utf-8 -*-

import unittest
from unittest.mock import call, patch

from backend.features.mass_edit import MassEditorComicInfo


class MassEditorComicInfoTest(unittest.TestCase):
    @patch('backend.features.mass_edit.WebSocket')
    @patch('backend.features.mass_edit.write_comicinfo_for_volume')
    @patch('backend.features.mass_edit.iter_commit', side_effect=lambda values: values)
    def test_writes_comicinfo_for_each_selected_volume(
        self, iter_commit, write_comicinfo, websocket
    ):
        MassEditorComicInfo([4, 8]).run()

        iter_commit.assert_called_once_with([4, 8])
        self.assertEqual(write_comicinfo.call_args_list, [call(4), call(8)])
        self.assertEqual(websocket.return_value.emit.call_count, 2)


if __name__ == '__main__':
    unittest.main()
