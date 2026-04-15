"""准确率评估脚本：衡量 VLM 字段抽取的准确率。

用法：
    python evaluate.py --ground-truth ground_truth.json --input-dir <pdf_dir>

ground_truth.json 格式：
[
  {
    "filename": "example.pdf",
    "page": 1,
    "doc_type": "customs",
    "fields": {
      "declaration_number": "JCI00158457",
      "date": "2026-02-18",
      "importer": "TERRA DRVO d.o.o.",
      "currency": "EUR",
      "total_value": "12345.67",
      ...
    }
  },
  ...
]

输出：
- 每个字段的精确匹配率、部分匹配率
- 总体准确率（精确匹配 / 总字段数）
- 每种文档类型的分类准确率（如果 ground_truth 中有 doc_type）
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _normalize(value: str) -> str:
    """规范化字段值以便比较（去空格、转小写、去标点差异）。"""
    v = value.strip().lower()
    # 统一分隔符
    v = v.replace("–", "-").replace("—", "-")
    # 去除尾部零
    try:
        f = float(v.replace(",", ""))
        v = f"{f:g}"
    except (ValueError, OverflowError):
        pass
    return v


def _partial_match(predicted: str, expected: str) -> float:
    """计算部分匹配分数（0.0 ~ 1.0）。

    使用字符级别的最长公共子序列比例。
    """
    p = _normalize(predicted)
    e = _normalize(expected)

    if p == e:
        return 1.0
    if not p or not e:
        return 0.0

    # LCS
    m, n = len(p), len(e)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if p[i - 1] == e[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    return 2.0 * lcs_len / (m + n)


def evaluate(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    """评估预测结果与标注数据。

    返回结构：
    {
        "overall": {"exact_match": 0.85, "partial_match": 0.92, "total_fields": 100},
        "per_field": {"date": {"exact": 0.95, "partial": 0.98, "count": 20}, ...},
        "per_doc_type": {"customs": {"exact": 0.88, ...}, ...},
    }
    """
    # 按 (filename, page) 索引标注
    gt_index: dict[tuple[str, int], dict[str, str]] = {}
    gt_types: dict[tuple[str, int], str] = {}
    for item in ground_truth:
        key = (item["filename"], item.get("page", 1))
        gt_index[key] = item.get("fields", {})
        gt_types[key] = item.get("doc_type", "unknown")

    # 统计
    total_exact = 0
    total_partial = 0.0
    total_count = 0

    field_stats: dict[str, dict[str, float]] = defaultdict(lambda: {"exact": 0, "partial": 0.0, "count": 0})
    type_stats: dict[str, dict[str, float]] = defaultdict(lambda: {"exact": 0, "partial": 0.0, "count": 0})

    for pred in predictions:
        key = (pred["filename"], pred.get("page", 1))
        gt_fields = gt_index.get(key)
        if gt_fields is None:
            continue

        doc_type = gt_types.get(key, "unknown")
        pred_fields = pred.get("fields", {})

        for field_name, expected_value in gt_fields.items():
            if not expected_value:
                continue

            predicted_value = str(pred_fields.get(field_name, ""))
            total_count += 1
            field_stats[field_name]["count"] += 1
            type_stats[doc_type]["count"] += 1

            exact = 1 if _normalize(predicted_value) == _normalize(expected_value) else 0
            partial = _partial_match(predicted_value, expected_value)

            total_exact += exact
            total_partial += partial
            field_stats[field_name]["exact"] += exact
            field_stats[field_name]["partial"] += partial
            type_stats[doc_type]["exact"] += exact
            type_stats[doc_type]["partial"] += partial

    # 计算比例
    result: dict[str, Any] = {
        "overall": {
            "exact_match": total_exact / total_count if total_count else 0,
            "partial_match": total_partial / total_count if total_count else 0,
            "total_fields": total_count,
            "exact_count": total_exact,
        },
        "per_field": {},
        "per_doc_type": {},
    }

    for name, stats in sorted(field_stats.items()):
        c = stats["count"]
        result["per_field"][name] = {
            "exact_match": stats["exact"] / c if c else 0,
            "partial_match": stats["partial"] / c if c else 0,
            "count": int(c),
        }

    for dtype, stats in sorted(type_stats.items()):
        c = stats["count"]
        result["per_doc_type"][dtype] = {
            "exact_match": stats["exact"] / c if c else 0,
            "partial_match": stats["partial"] / c if c else 0,
            "count": int(c),
        }

    return result


def _print_report(result: dict[str, Any]) -> None:
    """打印格式化的准确率报告。"""
    overall = result["overall"]
    print("\n" + "=" * 60)
    print("  DocAI Pipeline 准确率评估报告")
    print("=" * 60)

    print(f"\n总体准确率:")
    print(f"  精确匹配: {overall['exact_match']:.1%} ({overall['exact_count']}/{overall['total_fields']})")
    print(f"  部分匹配: {overall['partial_match']:.1%}")

    print(f"\n按字段分:")
    print(f"  {'字段名':<25} {'精确匹配':>8} {'部分匹配':>8} {'样本数':>6}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*6}")
    for name, stats in result["per_field"].items():
        print(f"  {name:<25} {stats['exact_match']:>7.1%} {stats['partial_match']:>7.1%} {stats['count']:>6}")

    if result["per_doc_type"]:
        print(f"\n按文档类型分:")
        print(f"  {'文档类型':<20} {'精确匹配':>8} {'部分匹配':>8} {'字段数':>6}")
        print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*6}")
        for dtype, stats in result["per_doc_type"].items():
            print(f"  {dtype:<20} {stats['exact_match']:>7.1%} {stats['partial_match']:>7.1%} {stats['count']:>6}")

    # 提案要求判定
    target = 0.80
    status = "✅ 达标" if overall["exact_match"] >= target else "⚠️ 未达标"
    print(f"\n提案目标: ≥ {target:.0%} 精确匹配率 → {status}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="DocAI Pipeline 准确率评估")
    parser.add_argument("--ground-truth", "-g", required=True, help="标注数据 JSON 文件路径")
    parser.add_argument("--predictions", "-p", required=True, help="预测结果 JSON 文件路径")
    parser.add_argument("--output", "-o", help="评估报告输出 JSON 文件路径")
    args = parser.parse_args()

    gt_path = Path(args.ground_truth)
    pred_path = Path(args.predictions)

    if not gt_path.exists():
        print(f"错误: 标注文件不存在: {gt_path}")
        sys.exit(1)
    if not pred_path.exists():
        print(f"错误: 预测文件不存在: {pred_path}")
        sys.exit(1)

    ground_truth = json.loads(gt_path.read_text("utf-8"))
    predictions = json.loads(pred_path.read_text("utf-8"))

    result = evaluate(ground_truth, predictions)
    _print_report(result)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n报告已保存到: {out_path}")


if __name__ == "__main__":
    main()
