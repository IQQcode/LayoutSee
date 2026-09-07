from __future__ import annotations

import unittest

from layoutsee_core.server import derive_session_token

GOLDEN_TOKEN = "a8151948d84f365c4722324e732be43b0e0a5e2558fc07a22b1e0057abb1ee77"


class SessionTokenTest(unittest.TestCase):
    def test_token_matches_javascript_golden_value(self) -> None:
        self.assertEqual(derive_session_token("a" * 64), GOLDEN_TOKEN)

    def test_token_changes_with_nonce(self) -> None:
        self.assertNotEqual(derive_session_token("a" * 64), derive_session_token("b" * 64))


if __name__ == "__main__":
    unittest.main()
