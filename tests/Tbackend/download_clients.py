# -*- coding: utf-8 -*-

import unittest
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from requests import ConnectionError

from backend.base.definitions import DownloadState
from backend.implementations.download_clients import (
    BaseDirectDownload,
    _get_pixeldrain_paid_transfer_state,
)


class PixelDrainTransferState(unittest.TestCase):
    def test_current_subscription_cap_takes_precedence(self):
        state = _get_pixeldrain_paid_transfer_state({
            'monthly_transfer_used': 342011840,
            'monthly_transfer_cap': 0,
            'subscription': {
                'type': 'patreon',
                'monthly_transfer_cap': 4000000000000
            }
        })

        self.assertEqual(state, (342011840, 4000000000000))

    def test_legacy_top_level_cap_is_supported(self):
        state = _get_pixeldrain_paid_transfer_state({
            'monthly_transfer_used': 100,
            'monthly_transfer_cap': 1000,
            'subscription': {'type': 'premium'}
        })

        self.assertEqual(state, (100, 1000))

    def test_unlimited_cap(self):
        state = _get_pixeldrain_paid_transfer_state({
            'monthly_transfer_used': 100,
            'subscription': {'monthly_transfer_cap': -1}
        })

        self.assertEqual(state, (100, float('inf')))


class DirectDownloadFailures(unittest.TestCase):
    def test_connection_failure_does_not_leave_download_running(self):
        with TemporaryDirectory() as folder:
            download = BaseDirectDownload.__new__(BaseDirectDownload)
            download._state = DownloadState.QUEUED_STATE
            download._files = [folder + '/test.cbz']
            download._supports_range_header = False
            download._download_link = 'https://example.invalid/test.cbz'
            download._size = 1
            download._progress = 0.0
            download._speed = 0.0
            download._BaseDirectDownload__r = None
            download._fetch_pure_link = Mock(
                side_effect=ConnectionError('connection failed')
            )

            with patch(
                'backend.implementations.download_clients.WebSocket'
            ):
                download.run()

        self.assertEqual(download.state, DownloadState.FAILED_STATE)


if __name__ == '__main__':
    unittest.main()
