from __future__ import annotations

import unittest

from layoutsee_core.adb import AdbClient, AdbResult
from layoutsee_core.errors import CoreError


class StubAdb(AdbClient):
    """用固定输出替换 subprocess，只验证包管理的参数拼装与结果判定。"""

    def __init__(self, responses: dict[str, AdbResult]) -> None:
        super().__init__(executable="/stub/adb")
        self.responses = responses
        self.calls: list[list[str]] = []

    @property
    def executable(self) -> str | None:
        return "/stub/adb"

    def run(self, args, *, serial=None, timeout=None, check=True):  # type: ignore[override]
        self.calls.append(list(args))
        for key, result in self.responses.items():
            if key in " ".join(args):
                return result
        return AdbResult(stdout=b"", stderr=b"", returncode=0)


def ok(text: str) -> AdbResult:
    return AdbResult(stdout=text.encode("utf-8"), stderr=b"", returncode=0)


class PackageManagerTest(unittest.TestCase):
    def test_apps_marks_system_packages_only_when_requested(self) -> None:
        client = StubAdb({
            "pm list packages -3": ok("package:com.demo.app\npackage:com.demo.other"),
            "pm list packages": ok("package:com.demo.app\npackage:com.demo.other\npackage:com.android.settings"),
        })
        third_party = client.apps("SER", "")
        self.assertEqual([item["packageName"] for item in third_party], ["com.demo.app", "com.demo.other"])
        self.assertFalse(any(item["system"] for item in third_party))

        everything = client.apps("SER", "", True)
        self.assertEqual(len(everything), 3)
        system = [item for item in everything if item["system"]]
        self.assertEqual([item["packageName"] for item in system], ["com.android.settings"])

    def test_apps_query_filters_case_insensitively(self) -> None:
        client = StubAdb({"pm list packages -3": ok("package:com.demo.app\npackage:org.other")})
        items = client.apps("SER", "DEMO")
        self.assertEqual([item["packageName"] for item in items], ["com.demo.app"])

    def test_clear_app_passes_package_and_accepts_success(self) -> None:
        client = StubAdb({"pm clear": ok("Success")})
        result = client.action("SER", "clear_app", {"packageName": "com.demo.app"})
        self.assertTrue(result["accepted"])
        self.assertIn(["shell", "pm", "clear", "com.demo.app"], client.calls)

    def test_uninstall_failure_without_success_marker_raises(self) -> None:
        client = StubAdb({"pm uninstall": ok("Failure [DELETE_FAILED_INTERNAL_ERROR]")})
        with self.assertRaises(CoreError) as ctx:
            client.action("SER", "uninstall_app", {"packageName": "com.android.settings"})
        self.assertEqual(ctx.exception.code, "PERMISSION_REQUIRED")

    def test_illegal_package_name_is_rejected_before_adb(self) -> None:
        client = StubAdb({})
        for bad in ("", "com.demo app", "com.demo;rm -rf /", "--user"):
            with self.subTest(package=bad):
                with self.assertRaises(CoreError) as ctx:
                    client.action("SER", "clear_app", {"packageName": bad})
                self.assertEqual(ctx.exception.code, "INVALID_ARGUMENT")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
