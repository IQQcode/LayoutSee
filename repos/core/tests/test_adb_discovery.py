from __future__ import annotations

import unittest
from unittest import mock

from layoutsee_core.adb import ADB_CANDIDATE_PATHS, find_adb


class AdbDiscoveryTest(unittest.TestCase):
    def test_finds_adb_from_candidate_paths_when_not_in_path(self) -> None:
        with mock.patch("layoutsee_core.adb.shutil.which", return_value=None):
            with mock.patch("layoutsee_core.adb.Path.is_file", return_value=True):
                with mock.patch("layoutsee_core.adb.os.access", return_value=True):
                    found = find_adb()
        self.assertEqual(found, ADB_CANDIDATE_PATHS[0])

    def test_prefers_configured_path_when_valid(self) -> None:
        with mock.patch("layoutsee_core.adb.Path.is_file", return_value=True):
            with mock.patch("layoutsee_core.adb.os.access", return_value=True):
                found = find_adb("/custom/adb")
        self.assertEqual(found, "/custom/adb")

    def test_returns_none_when_nothing_found(self) -> None:
        with mock.patch("layoutsee_core.adb.shutil.which", return_value=None):
            with mock.patch("layoutsee_core.adb.Path.is_file", return_value=False):
                self.assertIsNone(find_adb())


if __name__ == "__main__":
    unittest.main()
