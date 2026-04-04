#!/usr/bin/env python3
"""Verify review-tier answers via web search and external answer sheets.

Workflow:
1) Load target review queue rows (default: priority A only)
2) Search web candidates per exam source (year-round)
3) Extract answer maps from page text / attached xlsx/pdf
4) Compare with local generated answer map
5) Export per-question verification results and summary report

Outputs:
- reports/web_review_verification.csv
- reports/web_review_verification_summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin, urlparse

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_QUEUE = ROOT / "reports/review_queue.csv"
DEFAULT_QUESTIONS = ROOT / "src/data/generatedQuestions.js"
DEFAULT_OUTPUT_CSV = ROOT / "reports/web_review_verification.csv"
DEFAULT_OUTPUT_SUMMARY = ROOT / "reports/web_review_verification_summary.md"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}

FILE_EXTENSIONS = (".xlsx", ".xls", ".pdf")

DOMAIN_TRUST_SCORE = {
    "license.korcham.net": 100,
    "download.blog.naver.com": 65,
    "blog.naver.com": 60,
    "www.gunsys.com": 55,
    "gunsys.com": 55,
    "utong.sinjiwonedu.co.kr": 50,
    "landmeca.sinjiwonedu.co.kr": 50,
    "kisa.sinjiwonedu.co.kr": 50,
    "sinjiwonedu.co.kr": 50,
}


@dataclass
class Candidate:
    source: str
    query: str
    url: str
    title: str


@dataclass
class Evidence:
    source: str
    candidate_url: str
    evidence_url: str
    title: str
    answer_map: Dict[int, str]
    matched_count: int
    mismatched_count: int
    coverage_count: int
    match_rate: float
    source_context_score: float
    domain_score: int
    total_score: float


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


def load_local_answers(path: Path) -> Tuple[Dict[str, Dict[int, str]], Dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    payload = extract_export_payload(text, "generatedQuestionsBank", "generatedQuestionsMeta")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise RuntimeError("generatedQuestionsBank is not an array.")

    by_source: Dict[str, Dict[int, str]] = defaultdict(dict)
    by_qid: Dict[str, str] = {}

    for item in data:
        source = str(item["source"])
        number = int(item["number"])
        answer_digit = str(int(item["answer"]) + 1)
        by_source[source][number] = answer_digit
        by_qid[f"{source}-Q{number}"] = answer_digit

    return by_source, by_qid


def load_review_queue(path: Path, priorities: Sequence[str]) -> List[Dict[str, str]]:
    priority_set = {p.strip().upper() for p in priorities}
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("priority", "").upper() in priority_set:
                rows.append(row)
    return rows


def parse_source_info(source: str) -> Tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-R(\d+)", source)
    if not match:
        raise ValueError(f"Invalid source format: {source}")
    return int(match.group(1)), int(match.group(2))


def build_queries_for_source(source: str) -> List[str]:
    year, round_num = parse_source_info(source)
    return [
        f"{year}년 제{round_num}회 유통관리사 2급 확정답안",
        f"{year}년 제{round_num}회 유통관리사 2급 가답안",
        f"{year}년 {round_num}회 유통관리사 2급 답안",
    ]


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme and url.startswith("//"):
        return "https:" + url
    if not parsed.scheme:
        return "https://" + url
    return url


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def domain_score(url: str) -> int:
    domain = domain_of(url)
    if domain in DOMAIN_TRUST_SCORE:
        return DOMAIN_TRUST_SCORE[domain]
    # fall back to parent domain matching
    for known, score in DOMAIN_TRUST_SCORE.items():
        if domain.endswith("." + known):
            return score
    return 30


def search_naver(query: str, max_results: int = 15) -> List[Tuple[str, str]]:
    url = (
        "https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query="
        + quote(query)
    )
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    results: List[Tuple[str, str]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href.startswith("http"):
            continue
        if "search.naver.com" in href:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if len(title) < 4:
            continue
        key = (href, title)
        if key in seen:
            continue
        seen.add(key)
        results.append((href, title))
        if len(results) >= max_results:
            break
    return results


def extract_naver_blog_iframe_url(html: str, base_url: str) -> Optional[str]:
    match = re.search(r'id="mainFrame"[^>]*src="([^"]+)"', html)
    if not match:
        return None
    src = match.group(1)
    return urljoin(base_url, src)


def fetch_html(url: str) -> Tuple[str, str]:
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    text = response.text
    final_url = response.url

    if "blog.naver.com" in domain_of(final_url):
        iframe_url = extract_naver_blog_iframe_url(text, final_url)
        if iframe_url:
            inner = requests.get(iframe_url, headers=REQUEST_HEADERS, timeout=25)
            inner.raise_for_status()
            text = inner.text
            final_url = inner.url

    return final_url, text


def extract_attachment_urls(soup: BeautifulSoup, base_url: str) -> List[str]:
    urls: List[str] = []

    # Standard links
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        href_lc = href.lower()
        if href_lc.endswith(FILE_EXTENSIONS) or any(ext in href_lc for ext in FILE_EXTENSIONS):
            urls.append(urljoin(base_url, normalize_url(href)))

    # data-linkdata JSON often contains download URLs on Naver blogs.
    for tag in soup.find_all(attrs={"data-linkdata": True}):
        raw = str(tag.get("data-linkdata", "")).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
            link = str(payload.get("link", "")).strip()
            if link and any(ext in link.lower() for ext in FILE_EXTENSIONS):
                urls.append(normalize_url(link))
        except Exception:
            continue

    # Raw text fallback for hidden links.
    html = str(soup)
    for match in re.findall(r"https?://[^\"'<>]+", html, flags=re.I):
        if any(ext in match.lower() for ext in FILE_EXTENSIONS):
            urls.append(match)
    for match in re.findall(r"//download\.blog\.naver\.com/[^\"'<>]+", html, flags=re.I):
        if any(ext in match.lower() for ext in FILE_EXTENSIONS):
            urls.append("https:" + match)

    deduped: List[str] = []
    seen = set()
    for url in urls:
        normalized = normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def normalize_answer_text(text: str) -> str:
    circled = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
    for src, dst in circled.items():
        text = text.replace(src, dst)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def parse_answer_map_from_text(text: str) -> Dict[int, str]:
    text = normalize_answer_text(text)
    answer_map: Dict[int, str] = {}

    # Pattern: question number + A + B
    triple = re.compile(r"\b(\d{1,2})\s+([1-5](?:,[1-5])*)\s+([1-5](?:,[1-5])*)\b")
    for q_raw, a_raw, _ in triple.findall(text):
        q = int(q_raw)
        if 1 <= q <= 90 and re.fullmatch(r"[1-5]", a_raw):
            answer_map[q] = a_raw
    if len(answer_map) >= 70:
        return answer_map

    # Fallback for single-line "1 3 2 5 ..." style
    pair = re.compile(r"\b(\d{1,2})\s*[:.)]?\s*([1-5])\b")
    tmp: Dict[int, str] = {}
    for q_raw, a_raw in pair.findall(text):
        q = int(q_raw)
        if 1 <= q <= 90 and q not in tmp:
            tmp[q] = a_raw
    if len(tmp) >= 75 and 1 in tmp:
        return tmp

    return answer_map


def parse_answer_map_from_xlsx_bytes(content: bytes) -> Dict[int, str]:
    answer_map: Dict[int, str] = {}
    book = pd.read_excel(BytesIO(content), sheet_name=None, header=None)
    for _, df in book.items():
        rows, cols = df.shape
        for r in range(rows):
            for c in range(cols):
                q = df.iat[r, c]
                a = df.iat[r, c + 1] if c + 1 < cols else None
                if pd.isna(q) or pd.isna(a):
                    continue
                q_raw = str(q).strip()
                a_raw = str(a).strip()
                if re.fullmatch(r"\d{1,2}", q_raw) and re.fullmatch(r"[1-5]", a_raw):
                    qi = int(q_raw)
                    if 1 <= qi <= 90:
                        answer_map[qi] = a_raw
    if len(answer_map) >= 70:
        return answer_map

    # text fallback
    merged = "\n".join(
        " ".join(str(v).strip() for v in row if str(v).strip() and str(v).strip().lower() != "nan")
        for _, row in next(iter(book.items()))[1].iterrows()
    )
    return parse_answer_map_from_text(merged)


def parse_answer_map_from_pdf_bytes(content: bytes) -> Dict[int, str]:
    text_chunks: List[str] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text_chunks.append(page.extract_text() or "")
    text = "\n".join(text_chunks)
    return parse_answer_map_from_text(text)


def extract_answer_maps_from_candidate(candidate: Candidate) -> List[Tuple[str, Dict[int, str], str]]:
    """Return list of (evidence_url, answer_map, title_hint)."""
    result: List[Tuple[str, Dict[int, str], str]] = []
    final_url, html = fetch_html(candidate.url)
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)
    page_map = parse_answer_map_from_text(page_text)
    if len(page_map) >= 70:
        result.append((final_url, page_map, candidate.title))

    attachment_urls = extract_attachment_urls(soup, final_url)
    for attachment_url in attachment_urls[:12]:
        try:
            response = requests.get(attachment_url, headers=REQUEST_HEADERS, timeout=25)
            response.raise_for_status()
            content = response.content
            lower_url = attachment_url.lower()
            parsed_map: Dict[int, str] = {}
            if ".xlsx" in lower_url or ".xls" in lower_url:
                parsed_map = parse_answer_map_from_xlsx_bytes(content)
            elif ".pdf" in lower_url:
                parsed_map = parse_answer_map_from_pdf_bytes(content)
            else:
                continue
            if len(parsed_map) >= 70:
                result.append((attachment_url, parsed_map, candidate.title))
        except Exception:
            continue

    return result


def source_context_score(source: str, text_blob: str) -> float:
    year, round_num = parse_source_info(source)
    n = re.sub(r"\s+", "", text_blob).lower()
    year_hit = str(year) in n
    round_hit = f"{round_num}회" in n or f"제{round_num}회" in n or f"r{round_num}" in n
    return (0.5 if year_hit else 0.0) + (0.5 if round_hit else 0.0)


def evaluate_evidence(
    source: str,
    candidate: Candidate,
    evidence_url: str,
    answer_map: Dict[int, str],
    local_answers_by_source: Dict[str, Dict[int, str]],
) -> Evidence:
    local_map = local_answers_by_source[source]
    overlap = sorted(set(local_map.keys()) & set(answer_map.keys()))
    coverage = len(overlap)
    matched = sum(1 for q in overlap if local_map[q] == answer_map[q])
    mismatched = coverage - matched
    rate = matched / coverage if coverage else 0.0

    trust = domain_score(evidence_url)
    context_score = source_context_score(source, f"{candidate.title} {candidate.query} {evidence_url}")
    total_score = trust + (coverage * 0.45) + (rate * 50) + (context_score * 20)

    return Evidence(
        source=source,
        candidate_url=candidate.url,
        evidence_url=evidence_url,
        title=candidate.title,
        answer_map=answer_map,
        matched_count=matched,
        mismatched_count=mismatched,
        coverage_count=coverage,
        match_rate=rate,
        source_context_score=context_score,
        domain_score=trust,
        total_score=total_score,
    )


def collect_candidates_for_source(source: str, max_results_per_query: int = 8) -> List[Candidate]:
    candidates: List[Candidate] = []
    seen = set()
    for query in build_queries_for_source(source):
        try:
            pairs = search_naver(query, max_results=max_results_per_query)
        except Exception:
            continue
        for url, title in pairs:
            key = url
            if key in seen:
                continue
            seen.add(key)
            candidates.append(Candidate(source=source, query=query, url=url, title=title))
    return candidates


def choose_best_evidence_for_source(
    source: str,
    local_answers_by_source: Dict[str, Dict[int, str]],
    sleep_sec: float = 0.2,
) -> Tuple[Optional[Evidence], List[Evidence]]:
    candidates = collect_candidates_for_source(source)
    evidences: List[Evidence] = []

    for candidate in candidates[:15]:
        try:
            maps = extract_answer_maps_from_candidate(candidate)
        except Exception:
            continue
        for evidence_url, answer_map, _ in maps:
            evidence = evaluate_evidence(
                source=source,
                candidate=candidate,
                evidence_url=evidence_url,
                answer_map=answer_map,
                local_answers_by_source=local_answers_by_source,
            )
            evidences.append(evidence)
        time.sleep(sleep_sec)

    if not evidences:
        return None, []

    evidences.sort(
        key=lambda e: (
            e.total_score,
            e.match_rate,
            e.coverage_count,
            -e.mismatched_count,
        ),
        reverse=True,
    )

    best = evidences[0]
    # acceptance gate: meaningful coverage + decent consistency
    if best.coverage_count < 40 or best.match_rate < 0.55:
        return None, evidences
    return best, evidences


def verify_rows(
    target_rows: Sequence[Dict[str, str]],
    local_answers_by_source: Dict[str, Dict[int, str]],
    local_answers_by_qid: Dict[str, str],
) -> Tuple[List[Dict[str, object]], Dict[str, Optional[Evidence]], Dict[str, List[Evidence]]]:
    sources = sorted({row["source"] for row in target_rows})
    best_by_source: Dict[str, Optional[Evidence]] = {}
    evidences_by_source: Dict[str, List[Evidence]] = {}

    for source in sources:
        best, all_evidences = choose_best_evidence_for_source(source, local_answers_by_source)
        best_by_source[source] = best
        evidences_by_source[source] = all_evidences

    verified_rows: List[Dict[str, object]] = []
    for row in target_rows:
        qid = row["qid"]
        source = row["source"]
        number = int(row["number"])
        local_answer = local_answers_by_qid.get(qid, "")
        best = best_by_source.get(source)

        status = "no_web_evidence"
        web_answer = ""
        evidence_url = ""
        evidence_domain = ""
        match_rate = ""
        coverage = ""
        mismatch = ""

        if best:
            evidence_url = best.evidence_url
            evidence_domain = domain_of(best.evidence_url)
            match_rate = f"{best.match_rate:.3f}"
            coverage = str(best.coverage_count)
            mismatch = str(best.mismatched_count)
            web_answer = best.answer_map.get(number, "")
            if web_answer:
                status = "verified_match" if web_answer == local_answer else "web_mismatch"
            else:
                status = "not_in_web_map"

        verified_rows.append(
            {
                "priority": row.get("priority", ""),
                "qid": qid,
                "source": source,
                "number": number,
                "subject": row.get("subject", ""),
                "basis": row.get("basis", ""),
                "local_answer": local_answer,
                "web_answer": web_answer,
                "status": status,
                "evidence_domain": evidence_domain,
                "evidence_url": evidence_url,
                "source_match_rate": match_rate,
                "source_coverage": coverage,
                "source_mismatch_count": mismatch,
                "noise_flags": row.get("noise_flags", ""),
                "question_preview": row.get("question_preview", ""),
            }
        )

    return verified_rows, best_by_source, evidences_by_source


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_summary_markdown(
    rows: Sequence[Dict[str, object]],
    best_by_source: Dict[str, Optional[Evidence]],
    evidences_by_source: Dict[str, List[Evidence]],
    priorities: Sequence[str],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_counter = Counter(str(row["status"]) for row in rows)
    source_counter = Counter(str(row["source"]) for row in rows)

    lines: List[str] = []
    lines.append("# 웹 검색 기반 정답 교차검증 리포트")
    lines.append("")
    lines.append(f"- 생성시각: {now}")
    lines.append(f"- 대상 우선순위: {', '.join(priorities)}")
    lines.append(f"- 대상 문항 수: {len(rows)}")
    lines.append(
        "- 상태 분포: "
        f"verified_match {status_counter['verified_match']} / "
        f"web_mismatch {status_counter['web_mismatch']} / "
        f"not_in_web_map {status_counter['not_in_web_map']} / "
        f"no_web_evidence {status_counter['no_web_evidence']}"
    )
    lines.append("")

    lines.append("## 소스별 최적 근거")
    lines.append("")
    for source in sorted(source_counter.keys()):
        best = best_by_source.get(source)
        if not best:
            lines.append(f"- {source}: 근거 문서 확보 실패")
            continue
        lines.append(
            f"- {source}: {best.evidence_url} "
            f"(coverage={best.coverage_count}, match={best.match_rate:.3f}, mismatch={best.mismatched_count}, score={best.total_score:.1f})"
        )
    lines.append("")

    mismatch_rows = [row for row in rows if row["status"] == "web_mismatch"]
    lines.append("## 불일치 문항 (web_mismatch)")
    lines.append("")
    if mismatch_rows:
        for row in mismatch_rows[:80]:
            lines.append(
                f"- {row['qid']} ({row['subject']}) local={row['local_answer']} web={row['web_answer']} "
                f"| evidence={row['evidence_domain']}"
            )
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 참고")
    lines.append("")
    lines.append("- 본 검증은 웹 공개 자료 기반 자동 비교이며, 최종 확정은 사람 검토가 필요합니다.")
    lines.append("- `web_mismatch`와 `no_web_evidence`는 수기검수 우선 대상입니다.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify review answers via web search.")
    parser.add_argument("--review-queue", type=Path, default=DEFAULT_REVIEW_QUEUE)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--priorities", type=str, default="A", help="Comma-separated priorities, e.g. A,B")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-summary", type=Path, default=DEFAULT_OUTPUT_SUMMARY)
    args = parser.parse_args()

    priorities = [p.strip().upper() for p in args.priorities.split(",") if p.strip()]
    if not priorities:
        priorities = ["A"]

    local_answers_by_source, local_answers_by_qid = load_local_answers(args.questions)
    target_rows = load_review_queue(args.review_queue, priorities)
    if not target_rows:
        print("No target review rows found for requested priorities.")
        return

    verified_rows, best_by_source, evidences_by_source = verify_rows(
        target_rows, local_answers_by_source, local_answers_by_qid
    )

    write_csv(args.output_csv, verified_rows)
    summary = build_summary_markdown(verified_rows, best_by_source, evidences_by_source, priorities)
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(summary, encoding="utf-8")

    c = Counter(row["status"] for row in verified_rows)
    print(f"Target rows: {len(verified_rows)}")
    print(
        "Status: "
        f"verified_match={c['verified_match']}, "
        f"web_mismatch={c['web_mismatch']}, "
        f"not_in_web_map={c['not_in_web_map']}, "
        f"no_web_evidence={c['no_web_evidence']}"
    )
    print(f"CSV: {args.output_csv}")
    print(f"Summary: {args.output_summary}")


if __name__ == "__main__":
    main()
