#!/usr/bin/env python3
"""Build learning assets from supplementary PDFs.

Outputs:
- src/data/learningAssets.js
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREQUENT_PDF = Path("/Users/wacus/Downloads/유통관리사_빈출100선.pdf")
DEFAULT_CORE_PDF = Path("/Users/wacus/Downloads/유통관리사_핵심요점정리.pdf")
OUTPUT_FILE = ROOT / "src/data/learningAssets.js"

SUBJECT_BY_CHAPTER = {
    1: "유통물류일반",
    2: "상권분석",
    3: "유통마케팅",
    4: "유통정보",
}

KOREAN_STOPWORDS = {
    "및",
    "의",
    "과",
    "와",
    "이",
    "가",
    "을",
    "를",
    "에",
    "에서",
    "으로",
    "를",
    "한",
    "대한",
    "기초",
    "개요",
    "전략",
    "관리",
    "분석",
}


def normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def extract_title_keywords(title: str, limit: int = 6) -> List[str]:
    tokens = re.split(r"[^0-9a-zA-Z가-힣]+", title)
    words: List[str] = []
    for token in tokens:
        t = token.strip()
        if len(t) < 2:
            continue
        if t in KOREAN_STOPWORDS:
            continue
        words.append(t)

    unique: List[str] = []
    seen = set()
    for w in words:
        if w not in seen:
            unique.append(w)
            seen.add(w)
    return unique[:limit]


def looks_like_title(line: str) -> bool:
    if not line:
        return False
    if len(line) > 90:
        return False
    if "www.eduwill.net" in line:
        return False
    if re.fullmatch(r"\d+", line):
        return False
    if re.match(r"^[①-⑳ㄱ-ㅎ]", line):
        return False
    if line.startswith(("(", ")", "[", "]", "•", "-", "※", "ㄴ.")):
        return False
    return True


def load_pdf_lines(pdf_path: Path) -> List[List[str]]:
    page_lines: List[List[str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [normalize_line(line) for line in text.splitlines()]
            page_lines.append([line for line in lines if line])
    return page_lines


def extract_frequent_items(frequent_pdf: Path) -> List[Dict[str, object]]:
    lines_by_page = load_pdf_lines(frequent_pdf)
    items: Dict[int, str] = {}

    for lines in lines_by_page:
        for idx, line in enumerate(lines):
            # Pattern A: number on one line, title on next line
            if re.fullmatch(r"\d{1,3}", line):
                number = int(line)
                if 1 <= number <= 100 and idx + 1 < len(lines):
                    title = normalize_line(lines[idx + 1])
                    if looks_like_title(title):
                        items[number] = title

            # Pattern B: number + title in one line
            match = re.match(r"^(\d{1,3})\s+(.+)$", line)
            if match:
                number = int(match.group(1))
                title = normalize_line(match.group(2))
                if 1 <= number <= 100 and looks_like_title(title):
                    items[number] = title

    result: List[Dict[str, object]] = []
    for number in sorted(items):
        title = items[number]
        keywords = extract_title_keywords(title)
        result.append(
            {
                "number": number,
                "title": title,
                "keywords": [title] + keywords,
            }
        )
    return result


def detect_chapter_starts(lines_by_page: List[List[str]]) -> Dict[int, int]:
    starts: Dict[int, int] = {}
    for page_index, lines in enumerate(lines_by_page):
        header_scan = lines[:12]
        if "Chap" not in header_scan or "ter" not in header_scan:
            continue
        chapter_num = None
        for token in header_scan:
            if token in {"1", "2", "3", "4"}:
                chapter_num = int(token)
                break
        if chapter_num and chapter_num not in starts:
            starts[chapter_num] = page_index
    return starts


def chapter_ranges(starts: Dict[int, int], total_pages: int) -> Dict[int, Tuple[int, int]]:
    chapter_keys = sorted(starts.keys())
    ranges: Dict[int, Tuple[int, int]] = {}
    for idx, chapter in enumerate(chapter_keys):
        start = starts[chapter]
        end = starts[chapter_keys[idx + 1]] if idx + 1 < len(chapter_keys) else total_pages
        ranges[chapter] = (start, end)
    return ranges


def extract_core_summaries(core_pdf: Path) -> Dict[str, Dict[str, object]]:
    lines_by_page = load_pdf_lines(core_pdf)
    starts = detect_chapter_starts(lines_by_page)
    ranges = chapter_ranges(starts, len(lines_by_page))

    summaries: Dict[str, Dict[str, object]] = {}
    for chapter, (start, end) in ranges.items():
        subject = SUBJECT_BY_CHAPTER.get(chapter)
        if not subject:
            continue

        headings: List[str] = []
        seen = set()
        for lines in lines_by_page[start:end]:
            for line in lines:
                m = re.match(r"^(\d{2})\s+(.+)$", line)
                if not m:
                    continue
                heading = normalize_line(m.group(2))
                if len(heading) < 2:
                    continue
                if "핵심 요점 정리" in heading:
                    continue
                if heading.startswith("Chapter "):
                    continue
                if heading in seen:
                    continue
                headings.append(heading)
                seen.add(heading)

        key_points = headings[:12]
        summaries[subject] = {
            "sourceChapter": chapter,
            "keyPoints": key_points,
        }

    return summaries


def write_js(
    output: Path,
    frequent_items: List[Dict[str, object]],
    core_summaries: Dict[str, Dict[str, object]],
    frequent_pdf: Path,
    core_pdf: Path,
) -> None:
    metadata = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "frequentSource": str(frequent_pdf),
        "coreSource": str(core_pdf),
        "frequentCount": len(frequent_items),
    }

    lines = [
        "// Auto-generated by scripts/build_learning_assets.py",
        "// Do not edit manually.",
        "",
        f"export const frequent100Topics = {json.dumps(frequent_items, ensure_ascii=False, indent=2)};",
        "",
        f"export const coreSummaryBySubject = {json.dumps(core_summaries, ensure_ascii=False, indent=2)};",
        "",
        f"export const learningAssetsMeta = {json.dumps(metadata, ensure_ascii=False, indent=2)};",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build learning assets from supplementary PDFs.")
    parser.add_argument("--frequent-pdf", type=Path, default=DEFAULT_FREQUENT_PDF)
    parser.add_argument("--core-pdf", type=Path, default=DEFAULT_CORE_PDF)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()

    if not args.frequent_pdf.exists():
        raise FileNotFoundError(f"빈출 PDF를 찾지 못했습니다: {args.frequent_pdf}")
    if not args.core_pdf.exists():
        raise FileNotFoundError(f"핵심요점 PDF를 찾지 못했습니다: {args.core_pdf}")

    frequent_items = extract_frequent_items(args.frequent_pdf)
    core_summaries = extract_core_summaries(args.core_pdf)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_js(args.output, frequent_items, core_summaries, args.frequent_pdf, args.core_pdf)

    print(f"Generated: {args.output}")
    print(f"Frequent items: {len(frequent_items)}")
    print(f"Core summaries: {len(core_summaries)} subjects")


if __name__ == "__main__":
    main()
