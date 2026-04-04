#!/usr/bin/env python3
"""Export review-tier questions into prioritized verification queues.

Inputs:
- src/data/generatedQuestions.js
- src/data/questionReliability.js

Outputs:
- reports/review_queue.csv
- reports/review_queue_summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "src/data/generatedQuestions.js"
DEFAULT_RELIABILITY = ROOT / "src/data/questionReliability.js"
DEFAULT_QUEUE_CSV = ROOT / "reports/review_queue.csv"
DEFAULT_SUMMARY_MD = ROOT / "reports/review_queue_summary.md"


def extract_export_payload(js_text: str, export_name: str, next_export_name: str | None = None) -> str:
    if next_export_name:
        pattern = re.compile(
            rf"export\s+const\s+{re.escape(export_name)}\s*=\s*(.+?)\s*;\s*export\s+const\s+{re.escape(next_export_name)}\s*=",
            re.S,
        )
        match = pattern.search(js_text)
        if match:
            return match.group(1)

    fallback = re.search(
        rf"export\s+const\s+{re.escape(export_name)}\s*=\s*(.+?)\s*;",
        js_text,
        re.S,
    )
    if not fallback:
        raise RuntimeError(f"export payload not found: {export_name}")
    return fallback.group(1)


def load_questions(path: Path) -> Dict[str, Dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    payload = extract_export_payload(text, "generatedQuestionsBank", "generatedQuestionsMeta")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError("generatedQuestionsBank is not an array.")

    out: Dict[str, Dict[str, object]] = {}
    for item in data:
        qid = f"{item['source']}-Q{item['number']}"
        out[qid] = item
    return out


def load_reliability(path: Path) -> Dict[str, Dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    payload = extract_export_payload(text, "questionReliabilityByQid", "goldQuestionQids")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("questionReliabilityByQid is not an object.")
    return data


def truncate_text(text: str, length: int = 100) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= length:
        return text
    return text[: length - 1] + "…"


def assign_priority_bucket(reliability: Dict[str, object]) -> str:
    basis = str(reliability.get("basis", "unknown"))
    score = int(reliability.get("score", 0))
    noise_flags = reliability.get("noiseFlags", [])
    if not isinstance(noise_flags, list):
        noise_flags = []

    # A: high-impact; final key 기반 또는 노이즈로 채점오류 가능성이 큰 건
    if basis == "final" and (noise_flags or score >= 55):
        return "A"
    # B: tentative 기반 중 상대적으로 영향도가 큰 건
    if basis == "tentative" and (noise_flags or score >= 55):
        return "B"
    # C: 나머지 장기 검수
    return "C"


def build_queue_rows(
    questions: Dict[str, Dict[str, object]],
    reliability_by_qid: Dict[str, Dict[str, object]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for qid, reliability in reliability_by_qid.items():
        if str(reliability.get("tier")) != "review":
            continue

        question = questions.get(qid, {})
        noise_flags = reliability.get("noiseFlags", [])
        if not isinstance(noise_flags, list):
            noise_flags = []

        row = {
            "priority": assign_priority_bucket(reliability),
            "qid": qid,
            "source": str(question.get("source", "")),
            "number": int(question.get("number", 0) or 0),
            "subject": str(question.get("subject", "")),
            "basis": str(reliability.get("basis", "unknown")),
            "score": int(reliability.get("score", 0) or 0),
            "frequent_match_count": int(reliability.get("frequentMatchCount", 0) or 0),
            "core_match_count": int(reliability.get("coreMatchCount", 0) or 0),
            "noise_flags": "|".join(noise_flags) if noise_flags else "",
            "question_preview": truncate_text(question.get("question", ""), 100),
            "status": "pending",
            "verified_answer": "",
            "review_note": "",
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row["priority"],
            row["basis"] != "final",  # final 우선
            row["source"],
            row["number"],
        )
    )
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = [
        "priority",
        "qid",
        "source",
        "number",
        "subject",
        "basis",
        "score",
        "frequent_match_count",
        "core_match_count",
        "noise_flags",
        "question_preview",
        "status",
        "verified_answer",
        "review_note",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    priority_counter = Counter(row["priority"] for row in rows)
    basis_counter = Counter(row["basis"] for row in rows)
    subject_counter = Counter(row["subject"] for row in rows)
    noise_counter = Counter()
    for row in rows:
        for noise in str(row["noise_flags"]).split("|"):
            if noise:
                noise_counter[noise] += 1

    lines: List[str] = []
    lines.append("# Review 검수 큐 요약")
    lines.append("")
    lines.append(f"- 생성시각: {now}")
    lines.append(f"- 전체 Review: {len(rows)}")
    lines.append(
        f"- 우선순위: A {priority_counter['A']} / B {priority_counter['B']} / C {priority_counter['C']}"
    )
    lines.append(f"- 답안 기준: final {basis_counter['final']} / tentative {basis_counter['tentative']}")
    lines.append("")
    lines.append("## 과목별 Review")
    lines.append("")
    for subject, count in subject_counter.items():
        lines.append(f"- {subject}: {count}")
    lines.append("")
    lines.append("## 노이즈 상위")
    lines.append("")
    for noise, count in noise_counter.most_common(10):
        lines.append(f"- {noise}: {count}")
    lines.append("")
    lines.append("## 운영 규칙")
    lines.append("")
    lines.append("- A 먼저 수기검수: 확정답안 기반/노이즈 동반 문항을 우선 확인.")
    lines.append("- B 다음 검수: 가답안 기반 중 오탐 가능성이 높은 문항 검토.")
    lines.append("- C는 장기 검수: 의미 매칭 부족 위주로 뒤에서 처리.")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prioritized review queue.")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--reliability", type=Path, default=DEFAULT_RELIABILITY)
    parser.add_argument("--queue-csv", type=Path, default=DEFAULT_QUEUE_CSV)
    parser.add_argument("--summary-md", type=Path, default=DEFAULT_SUMMARY_MD)
    args = parser.parse_args()

    questions = load_questions(args.questions)
    reliability_by_qid = load_reliability(args.reliability)
    rows = build_queue_rows(questions, reliability_by_qid)

    write_csv(args.queue_csv, rows)
    write_summary(args.summary_md, rows)

    c = Counter(row["priority"] for row in rows)
    print(f"Queue CSV: {args.queue_csv}")
    print(f"Summary MD: {args.summary_md}")
    print(f"Review rows: {len(rows)} (A={c['A']}, B={c['B']}, C={c['C']})")


if __name__ == "__main__":
    main()
