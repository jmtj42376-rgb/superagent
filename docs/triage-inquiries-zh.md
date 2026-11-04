# 挂车询盘 CSV 自动分级

`tools/triage_inquiries.py` 是仅使用 Python 标准库的本地小工具：读取销售拿到的询盘 CSV，为每行追加 `priority`（A/B/C）和 `reason`，再由人判断如何联系。

## 运行

```bash
python3 tools/triage_inquiries.py examples/inquiries_sample.csv /tmp/inquiries_triage.csv
```

输入输出均为 UTF-8 CSV。输出保留输入的列和行顺序，只在末尾追加 `priority,reason` 两列。

## 分级规则

- 目标国家：Kazakhstan、Uzbekistan、Kyrgyzstan、Tajikistan、Turkmenistan。
- 目标产品：lowbed、flatbed、tipper。
- `country` 和 `product` 会去掉首尾空格，匹配时不区分大小写。
- 按以下顺序判断：
  1. **C**：国家或产品有明确填写，但不在目标列表。
  2. **B**：国家、产品、数量或交期缺失，或数量/交期不是正整数；`reason` 会列出缺失或无效的字段。
  3. **A**：字段完整且匹配目标市场，数量 ≥ 3、交期 ≤ 30 天。
  4. **B**：其余匹配询盘，即数量不足 3 或交期超过 30 天。

阈值边界：数量 3、交期 30 天仍为 A。

## 错误与坏数据

- 缺少必填表头 `id,country,product,quantity,timeline_days` 时，向标准错误输出中文提示并以非零状态退出，不创建也不覆盖输出文件。
- 空字段、非正整数、字段数不足只影响当前行（判为 B），不会中断整批；短行会按空值补齐。
- 行字段数多于表头时，输出只保留表头声明的列，并在 `reason` 中说明被截断的多余字段；原本可判 A 的目标询盘改判 B，后续行照常处理。
- 数量/交期超过 1000 位的异常数字按无效字段判 B，不会因整数转换失败中断整批。
- 输入不是有效 UTF-8 时同样报错退出，不产生输出文件。

## 示例

`examples/inquiries_sample.csv` 使用虚构数据，运行后可以看到：

| id | 输入摘要 | priority | reason |
| --- | --- | --- | --- |
| INQ-1001 | Kazakhstan / lowbed / 3 / 30 | A | 信息完整，数量 3 >= 3 且交期 30 天 <= 30 天 |
| INQ-1002 | Uzbekistan / flatbed / 2 / 20 | B | 信息完整，但数量 2 低于 3 |
| INQ-1003 | Kazakhstan / lowbed / 3 / 31 | B | 信息完整，但交期 31 天超过 30 天 |
| INQ-1004 | Germany / lowbed / 10 / 7 | C | 国家不在目标市场：Germany |
| INQ-1005 | Uzbekistan / tipper / 空 / 10 | B | 缺少必填字段：quantity |

示例文件还包含大小写/空格、非目标产品、数量和交期同时不达标、数量为 0 等行。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖 A/B/C、A 的阈值边界、空值和无效数量/交期、缺失表头不覆盖输出，以及示例命令的端到端结果。
