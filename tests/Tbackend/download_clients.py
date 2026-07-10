# -*- coding: utf-8 -*-

import unittest

from backend.implementations.download_clients import (
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


if __name__ == '__main__':
    unittest.main()
