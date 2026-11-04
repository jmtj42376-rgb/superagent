"""triage_inquiries 的单元测试与命令行端到端测试。"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "triage_inquiries.py"
SAMPLE = REPO_ROOT / "examples" / "inquiries_sample.csv"

sys.path.insert(0, str(REPO_ROOT))

from tools import triage_inquiries  # noqa: E402

HEADER = ["id", "country", "product", "quantity", "timeline_days"]


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def run_cli(input_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(input_path), str(output_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


class ClassifyInquiryTests(unittest.TestCase):
    def test_a_at_threshold(self) -> None:
        self.assertEqual(
            triage_inquiries.classify_inquiry("Kazakhstan", "lowbed", "3", "30")[0],
            "A",
        )

    def test_a_above_threshold(self) -> None:
        self.assertEqual(
            triage_inquiries.classify_inquiry("Uzbekistan", "flatbed", "10", "1")[0],
            "A",
        )

    def test_all_target_country_product_combinations_are_a(self) -> None:
        for country in sorted(triage_inquiries.TARGET_COUNTRIES):
            for product in sorted(triage_inquiries.TARGET_PRODUCTS):
                with self.subTest(country=country, product=product):
                    priority, _ = triage_inquiries.classify_inquiry(
                        country, product, "3", "30"
                    )
                    self.assertEqual(priority, "A")

    def test_b_quantity_below_threshold(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Uzbekistan", "flatbed", "2", "20"
        )
        self.assertEqual(priority, "B")
        self.assertIn("数量", reason)

    def test_b_timeline_above_threshold(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Kazakhstan", "lowbed", "3", "31"
        )
        self.assertEqual(priority, "B")
        self.assertIn("交期", reason)

    def test_b_below_both_thresholds(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Uzbekistan", "lowbed", "2", "45"
        )
        self.assertEqual(priority, "B")
        self.assertIn("数量", reason)
        self.assertIn("交期", reason)

    def test_b_missing_fields_are_named(self) -> None:
        cases = [
            ("", "lowbed", "3", "30", "country"),
            ("Kazakhstan", "", "3", "30", "product"),
            ("Kazakhstan", "lowbed", "", "30", "quantity"),
            ("Kazakhstan", "lowbed", "3", "", "timeline_days"),
        ]
        for country, product, quantity, timeline, field in cases:
            with self.subTest(field=field):
                priority, reason = triage_inquiries.classify_inquiry(
                    country, product, quantity, timeline
                )
                self.assertEqual(priority, "B")
                self.assertIn(field, reason)

    def test_b_reports_all_missing_fields(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry("", "", "", "")
        self.assertEqual(priority, "B")
        for field in ("country", "product", "quantity", "timeline_days"):
            with self.subTest(field=field):
                self.assertIn(field, reason)

    def test_b_non_positive_or_non_integer_quantity(self) -> None:
        for raw in ("0", "-1", "3.5", "abc", "1_0"):
            with self.subTest(quantity=raw):
                priority, reason = triage_inquiries.classify_inquiry(
                    "Kazakhstan", "lowbed", raw, "10"
                )
                self.assertEqual(priority, "B")
                self.assertIn("quantity", reason)

    def test_b_non_positive_or_non_integer_timeline(self) -> None:
        for raw in ("0", "-5", "30.5", "abc"):
            with self.subTest(timeline=raw):
                priority, reason = triage_inquiries.classify_inquiry(
                    "Kazakhstan", "lowbed", "5", raw
                )
                self.assertEqual(priority, "B")
                self.assertIn("timeline_days", reason)

    def test_b_reports_both_invalid_numeric_fields(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Kazakhstan", "lowbed", "abc", "0"
        )
        self.assertEqual(priority, "B")
        self.assertIn("quantity", reason)
        self.assertIn("timeline_days", reason)

    def test_oversized_numeric_values_are_invalid_with_short_reason(self) -> None:
        huge = "9" * 5000
        for quantity, timeline, field in (
            (huge, "30", "quantity"),
            ("4", huge, "timeline_days"),
        ):
            with self.subTest(field=field):
                priority, reason = triage_inquiries.classify_inquiry(
                    "Kazakhstan", "lowbed", quantity, timeline
                )
                self.assertEqual(priority, "B")
                self.assertIn(field, reason)
                self.assertNotIn(huge, reason)
                self.assertLess(len(reason), 200)

    def test_c_non_target_country(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Germany", "lowbed", "10", "7"
        )
        self.assertEqual(priority, "C")
        self.assertIn("Germany", reason)

    def test_c_non_target_product(self) -> None:
        priority, reason = triage_inquiries.classify_inquiry(
            "Kazakhstan", "van", "10", "7"
        )
        self.assertEqual(priority, "C")
        self.assertIn("van", reason)

    def test_c_takes_precedence_over_missing_or_invalid_fields(self) -> None:
        for country, product, quantity, timeline in (
            ("Germany", "", "", ""),
            ("", "van", "", ""),
            ("germany", "lowbed", "0", "abc"),
            ("Kazakhstan", "van", "", ""),
        ):
            with self.subTest(country=country, product=product):
                priority, _ = triage_inquiries.classify_inquiry(
                    country, product, quantity, timeline
                )
                self.assertEqual(priority, "C")

    def test_country_and_product_are_trimmed_and_case_insensitive(self) -> None:
        for country, product in (
            ("  kAzAkHsTaN  ", "  LoWbEd "),
            ("UZBEKISTAN", "FLATBED"),
            ("Kyrgyzstan\t", "\tTipper"),
        ):
            with self.subTest(country=country, product=product):
                priority, _ = triage_inquiries.classify_inquiry(
                    country, product, "3", "30"
                )
                self.assertEqual(priority, "A")

    def test_reason_is_never_empty(self) -> None:
        cases = [
            ("Kazakhstan", "lowbed", "3", "30"),
            ("Uzbekistan", "flatbed", "2", "20"),
            ("Germany", "lowbed", "10", "7"),
            ("", "", "", ""),
            ("Kazakhstan", "lowbed", "abc", "31"),
        ]
        for case in cases:
            with self.subTest(case=case):
                priority, reason = triage_inquiries.classify_inquiry(*case)
                self.assertIn(priority, {"A", "B", "C"})
                self.assertTrue(reason.strip())


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.tmp = Path(self._temp.name)

    def test_required_sample_outcomes(self) -> None:
        rows = [
            ["INQ-1", "Kazakhstan", "lowbed", "3", "30", "边界"],
            ["INQ-2", "Uzbekistan", "flatbed", "2", "20", "数量少"],
            ["INQ-3", "Kazakhstan", "lowbed", "3", "31", "交期长"],
            ["INQ-4", "Germany", "lowbed", "10", "7", "非目标国家"],
            ["INQ-5", "Uzbekistan", "tipper", "", "10", "空数量"],
        ]
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, HEADER + ["note"], rows)

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)

        self.assertEqual(output[0], HEADER + ["note", "priority", "reason"])
        self.assertEqual(len(output), len(rows) + 1)
        by_id = {row[0]: row for row in output[1:]}
        expected = {"INQ-1": "A", "INQ-2": "B", "INQ-3": "B", "INQ-4": "C", "INQ-5": "B"}
        for inquiry_id, priority in expected.items():
            with self.subTest(inquiry_id=inquiry_id):
                self.assertEqual(by_id[inquiry_id][6], priority)
                self.assertTrue(by_id[inquiry_id][7].strip())

    def test_sample_file_matches_required_outcomes(self) -> None:
        target = self.tmp / "sample_out.csv"
        result = run_cli(SAMPLE, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        header = output[0]
        priority_index = header.index("priority")
        reason_index = header.index("reason")
        by_id = {row[0]: row for row in output[1:]}
        expected = {
            "INQ-1001": "A",
            "INQ-1002": "B",
            "INQ-1003": "B",
            "INQ-1004": "C",
            "INQ-1005": "B",
            "INQ-1006": "A",
            "INQ-1007": "A",
            "INQ-1008": "C",
            "INQ-1009": "B",
            "INQ-1010": "B",
        }
        for inquiry_id, priority in expected.items():
            with self.subTest(inquiry_id=inquiry_id):
                row = by_id[inquiry_id]
                self.assertEqual(row[priority_index], priority)
                self.assertTrue(row[reason_index].strip())

    def test_preserves_input_columns_and_row_order(self) -> None:
        rows = [
            ["INQ-20", "Germany", "lowbed", "10", "7", "second"],
            ["INQ-10", "Kazakhstan", "lowbed", "3", "30", "first"],
        ]
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, ["id", "country", "product", "quantity", "timeline_days", "note"], rows)

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)

        self.assertEqual(
            output[0],
            ["id", "country", "product", "quantity", "timeline_days", "note", "priority", "reason"],
        )
        self.assertEqual([row[0] for row in output[1:]], ["INQ-20", "INQ-10"])
        self.assertEqual([row[5] for row in output[1:]], ["second", "first"])
        self.assertEqual([row[6] for row in output[1:]], ["C", "A"])

    def test_empty_and_bad_rows_do_not_abort_batch(self) -> None:
        rows = [
            ["INQ-30", "Kazakhstan", "lowbed", "3", "30"],
            ["INQ-31", "Uzbekistan", "tipper", "", "10"],
            ["INQ-32", "Kazakhstan", "lowbed", "abc", "20"],
            ["INQ-33", "", "", "", ""],
            ["INQ-34", "Germany", "van", "0", "0"],
            ["INQ-35", "Tajikistan", "flatbed", "4", "30"],
        ]
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, HEADER, rows)

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        self.assertEqual(len(output), len(rows) + 1)
        self.assertEqual([row[0] for row in output[1:]], [row[0] for row in rows])
        self.assertEqual(
            [row[-2] for row in output[1:]],
            ["A", "B", "B", "B", "C", "A"],
        )
        self.assertTrue(all(row[-1].strip() for row in output[1:]))

    def test_short_row_is_padded_and_triaged(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_text(
            "id,country,product,quantity,timeline_days\nINQ-40,Kazakhstan,lowbed\n",
            encoding="utf-8",
        )

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        self.assertEqual(len(output), 2)
        row = output[1]
        self.assertEqual(len(row), 7)
        self.assertEqual(row[3], "")
        self.assertEqual(row[4], "")
        self.assertEqual(row[5], "B")
        self.assertIn("quantity", row[6])
        self.assertIn("timeline_days", row[6])

    def test_over_wide_row_is_b_truncated_and_batch_continues(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_text(
            "id,country,product,quantity,timeline_days\n"
            "INQ-70,Kazakhstan,lowbed,3,30,unexpected\n"
            "INQ-71,Uzbekistan,flatbed,4,20\n",
            encoding="utf-8",
        )

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        self.assertEqual(output[0], HEADER + ["priority", "reason"])
        self.assertEqual(len(output), 3)

        malformed = output[1]
        self.assertEqual(len(malformed), 7)
        self.assertEqual(
            malformed[:5], ["INQ-70", "Kazakhstan", "lowbed", "3", "30"]
        )
        self.assertEqual(malformed[5], "B")
        self.assertIn("多余字段", malformed[6])
        self.assertIn("unexpected", malformed[6])

        normal = output[2]
        self.assertEqual(len(normal), 7)
        self.assertEqual(normal[5], "A")

    def test_over_wide_row_with_empty_extra_field_is_b(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_text(
            "id,country,product,quantity,timeline_days\n"
            "INQ-72,Kazakhstan,lowbed,3,30,\n"
            "INQ-73,Uzbekistan,flatbed,4,20\n",
            encoding="utf-8",
        )

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)

        malformed = output[1]
        self.assertEqual(len(malformed), 7)
        self.assertEqual(malformed[5], "B")
        self.assertIn("多余字段", malformed[6])
        self.assertIn("（空）", malformed[6])
        self.assertEqual(output[2][5], "A")

    def test_oversized_quantity_does_not_abort_batch(self) -> None:
        huge = "9" * 5000
        rows = [
            ["INQ-80", "Kazakhstan", "lowbed", huge, "30"],
            ["INQ-81", "Uzbekistan", "flatbed", "4", "20"],
        ]
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, HEADER, rows)

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        self.assertEqual(len(output), 3)

        malformed = output[1]
        self.assertEqual(len(malformed), 7)
        self.assertEqual(malformed[3], huge)
        self.assertEqual(malformed[5], "B")
        self.assertIn("quantity", malformed[6])
        self.assertNotIn(huge, malformed[6])
        self.assertLess(len(malformed[6]), 200)

        normal = output[2]
        self.assertEqual(normal[5], "A")

    def test_header_only_input_succeeds(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, HEADER, [])

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read_csv(target), [HEADER + ["priority", "reason"]])

    def test_bom_input_is_accepted(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_bytes(
            b"\xef\xbb\xbfid,country,product,quantity,timeline_days\n"
            b"INQ-50,Kazakhstan,lowbed,3,30\n"
        )

        result = run_cli(source, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = read_csv(target)
        self.assertEqual(output[0], HEADER + ["priority", "reason"])
        self.assertEqual(output[1][-2], "A")

    def test_missing_required_header_fails_without_output(self) -> None:
        all_headers = list(HEADER)
        for missing in all_headers:
            with self.subTest(missing=missing):
                directory = self.tmp / f"missing_{missing}"
                directory.mkdir()
                source = directory / "in.csv"
                target = directory / "out.csv"
                header = [name for name in all_headers if name != missing]
                write_csv(source, header, [["INQ-60"] + ["x"] * (len(header) - 1)])

                result = run_cli(source, target)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("必填表头", result.stderr)
                self.assertIn(missing, result.stderr)
                self.assertFalse(target.exists())

    def test_missing_header_does_not_overwrite_existing_output(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        write_csv(source, ["id", "country", "product", "quantity"], [["INQ-61", "Kazakhstan", "lowbed", "3"]])
        target.write_text("SENTINEL", encoding="utf-8")

        result = run_cli(source, target)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "SENTINEL")

    def test_empty_input_file_fails_without_output(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_text("", encoding="utf-8")

        result = run_cli(source, target)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("必填表头", result.stderr)
        self.assertFalse(target.exists())

    def test_invalid_utf8_input_fails_without_output(self) -> None:
        source = self.tmp / "in.csv"
        target = self.tmp / "out.csv"
        source.write_bytes(b"\xff\xfeid,country,product,quantity,timeline_days\n")

        result = run_cli(source, target)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UTF-8", result.stderr)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
