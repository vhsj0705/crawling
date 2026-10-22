"""skills.sh 리더보드(All Time / Trending / Hot) 스냅샷 수집 -> 날짜별 CSV.

공식 API(/api/v1/)는 Vercel OIDC 인증이 필요하고 robots.txt 에서도 막혀 있으므로,
크롤링이 허용된 리더보드 HTML 페이지에 포함된 Next.js RSC 페이로드("initialSkills" 배열)를 파싱한다.
페이지당 상위 약 600개가 순위 순서대로 들어 있다.

    python scrape_leaderboard.py                     # data/<오늘(KST)>.csv 생성
    python scrape_leaderboard.py --date 2026-10-22   # 파일명 날짜 지정
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time

import requests

BASE_URL = "https://www.skills.sh"
VIEWS = {"all-time": "/", "trending": "/trending", "hot": "/hot"}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KST = dt.timezone(dt.timedelta(hours=9))
# 구조가 바뀌어 일부만 파싱되는 경우를 잡기 위한 최소 건수
MIN_ROWS_PER_VIEW = 100

FIELDS = [
    "date", "view", "rank", "source", "skill_id", "name", "installs",
    "installs_yesterday", "change", "weekly_installs", "is_official",
]

PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (leaderboard snapshot bot)"})
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            print(f"  재시도 {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(2 ** (attempt + 1))


def parse_skills(html):
    """HTML 안의 RSC 청크를 이어 붙인 뒤 첫 번째 "initialSkills" 배열을 디코드한다."""
    payload = "".join(json.loads('"' + c + '"') for c in PUSH_RE.findall(html))
    idx = payload.find('"initialSkills":')
    if idx < 0:
        raise ValueError("initialSkills 를 찾지 못함 (페이지 구조 변경?)")
    skills, _ = json.JSONDecoder().raw_decode(payload, idx + len('"initialSkills":'))
    return skills


def to_rows(date, view, skills):
    for rank, s in enumerate(skills, 1):
        weekly = s.get("weeklyInstalls")
        yield {
            "date": date,
            "view": view,
            "rank": rank,
            "source": s["source"],
            "skill_id": s["skillId"],
            "name": s.get("name", s["skillId"]),
            "installs": s.get("installs", ""),
            "installs_yesterday": s.get("installsYesterday", ""),
            "change": s.get("change", ""),
            "weekly_installs": ";".join(map(str, weekly)) if weekly else "",
            "is_official": int(bool(s.get("isOfficial"))),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="파일명/date 컬럼에 쓸 날짜 YYYY-MM-DD (기본: 오늘 KST)")
    args = ap.parse_args()
    date = args.date or dt.datetime.now(KST).date().isoformat()

    rows = []
    for view, path in VIEWS.items():
        skills = parse_skills(fetch(BASE_URL + path))
        print(f"{view}: {len(skills)}건")
        if len(skills) < MIN_ROWS_PER_VIEW:
            sys.exit(f"{view} 파싱 결과가 {len(skills)}건뿐 -> 구조 변경 의심, 중단")
        rows.extend(to_rows(date, view, skills))
        time.sleep(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    out = os.path.join(DATA_DIR, f"{date}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {out} ({len(rows)}행)")


if __name__ == "__main__":
    main()
