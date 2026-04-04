#!/usr/bin/env python3
"""Build reliability tiers for generated question bank.

Inputs:
- src/data/generatedQuestions.js
- src/data/learningAssets.js

Outputs:
- src/data/questionReliability.js
- reports/question_reliability_report.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = ROOT / "src/data/generatedQuestions.js"
DEFAULT_LEARNING_ASSETS = ROOT / "src/data/learningAssets.js"
DEFAULT_OUTPUT = ROOT / "src/data/questionReliability.js"
DEFAULT_REPORT = ROOT / "reports/question_reliability_report.md"

STOPWORDS = {
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
    "한",
    "대한",
    "기초",
    "개요",
    "전략",
    "관리",
    "분석",
    "기법",
    "이론",
    "활용",
    "구성",
}

NOISE_PENALTY = {
    "source_watermark": 8,
    "page_footer_text": 8,
    "broken_prefix": 7,
    "trailing_page_token": 6,
    "partial_legal_fragment": 5,
    "short_question": 5,
    "short_option": 4,
    "duplicated_option": 2,
}


def normalize_for_match(text: str) -> str:
    text = str(text).replace("\u00a0", " ").lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    return text


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


def load_generated_questions(path: Path) -> List[Dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    payload = extract_export_payload(text, "generatedQuestionsBank", "generatedQuestionsMeta")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError("generatedQuestionsBank is not an array.")
    return data


def load_learning_assets(path: Path) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, object]]]:
    text = path.read_text(encoding="utf-8")
    frequent_payload = extract_export_payload(text, "frequent100Topics", "coreSummaryBySubject")
    core_payload = extract_export_payload(text, "coreSummaryBySubject", "learningAssetsMeta")
    frequent = json.loads(frequent_payload)
    core = json.loads(core_payload)
    if not isinstance(frequent, list) or not isinstance(core, dict):
        raise RuntimeError("learning assets payload shape is invalid.")
    return frequent, core


def build_qid(item: Dict[str, object]) -> str:
    source = str(item.get("source", "")).strip()
    number = int(item.get("number", 0))
    return f"{source}-Q{number}"


def tokenize_korean_phrase(text: str) -> List[str]:
    tokens = re.split(r"[^0-9a-zA-Z가-힣]+", str(text))
    out: List[str] = []
    for raw in tokens:
        token = raw.strip()
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        out.append(token)
    deduped: List[str] = []
    seen = set()
    for token in out:
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def build_frequent_matchers(frequent_topics: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    raw_entries: List[Dict[str, object]] = []
    keyword_df = Counter()

    for topic in frequent_topics:
        title = str(topic.get("title", "")).strip()
        keywords = [title]
        keywords.extend(str(kw).strip() for kw in topic.get("keywords", []) if str(kw).strip())
        keywords.extend(tokenize_korean_phrase(title))

        normalized_candidates = []
        for keyword in keywords:
            n = normalize_for_match(keyword)
            if len(n) < 3:
                continue
            normalized_candidates.append(n)

        deduped = sorted(set(normalized_candidates), key=len, reverse=True)
        if not deduped:
            continue

        raw_entries.append(
            {
                "number": int(topic.get("number", 0)),
                "title": title,
                "title_keyword": normalize_for_match(title),
                "keywords": deduped,
            }
        )
        for keyword in deduped:
            keyword_df[keyword] += 1

    matchers: List[Dict[str, object]] = []
    for entry in raw_entries:
        filtered_keywords = []
        for keyword in entry["keywords"]:
            too_common = keyword_df[keyword] > 3 and len(keyword) < 8
            too_short = len(keyword) < 4
            if too_short:
                continue
            if too_common:
                continue
            filtered_keywords.append(keyword)

        if entry["title_keyword"] and entry["title_keyword"] not in filtered_keywords:
            filtered_keywords.insert(0, entry["title_keyword"])

        filtered_keywords = sorted(set(filtered_keywords), key=len, reverse=True)
        if not filtered_keywords:
            continue

        matchers.append(
            {
                "number": entry["number"],
                "title": entry["title"],
                "keywords": filtered_keywords,
            }
        )

    return matchers


def build_core_matchers(core_summary_by_subject: Dict[str, Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    subject_matchers: Dict[str, List[Dict[str, object]]] = {}
    for subject, payload in core_summary_by_subject.items():
        points = payload.get("keyPoints", [])
        if not isinstance(points, list):
            continue

        matchers: List[Dict[str, object]] = []
        for point in points:
            point_text = str(point).strip()
            if not point_text:
                continue
            normalized_point = normalize_for_match(point_text)
            tokens = [normalize_for_match(token) for token in tokenize_korean_phrase(point_text)]
            tokens = [token for token in tokens if len(token) >= 2]
            matchers.append(
                {
                    "point": point_text,
                    "normalized_point": normalized_point,
                    "tokens": tokens[:8],
                }
            )

        subject_matchers[subject] = matchers

    return subject_matchers


def match_frequent(normalized_text: str, matchers: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    matched = []
    for matcher in matchers:
        keywords = matcher.get("keywords", [])
        if any(keyword in normalized_text for keyword in keywords):
            matched.append({"number": matcher["number"], "title": matcher["title"]})
    return matched


def match_core(normalized_text: str, subject: str, core_matchers: Dict[str, List[Dict[str, object]]]) -> List[str]:
    subject_rules = core_matchers.get(subject, [])
    matched_points: List[str] = []

    for rule in subject_rules:
        normalized_point = str(rule.get("normalized_point", ""))
        tokens = [token for token in rule.get("tokens", []) if token]
        phrase_match = len(normalized_point) >= 4 and normalized_point in normalized_text
        token_hits = sum(1 for token in tokens if token in normalized_text)
        token_match = token_hits >= 2

        if phrase_match or token_match:
            matched_points.append(str(rule.get("point", "")))

    return matched_points


def detect_noise(question_text: str, options: Sequence[str]) -> List[str]:
    flags: List[str] = []
    question = str(question_text).strip()
    normalized_q = normalize_for_match(question)
    merged = f"{question} {' '.join(str(option) for option in options)}"
    normalized_merged = normalize_for_match(merged)

    if "wwwcomcbtcom" in normalized_merged:
        flags.append("source_watermark")
    if "2급a형" in normalized_merged or "2급b형" in normalized_merged:
        flags.append("page_footer_text")
    if re.search(r"^\d{1,2}\.,", question):
        flags.append("broken_prefix")
    if re.search(r"-\s*\d+\s*$", question):
        flags.append("trailing_page_token")
    if "일부개정" in normalized_q and not any(
        word in normalized_q for word in ("법", "시행령", "시행규칙")
    ):
        flags.append("partial_legal_fragment")
    if len(normalized_q) < 12:
        flags.append("short_question")

    normalized_options = [normalize_for_match(option) for option in options]

    def is_short_numeric_option(option_raw: str, option_normalized: str) -> bool:
        if not option_normalized:
            return False
        compact = re.sub(r"\s+", "", option_raw)
        compact = compact.lstrip("①②③④⑤")
        return bool(
            re.fullmatch(
                r"[0-9]+(?:\.[0-9]+)?(?:%|점|회|개|원|년|월|일|배|명|곳|kg|km)?",
                compact,
            )
        )

    if any(
        len(option) < 4 and not is_short_numeric_option(raw, option)
        for raw, option in zip(options, normalized_options)
    ):
        flags.append("short_option")
    if len(set(normalized_options)) != len(normalized_options):
        flags.append("duplicated_option")

    deduped = []
    seen = set()
    for flag in flags:
        if flag not in seen:
            deduped.append(flag)
            seen.add(flag)
    return deduped


def answer_basis_from_explanation(explanation: str) -> str:
    if "확정답안" in explanation:
        return "final"
    if "가답안" in explanation:
        return "tentative"
    return "unknown"


def compute_reliability(
    item: Dict[str, object],
    frequent_matchers: Sequence[Dict[str, object]],
    core_matchers: Dict[str, List[Dict[str, object]]],
) -> Dict[str, object]:
    qid = build_qid(item)
    question = str(item.get("question", ""))
    options = item.get("options", [])
    if not isinstance(options, list):
        options = []
    options = [str(option) for option in options]
    explanation = str(item.get("explanation", ""))
    subject = str(item.get("subject", ""))
    normalized_text = normalize_for_match(" ".join([question] + options))

    frequent_matches = match_frequent(normalized_text, frequent_matchers)
    core_matches = match_core(normalized_text, subject, core_matchers)
    noise_flags = detect_noise(question, options)

    basis = answer_basis_from_explanation(explanation)
    basis_score = 45 if basis == "final" else 30 if basis == "tentative" else 15

    frequent_count = len(frequent_matches)
    core_count = len(core_matches)

    score = basis_score
    if frequent_count > 0:
        score += 20 + min(15, (frequent_count - 1) * 5)
    if core_count > 0:
        score += 15 + min(10, (core_count - 1) * 5)
    if frequent_count > 0 and core_count > 0:
        score += 10

    quality_penalty = sum(NOISE_PENALTY.get(flag, 5) for flag in noise_flags)
    quality_score = max(0, 20 - min(20, quality_penalty))
    score += quality_score
    score = max(0, min(100, score))

    strict_verified = (
        frequent_count > 0
        and core_count > 0
        and len(noise_flags) == 0
        and score >= 75
    )

    if strict_verified:
        tier = "gold"
    elif frequent_count > 0 and core_count > 0 and len(noise_flags) <= 1 and score >= 72:
        tier = "gold"
    elif (frequent_count > 0 or core_count > 0) and len(noise_flags) <= 2 and score >= 60:
        tier = "silver"
    else:
        tier = "review"

    return {
        "qid": qid,
        "tier": tier,
        "strictVerified": strict_verified,
        "score": score,
        "basis": basis,
        "frequentMatchCount": frequent_count,
        "frequentTopicNumbers": [match["number"] for match in frequent_matches[:8]],
        "coreMatchCount": core_count,
        "corePoints": core_matches[:8],
        "noiseFlags": noise_flags,
    }


def build_report(
    reliability_rows: Sequence[Dict[str, object]],
    questions: Sequence[Dict[str, object]],
    output_path: Path,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_qid = {build_qid(question): question for question in questions}

    tier_counter = Counter(row["tier"] for row in reliability_rows)
    strict_count = sum(1 for row in reliability_rows if row["strictVerified"])
    basis_counter = Counter(row["basis"] for row in reliability_rows)
    subject_tier: Dict[str, Counter] = defaultdict(Counter)
    noise_counter = Counter()

    for row in reliability_rows:
        question = by_qid.get(row["qid"], {})
        subject = str(question.get("subject", "N/A"))
        subject_tier[subject][row["tier"]] += 1
        for flag in row["noiseFlags"]:
            noise_counter[flag] += 1

    review_samples = [row for row in reliability_rows if row["tier"] == "review"][:25]
    review_lines = []
    for row in review_samples:
        question = by_qid.get(row["qid"], {})
        review_lines.append(
            f"- {row['qid']} ({question.get('subject', 'N/A')}) "
            f"| score={row['score']} basis={row['basis']} "
            f"| frequent={row['frequentMatchCount']} core={row['coreMatchCount']} "
            f"| noise={','.join(row['noiseFlags']) if row['noiseFlags'] else '-'}"
        )

    lines: List[str] = []
    lines.append("# 문제은행 정답 신뢰도 리포트")
    lines.append("")
    lines.append(f"- 생성시각: {now}")
    lines.append(f"- 출력파일: `{output_path}`")
    lines.append(f"- 전체 문항: {len(reliability_rows)}")
    lines.append(
        f"- 등급 분포: Gold {tier_counter['gold']} / Silver {tier_counter['silver']} / Review {tier_counter['review']}"
    )
    lines.append(f"- Strict(완전매치): {strict_count}")
    lines.append("")
    lines.append("## 정답 기준 분포")
    lines.append("")
    lines.append(f"- 확정답안(final): {basis_counter['final']}")
    lines.append(f"- 가답안(tentative): {basis_counter['tentative']}")
    lines.append(f"- 미확인(unknown): {basis_counter['unknown']}")
    lines.append("")
    lines.append("## 과목별 등급 분포")
    lines.append("")
    lines.append("| 과목 | Gold | Silver | Review | 합계 |")
    lines.append("|---|---:|---:|---:|---:|")
    for subject in ("유통물류일반", "상권분석", "유통마케팅", "유통정보"):
        counter = subject_tier.get(subject, Counter())
        total = counter["gold"] + counter["silver"] + counter["review"]
        lines.append(
            f"| {subject} | {counter['gold']} | {counter['silver']} | {counter['review']} | {total} |"
        )
    lines.append("")
    lines.append("## OCR/파싱 노이즈 상위")
    lines.append("")
    if noise_counter:
        for flag, count in noise_counter.most_common(10):
            lines.append(f"- {flag}: {count}")
    else:
        lines.append("- 노이즈 플래그 없음")
    lines.append("")
    lines.append("## Review 샘플 (최대 25개)")
    lines.append("")
    if review_lines:
        lines.extend(review_lines)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## 해석")
    lines.append("")
    lines.append("- Strict(완전매치): 빈출/핵심 동시 매칭 + 노이즈 없음 + 고신뢰 점수.")
    lines.append("- Gold: 자동 출제용으로 우선 권장되는 문항.")
    lines.append("- Silver: 학습용으로는 사용 가능하지만 수기 검토 권장.")
    lines.append("- Review: 자동 출제 제외 권장.")
    lines.append("")

    return "\n".join(lines)


def write_js(
    output_path: Path,
    reliability_rows: Sequence[Dict[str, object]],
) -> None:
    by_qid = {row["qid"]: row for row in reliability_rows}
    gold = [row["qid"] for row in reliability_rows if row["tier"] == "gold"]
    silver = [row["qid"] for row in reliability_rows if row["tier"] == "silver"]
    review = [row["qid"] for row in reliability_rows if row["tier"] == "review"]
    strict = [row["qid"] for row in reliability_rows if row["strictVerified"]]

    score_values = [int(row["score"]) for row in reliability_rows]
    meta = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(reliability_rows),
        "tierCounts": {
            "gold": len(gold),
            "silver": len(silver),
            "review": len(review),
        },
        "strictCount": len(strict),
        "score": {
            "min": min(score_values) if score_values else 0,
            "max": max(score_values) if score_values else 0,
            "avg": round(sum(score_values) / max(1, len(score_values)), 2),
        },
    }

    lines = [
        "// Auto-generated by scripts/build_question_reliability.py",
        "// Do not edit manually.",
        "",
        f"export const questionReliabilityByQid = {json.dumps(by_qid, ensure_ascii=False, indent=2)};",
        "",
        f"export const goldQuestionQids = {json.dumps(gold, ensure_ascii=False, indent=2)};",
        "",
        f"export const silverQuestionQids = {json.dumps(silver, ensure_ascii=False, indent=2)};",
        "",
        f"export const reviewQuestionQids = {json.dumps(review, ensure_ascii=False, indent=2)};",
        "",
        f"export const strictVerifiedQuestionQids = {json.dumps(strict, ensure_ascii=False, indent=2)};",
        "",
        f"export const questionReliabilityMeta = {json.dumps(meta, ensure_ascii=False, indent=2)};",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_reliability(
    questions_path: Path,
    learning_assets_path: Path,
) -> List[Dict[str, object]]:
    questions = load_generated_questions(questions_path)
    frequent_topics, core_summary_by_subject = load_learning_assets(learning_assets_path)
    frequent_matchers = build_frequent_matchers(frequent_topics)
    core_matchers = build_core_matchers(core_summary_by_subject)

    rows = [
        compute_reliability(question, frequent_matchers, core_matchers)
        for question in questions
    ]
    rows.sort(key=lambda row: row["qid"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build question reliability tiers.")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--learning-assets", type=Path, default=DEFAULT_LEARNING_ASSETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    reliability_rows = build_reliability(args.questions, args.learning_assets)
    questions = load_generated_questions(args.questions)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_js(args.output, reliability_rows)

    report = build_report(reliability_rows, questions, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    counts = Counter(row["tier"] for row in reliability_rows)
    strict_count = sum(1 for row in reliability_rows if row["strictVerified"])
    print(f"Generated: {args.output}")
    print(f"Report: {args.report}")
    print(
        "Tier counts: "
        f"gold={counts['gold']}, silver={counts['silver']}, review={counts['review']}, strict={strict_count}"
    )


if __name__ == "__main__":
    main()
