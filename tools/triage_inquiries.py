#!/usr/bin/env python3
"""按 A/B/C 给挂车询盘 CSV 分级。

用法：
    python3 tools/triage_inquiries.py INPUT.csv OUTPUT.csv

规则：
    C：国家或产品有填写但不在目标市场/品类；
    B：国家、产品、数量或交期缺失，数量/交期不是正整数，或满足匹配但未达 A 阈值；
    A：国家、产品匹配，数量 >= 3 且交期 <= 30 天。

输出保留输入列和行顺序，并在末尾追加 priority,reason 两列。
仅使用 Python 标准库，输入输出均为 UTF-8 CSV。
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

REQUIRED_HEADERS: tuple[str, ...] = (
    "id",
    "country",
    "product",
    "quantity",
    "timeline_days",
)
OUTPUT_HEADERS: tuple[str, ...] = ("priority", "reason")

TARGET_COUNTRIES = frozenset(
    {
        "kazakhstan",
        "uzbekistan",
        "kyrgyzstan",
        "tajikistan",
        "turkmenistan",
    }
)
TARGET_PRODUCTS = frozenset({"lowbed", "flatbed", "tipper"})

MIN_QUANTITY = 3
MAX_TIMELINE_DAYS = 30

# ASCII 数字串，避免把 "+3"、"3.0"、"3_0"、Unicode 数字等当作正整数。
_POSITIVE_INT_RE = re.compile(r"[0-9]+")
_MISSING_HEADER_MESSAGE = (
    "缺少必填表头：{missing}。必填表头为：{required}"
)

EXIT_OK = 0
EXIT_ERROR = 2


class TriageError(Exception):
    """输入/输出错误，由命令行入口转换为非零退出码。"""


def _positive_int(raw: str) -> int | None:
    """把去空白后的 ASCII 数字串转成正整数，失败返回 None。"""
    text = raw.strip()
    if not _POSITIVE_INT_RE.fullmatch(text):
        return None
    value = int(text)
    return value if value > 0 else None


def classify_inquiry(
    country: str,
    product: str,
    quantity: str,
    timeline_days: str,
) -> tuple[str, str]:
    """按规则返回 ``(priority, reason)``。

    参数均为 CSV 原始字符串；国家/产品去首尾空白并忽略大小写，
    数量/交期去首尾空白后要求为正整数。
    """
    country_value = country.strip()
    product_value = product.strip()
    country_key = country_value.casefold()
    product_key = product_value.casefold()

    # C 优先：只要国家或产品明确填写且不在目标列表，直接判 C。
    non_target: list[str] = []
    if country_key and country_key not in TARGET_COUNTRIES:
        non_target.append(f"国家不在目标市场：{country_value}")
    if product_key and product_key not in TARGET_PRODUCTS:
        non_target.append(f"产品不在目标品类：{product_value}")
    if non_target:
        return "C", "；".join(non_target)

    # 缺失或无效字段判 B，并列出具体字段。
    missing: list[str] = []
    invalid: list[str] = []
    fields = (
        ("country", country),
        ("product", product),
        ("quantity", quantity),
        ("timeline_days", timeline_days),
    )
    for name, raw in fields:
        if not raw.strip():
            missing.append(name)

    quantity_value: int | None = None
    timeline_value: int | None = None
    quantity_text = quantity.strip()
    timeline_text = timeline_days.strip()
    if quantity_text:
        quantity_value = _positive_int(quantity_text)
        if quantity_value is None:
            invalid.append(f"quantity={quantity_text}")
    if timeline_text:
        timeline_value = _positive_int(timeline_text)
        if timeline_value is None:
            invalid.append(f"timeline_days={timeline_text}")

    if missing or invalid:
        parts: list[str] = []
        if missing:
            parts.append("缺少必填字段：" + ", ".join(missing))
        if invalid:
            parts.append("无效字段（需为正整数）：" + ", ".join(invalid))
        return "B", "；".join(parts)

    # 到这里国家/产品匹配且数量/交期均为正整数。
    assert quantity_value is not None and timeline_value is not None
    below: list[str] = []
    if quantity_value < MIN_QUANTITY:
        below.append(f"数量 {quantity_value} 低于 {MIN_QUANTITY}")
    if timeline_value > MAX_TIMELINE_DAYS:
        below.append(f"交期 {timeline_value} 天超过 {MAX_TIMELINE_DAYS} 天")
    if below:
        return "B", "信息完整，但" + "；".join(below)

    return (
        "A",
        "信息完整，"
        f"数量 {quantity_value} >= {MIN_QUANTITY} 且交期 {timeline_value} 天 <= {MAX_TIMELINE_DAYS} 天",
    )


def _read_input(input_path: Path) -> tuple[list[str], list[list[str]]]:
    """读取 UTF-8 CSV，返回表头与全部数据行。"""
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise TriageError(
                    _MISSING_HEADER_MESSAGE.format(
                        missing=", ".join(REQUIRED_HEADERS),
                        required=", ".join(REQUIRED_HEADERS),
                    )
                ) from None
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise TriageError(f"输入文件不是有效的 UTF-8 编码：{exc}") from exc
    except csv.Error as exc:
        raise TriageError(f"输入 CSV 格式无法解析：{exc}") from exc
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise TriageError(f"无法读取输入文件 {input_path}：{detail}") from exc
    return header, rows


def _missing_headers(header: Sequence[str]) -> list[str]:
    present = set(header)
    return [name for name in REQUIRED_HEADERS if name not in present]


def triage_rows(
    header: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> list[list[str]]:
    """为每行追加 priority/reason；短行补齐，保持原有列与行顺序。"""
    indexes = {name: header.index(name) for name in REQUIRED_HEADERS}
    width = len(header)
    output: list[list[str]] = []
    for row in rows:
        cells = list(row)
        if len(cells) < width:
            cells.extend([""] * (width - len(cells)))

        def cell(name: str) -> str:
            index = indexes[name]
            return cells[index] if index < len(cells) else ""

        priority, reason = classify_inquiry(
            cell("country"),
            cell("product"),
            cell("quantity"),
            cell("timeline_days"),
        )
        output.append(cells + [priority, reason])
    return output


def _write_output(
    output_path: Path,
    header: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> None:
    """先写同目录临时文件再原子替换，避免失败时留下半成品。"""
    directory = output_path.parent
    if not directory.is_dir():
        raise TriageError(f"输出目录不存在：{directory}")
    try:
        fd, temp_name = tempfile.mkstemp(
            dir=str(directory),
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise TriageError(f"无法创建输出文件 {output_path}：{detail}") from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(list(header) + list(OUTPUT_HEADERS))
            writer.writerows(rows)
        os.replace(temp_name, output_path)
    except OSError as exc:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        detail = exc.strerror or str(exc)
        raise TriageError(f"无法写入输出文件 {output_path}：{detail}") from exc
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def run(input_path: Path, output_path: Path) -> None:
    """读取、分级并写出；任一检查失败时不会创建/覆盖输出文件。"""
    header, rows = _read_input(input_path)
    missing = _missing_headers(header)
    if missing:
        raise TriageError(
            _MISSING_HEADER_MESSAGE.format(
                missing=", ".join(missing),
                required=", ".join(REQUIRED_HEADERS),
            )
        )
    triaged = triage_rows(header, rows)
    _write_output(output_path, header, triaged)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按规则给挂车询盘 CSV 分级，并在末尾追加 priority,reason 列。",
    )
    parser.add_argument("input_csv", type=Path, help="输入 UTF-8 CSV 路径")
    parser.add_argument("output_csv", type=Path, help="输出 UTF-8 CSV 路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        run(args.input_csv, args.output_csv)
    except TriageError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
