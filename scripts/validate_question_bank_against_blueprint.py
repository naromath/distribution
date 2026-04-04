#!/usr/bin/env python3
"""Validate generated question bank coverage against the 2024+ exam blueprint.

References:
- /Users/wacus/Downloads/기출기준.pdf (2급, pages 13-18)
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "src/data/generatedQuestions.js"
DEFAULT_OUTPUT = ROOT / "reports/blueprint_coverage_report.md"


@dataclass(frozen=True)
class TopicRule:
    name: str
    keywords: Tuple[str, ...]


BLUEPRINT: Dict[str, Tuple[TopicRule, ...]] = {
    "유통물류일반": (
        TopicRule("유통의 이해", ("유통의 개념", "중간상", "유통기능", "유통흐름", "유통경로")),
        TopicRule("유통경영전략", ("경영전략", "경쟁우위", "경영혁신", "다각화", "아웃소싱", "합작투자", "인수합병", "글로벌화")),
        TopicRule("조직관리", ("조직이론", "조직구조", "목표관리", "동기부여", "의사소통", "갈등관리", "리더십")),
        TopicRule("인적자원관리", ("인사관리", "직무분석", "직무평가", "채용", "배치", "보상", "근로", "승진")),
        TopicRule("재무관리", ("재무관리", "화폐의 시간가치", "현재가치", "자본예산", "자본조달", "자본비용", "ROI", "수익률")),
        TopicRule("구매 및 조달관리", ("구매", "조달", "공급자", "원가계산", "구매가격", "구매계약", "구매협상", "품질관리")),
        TopicRule("도소매물류관리", ("물류계획", "운송", "보관", "하역", "창고", "포장", "물류비", "3자물류", "4자물류", "국제물류", "SCM", "JIT")),
        TopicRule("유통기업 윤리와 법규", ("기업윤리", "사회적 책임", "유통산업발전법", "전자문서", "전자거래기본법", "소비자기본법", "양성평등")),
    ),
    "상권분석": (
        TopicRule("상권의 개요", ("상권", "상권의 유형", "상권의 계층성")),
        TopicRule("상권정보기술 활용", ("상권정보", "상권정보시스템", "지리정보", "GIS")),
        TopicRule("상권설정 및 분석", ("상권설정", "상권조사", "상권분석", "업태", "업종", "상권입지분석")),
        TopicRule("입지의 개요", ("입지", "도매입지", "소매입지", "물류입지")),
        TopicRule("입지별 유형", ("지역 공간 구조", "도심입지", "쇼핑센터", "기타입지")),
        TopicRule("입지선정 및 분석", ("입지선정", "입지영향", "경쟁점", "채널분석", "입지 개발")),
        TopicRule("개점전략", ("점포개점", "개점계획", "출점", "폐점", "업종전환", "법률규제")),
    ),
    "유통마케팅": (
        TopicRule("유통마케팅 전략기획", ("시장세분화", "목표시장", "포지셔닝", "STP")),
        TopicRule("유통경쟁전략", ("유통경쟁", "소매업태", "글로벌 경쟁전략", "서비스 마케팅")),
        TopicRule("상품관리 및 머천다이징", ("머천다이징", "브랜드", "상품기획", "카테고리", "매입", "구매계획", "상품수명주기", "단품관리", "PB")),
        TopicRule("가격관리전략", ("가격관리", "가격설정", "가격정책", "할인", "가격전략")),
        TopicRule("촉진관리전략", ("촉진", "프로모션", "옴니채널", "O2O", "O4O", "소매정보", "e-retailing")),
        TopicRule("디지털 마케팅 전략", ("디지털 마케팅", "온라인 구매", "검색엔진", "SEO", "소셜미디어", "콘텐츠", "CPC", "CPM", "전환율", "노출수")),
        TopicRule("점포구성/레이아웃/디스플레이", ("점포구성", "점포 디자인", "레이아웃", "디스플레이", "상품진열", "비주얼", "POP")),
        TopicRule("매장환경관리", ("매장 환경", "매장 안전", "매장 관리", "통제")),
        TopicRule("상품판매와 고객관리", ("판매서비스", "로스관리", "고객의 이해", "고객정보", "고객응대")),
        TopicRule("CRM전략 및 구현", ("CRM", "고객관리", "고객충성도", "고객관계관리")),
        TopicRule("유통마케팅 조사와 평가", ("유통마케팅 조사", "자료분석", "성과 평가", "경로구성원", "갈등 평가")),
    ),
    "유통정보": (
        TopicRule("정보의 개념과 정보화사회", ("정보화 사회", "정보혁명", "정보와 자료", "자료지식", "정보의 유형")),
        TopicRule("정보와 의사결정", ("의사결정", "DSS", "GDSS", "EIS", "지식경영", "지식관리시스템")),
        TopicRule("유통정보시스템", ("유통정보시스템", "정보 네트워크", "시스템 기획", "분석설계구축")),
        TopicRule("바코드/POS/EDI/QR", ("바코드", "POS", "EDI", "QR")),
        TopicRule("데이터관리", ("데이터베이스", "데이터웨어하우스", "데이터마트", "빅데이터", "데이터마이닝", "데이터 거버넌스")),
        TopicRule("개인정보보호/프라이버시", ("개인정보", "프라이버시", "보안시스템", "개인정보보호")),
        TopicRule("고객충성도 프로그램", ("고객충성도 프로그램", "고객충성도")),
        TopicRule("전자상거래 운영", ("전자상거래", "물류 및 배송", "전자결제", "배송 관리시스템")),
        TopicRule("ERP/CRM/SCM 시스템", ("ERP", "CRM", "SCM")),
        TopicRule("신융합기술 응용", ("애널리틱스", "인공지능", "RFID", "사물인터넷", "로보틱스", "블록체인", "핀테크", "클라우드", "메타버스", "스마트물류", "자율주행")),
    ),
}


def normalize_for_match(text: str) -> str:
    text = text.replace("\u00a0", " ").lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    return text


def extract_questions_json(js_text: str) -> str:
    pattern = re.compile(
        r"export\s+const\s+generatedQuestionsBank\s*=\s*(\[.*?\])\s*;\s*export\s+const\s+generatedQuestionsMeta",
        re.S,
    )
    match = pattern.search(js_text)
    if not match:
        fallback = re.search(r"export\s+const\s+generatedQuestionsBank\s*=\s*(\[.*\])\s*;", js_text, re.S)
        if not fallback:
            raise RuntimeError("generatedQuestionsBank 배열을 찾지 못했습니다.")
        return fallback.group(1)
    return match.group(1)


def load_questions(input_path: Path) -> List[Dict[str, object]]:
    text = input_path.read_text(encoding="utf-8")
    payload = extract_questions_json(text)
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError("generatedQuestionsBank 형식이 올바르지 않습니다.")
    return data


def analyze_subject(items: Sequence[Dict[str, object]], rules: Sequence[TopicRule], min_hits: int) -> Dict[str, object]:
    topic_hits = Counter({rule.name: 0 for rule in rules})
    unmatched: List[str] = []

    normalized_rules = {
        rule.name: [normalize_for_match(keyword) for keyword in rule.keywords]
        for rule in rules
    }

    for item in items:
        question = str(item.get("question", ""))
        options = item.get("options", [])
        if not isinstance(options, list):
            options = []
        merged_text = " ".join([question] + [str(opt) for opt in options])
        normalized = normalize_for_match(merged_text)

        matched = False
        for rule in rules:
            keywords = normalized_rules[rule.name]
            if any(keyword and keyword in normalized for keyword in keywords):
                topic_hits[rule.name] += 1
                matched = True

        if not matched:
            unmatched.append(f"{item.get('source', 'N/A')}-Q{item.get('number', 'N/A')}")

    covered_topics = sum(1 for rule in rules if topic_hits[rule.name] > 0)
    weak_topics = [rule.name for rule in rules if topic_hits[rule.name] < min_hits]

    return {
        "total": len(items),
        "topic_hits": topic_hits,
        "covered_topics": covered_topics,
        "total_topics": len(rules),
        "unmatched": unmatched,
        "weak_topics": weak_topics,
    }


def build_markdown_report(
    questions: Sequence[Dict[str, object]],
    analyses: Dict[str, Dict[str, object]],
    min_hits: int,
    input_path: Path,
) -> str:
    lines: List[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    source_counter = Counter(str(item.get("source", "N/A")) for item in questions)

    lines.append("# 문제은행 출제기준 커버리지 점검 리포트")
    lines.append("")
    lines.append(f"- 생성시각: {now}")
    lines.append(f"- 입력파일: `{input_path}`")
    lines.append(f"- 전체 문항수: {len(questions)}")
    lines.append(f"- 기준: `유통관리사 출제기준(2024~) 2급` (PDF 13~18페이지)")
    lines.append("")
    lines.append("## 회차별 문항 수")
    lines.append("")
    for source, count in sorted(source_counter.items()):
        lines.append(f"- {source}: {count}문항")
    lines.append("")

    lines.append("## 과목별 커버리지")
    lines.append("")
    for subject, rules in BLUEPRINT.items():
        result = analyses.get(subject)
        if result is None:
            continue

        lines.append(f"### {subject}")
        lines.append("")
        lines.append(f"- 문항수: {result['total']}문항")
        lines.append(
            f"- 세부영역 커버리지: {result['covered_topics']}/{result['total_topics']} "
            f"({(result['covered_topics'] / max(1, result['total_topics'])) * 100:.1f}%)"
        )
        lines.append(f"- 미분류 문항수(키워드 불일치): {len(result['unmatched'])}")
        lines.append(f"- 취약 세부영역 기준: {min_hits}문항 미만")
        if result["weak_topics"]:
            lines.append(f"- 취약 세부영역: {', '.join(result['weak_topics'])}")
        else:
            lines.append("- 취약 세부영역: 없음")

        if result["unmatched"]:
            sample = ", ".join(result["unmatched"][:10])
            lines.append(f"- 미분류 샘플(최대 10개): {sample}")
        else:
            lines.append("- 미분류 샘플: 없음")

        lines.append("")
        lines.append("| 세부영역 | 매칭 문항수 | 기준 키워드 예시 |")
        lines.append("|---|---:|---|")
        hits: Counter = result["topic_hits"]
        for rule in rules:
            keyword_preview = ", ".join(rule.keywords[:4])
            lines.append(f"| {rule.name} | {hits[rule.name]} | {keyword_preview} |")
        lines.append("")

    lines.append("## 해석 주의")
    lines.append("")
    lines.append("- 본 리포트는 `키워드 기반 자동 분류` 결과입니다.")
    lines.append("- 실제 출제기준 적합성은 사람이 최종 검토해야 합니다.")
    lines.append("- 키워드 사전은 `scripts/validate_question_bank_against_blueprint.py`의 `BLUEPRINT` 상수에서 조정할 수 있습니다.")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated question bank against 2024+ blueprint.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to generatedQuestions.js")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to markdown report")
    parser.add_argument("--min-hits", type=int, default=2, help="Minimum hit count threshold for weak topics")
    parser.add_argument("--stdout", action="store_true", help="Print markdown report to stdout")
    args = parser.parse_args()

    questions = load_questions(args.input)

    analyses: Dict[str, Dict[str, object]] = {}
    for subject, rules in BLUEPRINT.items():
        subject_items = [item for item in questions if str(item.get("subject", "")) == subject]
        analyses[subject] = analyze_subject(subject_items, rules, args.min_hits)

    report = build_markdown_report(questions, analyses, args.min_hits, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    print(f"Report generated: {args.output}")
    print(f"Question count: {len(questions)}")
    for subject in BLUEPRINT:
        result = analyses[subject]
        print(
            f"- {subject}: {result['covered_topics']}/{result['total_topics']} topics covered, "
            f"unmatched={len(result['unmatched'])}, weak={len(result['weak_topics'])}"
        )

    if args.stdout:
        print("\n" + report)


if __name__ == "__main__":
    main()
