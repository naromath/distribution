#!/usr/bin/env python3
"""Build generated question bank from past exam PDFs/XLSX answer sheets.

Output:
- src/data/generatedQuestions.js

Usage:
  python3 scripts/build_question_bank.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "src/data/generatedQuestions.js"


@dataclass(frozen=True)
class ExamConfig:
  exam_id: str
  question_pdf: Path
  answer_source: Path
  answer_type: str  # "pdf" | "xlsx"
  answer_label: str  # "확정답안" | "가답안"
  question_end_marker: str | None = None


EXAMS: List[ExamConfig] = [
    ExamConfig(
        exam_id="2021-R2",
        question_pdf=ROOT / "기출문제/2021/2021-R2-cbt-ab.pdf",
        answer_source=ROOT / "기출문제/2021/2021-R2-cbt-ab.pdf",
        answer_type="pdf",
        answer_label="가답안",
        question_end_marker="2급 B형",
    ),
    ExamConfig(
        exam_id="2022-R1",
        question_pdf=ROOT / "기출문제/2022/2022-R1-A.pdf",
        answer_source=ROOT / "기출문제/2022/2022-R1-answer-tentative.xlsx",
        answer_type="xlsx",
        answer_label="가답안",
    ),
    ExamConfig(
        exam_id="2022-R2",
        question_pdf=ROOT / "기출문제/2022/2022-R2-cbt-ab.pdf",
        answer_source=ROOT / "기출문제/2022/2022-R2-cbt-ab.pdf",
        answer_type="pdf",
        answer_label="가답안",
        question_end_marker="2급 B형",
    ),
    ExamConfig(
        exam_id="2022-R3",
        question_pdf=ROOT / "기출문제/2022/2022-R3-A.pdf",
        answer_source=ROOT / "기출문제/2022/2022-R3-answer-final.pdf",
        answer_type="pdf",
        answer_label="확정답안",
    ),
    ExamConfig(
        exam_id="2023-R1",
        question_pdf=ROOT / "기출문제/2023/2023-R1-A.pdf",
        answer_source=ROOT / "기출문제/2023/2023-R1-answer-tentative.xlsx",
        answer_type="xlsx",
        answer_label="가답안",
    ),
    ExamConfig(
        exam_id="2023-R2",
        question_pdf=ROOT / "기출문제/2023/2023-R2-cbt.pdf",
        answer_source=ROOT / "기출문제/2023/2023-R2-cbt.pdf",
        answer_type="pdf",
        answer_label="가답안",
    ),
    ExamConfig(
        exam_id="2023-R3",
        question_pdf=ROOT / "기출문제/2023/2023-R3-A.pdf",
        answer_source=ROOT / "기출문제/2023/2023-R3-answer-final.pdf",
        answer_type="pdf",
        answer_label="확정답안",
    ),
    ExamConfig(
        exam_id="2024-R1",
        question_pdf=ROOT / "기출문제/2024/2024-R1-A.pdf",
        answer_source=ROOT / "기출문제/2024/2024-R1-answer-tentative.pdf",
        answer_type="pdf",
        answer_label="가답안",
    ),
    ExamConfig(
        exam_id="2024-R2",
        question_pdf=ROOT / "기출문제/2024/2024-R2-A.pdf",
        answer_source=ROOT / "기출문제/2024/2024-R2-answer-tentative.xlsx",
        answer_type="xlsx",
        answer_label="가답안",
    ),
    ExamConfig(
        exam_id="2024-R3",
        question_pdf=ROOT / "기출문제/2024/2024-R3-A.pdf",
        answer_source=ROOT / "기출문제/2024/2024-R3-answer-final.xlsx",
        answer_type="xlsx",
        answer_label="확정답안",
    ),
]

CIRCLED_MARKERS = ["①", "②", "③", "④", "⑤"]


def normalize_text(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:?!])", r"\1", value)
    return value.strip()


def extract_two_column_page_text(page) -> str:
    width, height = page.width, page.height
    midpoint = width / 2
    left = page.crop((0, 0, midpoint, height)).extract_text() or ""
    right = page.crop((midpoint, 0, width, height)).extract_text() or ""
    return f"{left}\n{right}"


def extract_question_map(pdf_path: Path, question_end_marker: str | None = None) -> Dict[int, Dict[str, object]]:
    page_texts: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_texts.append(extract_two_column_page_text(page))

    full_text = "\n".join(page_texts)

    # Skip cover/instructions and start from real subject section.
    subject_header = re.search(r"(?:<\s*제?1과목\s*>|제?1과목\s*[:：]|1과목\s)", full_text)
    if subject_header:
        full_text = full_text[subject_header.start() :]

    first_question = re.search(r"(?m)^\s*1\.\s", full_text)
    if first_question:
        full_text = full_text[first_question.start() :]

    # For files containing both A/B forms in one PDF, keep A section only.
    if question_end_marker and question_end_marker in full_text:
        full_text = full_text.split(question_end_marker, 1)[0]

    full_text = full_text.replace("\u00a0", " ")
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"\s+\n", "\n", full_text)
    full_text = re.sub(r"\n{2,}", "\n", full_text)

    starts = list(re.finditer(r"(?m)^\s*(\d{1,2})\.\s", full_text))
    question_map: Dict[int, Dict[str, object]] = {}

    for index, match in enumerate(starts):
        q_number = int(match.group(1))
        start = match.start()
        end = starts[index + 1].start() if index + 1 < len(starts) else len(full_text)
        block = full_text[start:end].strip()
        block = re.sub(r"^\s*\d{1,2}\.\s*", "", block)

        positions = [block.find(marker) for marker in CIRCLED_MARKERS]
        if any(pos == -1 for pos in positions) or positions != sorted(positions):
            continue

        question_text = normalize_text(block[: positions[0]])
        options: List[str] = []

        for i, pos in enumerate(positions):
            next_pos = positions[i + 1] if i < 4 else len(block)
            option_text = normalize_text(block[pos + 1 : next_pos])
            options.append(f"{CIRCLED_MARKERS[i]} {option_text}")

        if len(options) != 5:
            continue

        question_map[q_number] = {
            "question": question_text,
            "options": options,
        }

    return question_map


def parse_answers_from_pdf(pdf_path: Path) -> Dict[int, str]:
    text_chunks: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text_chunks.append(page.extract_text() or "")
    text = "\n".join(text_chunks)

    answers: Dict[int, str] = {}
    pattern = re.compile(r"\b(\d{1,2})\s+([1-5](?:,[1-5])*)\s+([1-5](?:,[1-5])*)\b")
    for match in pattern.finditer(text):
        q_number = int(match.group(1))
        a_type_answer = match.group(2)
        answers[q_number] = a_type_answer

    if len(answers) >= 80:
        return answers

    # Fallback for CBT PDFs that provide one 90-number circled-answer table.
    anchor = re.search(r"(?m)^\s*1\s+2\s+3\s+4\s+5\s+6\s+7\s+8\s+9\s+10\s*$", text)
    if anchor:
        tail = text[anchor.start() :]
        circled_tokens = re.findall(r"[①②③④⑤]", tail)
        if len(circled_tokens) >= 90:
            circled_to_digit = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
            return {index + 1: circled_to_digit[token] for index, token in enumerate(circled_tokens[:90])}

    return answers


def parse_answers_from_xlsx(xlsx_path: Path) -> Dict[int, str]:
    df = pd.read_excel(str(xlsx_path), sheet_name="2급", header=None)

    header_row = None
    for row_index in range(min(10, len(df))):
        row_values = [str(v).strip() for v in df.iloc[row_index].tolist()]
        if any(v == "문제번호" for v in row_values):
            header_row = row_index
            break

    if header_row is None:
        raise RuntimeError(f"'문제번호' 헤더를 찾지 못했습니다: {xlsx_path}")

    question_columns = [
        col for col, value in enumerate(df.iloc[header_row].tolist()) if str(value).strip() == "문제번호"
    ]

    answers: Dict[int, str] = {}
    for row_index in range(header_row + 1, len(df)):
        for col in question_columns:
            question_cell = df.iat[row_index, col]
            answer_cell = df.iat[row_index, col + 1] if col + 1 < df.shape[1] else None

            if pd.isna(question_cell) or pd.isna(answer_cell):
                continue

            question_raw = str(question_cell).strip()
            answer_raw = str(answer_cell).strip()

            if re.fullmatch(r"\d{1,2}", question_raw):
                answers[int(question_raw)] = answer_raw

    return answers


def subject_for_question_number(question_number: int) -> str:
    if 1 <= question_number <= 25:
        return "유통물류일반"
    if 26 <= question_number <= 45:
        return "상권분석"
    if 46 <= question_number <= 70:
        return "유통마케팅"
    if 71 <= question_number <= 90:
        return "유통정보"
    raise ValueError(f"Unsupported question number: {question_number}")


def load_answers(exam: ExamConfig) -> Dict[int, str]:
    if exam.answer_type == "pdf":
        return parse_answers_from_pdf(exam.answer_source)
    if exam.answer_type == "xlsx":
        return parse_answers_from_xlsx(exam.answer_source)
    raise ValueError(f"Unsupported answer type: {exam.answer_type}")


def build_question_bank() -> Dict[str, object]:
    generated_items: List[Dict[str, object]] = []
    skipped_ambiguous: List[Dict[str, object]] = []

    for exam in EXAMS:
        question_map = extract_question_map(exam.question_pdf, exam.question_end_marker)
        answer_map = load_answers(exam)

        for question_number in range(1, 91):
            question_data = question_map.get(question_number)
            answer_raw = answer_map.get(question_number)
            if not question_data or answer_raw is None:
                continue

            # Skip multiple-correct answer keys (e.g. "1,3") to avoid wrong grading.
            if not re.fullmatch(r"[1-5]", str(answer_raw)):
                skipped_ambiguous.append(
                    {
                        "source": exam.exam_id,
                        "number": question_number,
                        "answer_raw": str(answer_raw),
                    }
                )
                continue

            answer_index = int(answer_raw) - 1
            generated_items.append(
                {
                    "source": exam.exam_id,
                    "number": question_number,
                    "subject": subject_for_question_number(question_number),
                    "question": question_data["question"],
                    "options": question_data["options"],
                    "answer": answer_index,
                    "explanation": f"{exam.exam_id} A형 {exam.answer_label} 기준",
                }
            )

    generated_items.sort(key=lambda item: (str(item["source"]), int(item["number"])))

    return {
        "items": generated_items,
        "skipped_ambiguous": skipped_ambiguous,
    }


def write_js_output(payload: Dict[str, object]) -> None:
    items = payload["items"]
    skipped = payload["skipped_ambiguous"]

    js_lines = [
        "// Auto-generated by scripts/build_question_bank.py",
        "// Do not edit manually.",
        "",
        f"export const generatedQuestionsBank = {json.dumps(items, ensure_ascii=False, indent=2)};",
        "",
        f"export const generatedQuestionsMeta = {json.dumps({'count': len(items), 'skippedAmbiguous': skipped}, ensure_ascii=False, indent=2)};",
        "",
    ]
    OUTPUT_FILE.write_text("\n".join(js_lines), encoding="utf-8")


def main() -> None:
    result = build_question_bank()
    write_js_output(result)

    print(f"Generated: {OUTPUT_FILE}")
    print(f"Question count: {len(result['items'])}")
    print(f"Skipped ambiguous answers: {len(result['skipped_ambiguous'])}")


if __name__ == "__main__":
    main()
