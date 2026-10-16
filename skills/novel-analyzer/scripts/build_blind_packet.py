#!/usr/bin/env python3
"""Build a deterministic provenance-blind packet from old and current pools."""

import argparse
import json
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    old = json.loads(args.old.read_text(encoding="utf-8"))["candidates"]
    current = [item for item in json.loads(args.current.read_text(encoding="utf-8"))["candidates"] if item["status"] == "ready"]
    candidates = [("old", item) for item in old] + [("current", item) for item in current]
    random.Random(41).shuffle(candidates)
    lines = [
        "# 短篇候选盲选包",
        "",
        "请选择最愿意实际写成 8000–15000 字短篇的 5 个候选。只看概念、承诺、闭环和场景承载；同时标出明显 IP/敏感/热点拼接风险。",
        "",
    ]
    key = {}
    for index, (source, item) in enumerate(candidates, 1):
        label = chr(64 + index)
        key[label] = {"source": source, "id": item["id"], "title": item["title"]}
        lines.extend([
            f"## {label}. 《{item['title']}》",
            "",
            f"- 题材：{item['genre_bucket']}；核心情绪：{item['emotion_bucket']}",
            f"- 概念：{item['premise']}",
            f"- 前300字承诺：{item['promise_300']}",
            f"- 核心兑现：{item['payoff'] or '未提供'}",
            f"- 场景链：{' → '.join(item['scene_chain'])}",
            "",
        ])
    args.out.write_text("\n".join(lines), encoding="utf-8")
    args.out.with_suffix(".key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
