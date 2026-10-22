"""data/ 의 최신 스냅샷을 직전 스냅샷과 비교해 변동 리포트(REPORT.md)를 만든다.

    python report.py                  # 최신 vs 직전 스냅샷 -> REPORT.md (+ stdout)
    python report.py --date 2026-10-22
"""
import argparse
import csv
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
REPORT_PATH = os.path.join(HERE, "REPORT.md")
TOP_N = 10


def load(path):
    by_view = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["rank"] = int(r["rank"])
            r["installs"] = int(r["installs"]) if r["installs"] else 0
            by_view.setdefault(r["view"], {})[(r["source"], r["skill_id"])] = r
    return by_view


def link(r):
    return f"[{r['name']}](https://skills.sh/{r['source']}/{r['skill_id']}) `{r['source']}`"


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) if rows else "_없음_"


def build(date, cur, prev_date, prev):
    out = [f"# skills.sh 리더보드 리포트 — {date}", ""]
    out.append(f"비교 기준: {prev_date}" if prev else "직전 스냅샷 없음 (첫 수집)")
    out.append("")

    allt = cur.get("all-time", {})
    if prev:
        p_allt = prev.get("all-time", {})
        new = sorted((allt[k] for k in allt.keys() - p_allt.keys()), key=lambda r: r["rank"])
        gone = sorted((p_allt[k] for k in p_allt.keys() - allt.keys()), key=lambda r: r["rank"])
        common = [(allt[k], p_allt[k]) for k in allt.keys() & p_allt.keys()]
        risers = sorted((c for c in common if c[1]["rank"] > c[0]["rank"]),
                        key=lambda c: c[1]["rank"] - c[0]["rank"], reverse=True)[:TOP_N]
        growth = sorted(common, key=lambda c: c[0]["installs"] - c[1]["installs"], reverse=True)[:TOP_N]

        out += [f"## All Time 설치 수 증가 Top {TOP_N}", "",
                table(["순위", "스킬", "설치 수", "증가"],
                      [(c[0]["rank"], link(c[0]), f"{c[0]['installs']:,}",
                        f"+{c[0]['installs'] - c[1]['installs']:,}") for c in growth]), ""]
        out += [f"## All Time 순위 상승 Top {TOP_N}", "",
                table(["순위", "스킬", "변동"],
                      [(c[0]["rank"], link(c[0]), f"▲{c[1]['rank'] - c[0]['rank']} ({c[1]['rank']}→{c[0]['rank']})")
                       for c in risers]), ""]
        out += [f"## All Time 신규 진입 ({len(new)})", "",
                table(["순위", "스킬", "설치 수"], [(r["rank"], link(r), f"{r['installs']:,}") for r in new]), ""]
        out += [f"## All Time 이탈 ({len(gone)})", "",
                table(["직전 순위", "스킬"], [(r["rank"], link(r)) for r in gone]), ""]
    else:
        top = sorted(allt.values(), key=lambda r: r["rank"])[:TOP_N]
        out += [f"## All Time Top {TOP_N}", "",
                table(["순위", "스킬", "설치 수"], [(r["rank"], link(r), f"{r['installs']:,}") for r in top]), ""]

    trend = sorted(cur.get("trending", {}).values(), key=lambda r: r["rank"])[:TOP_N]
    out += [f"## Trending (24h) Top {TOP_N}", "",
            table(["순위", "스킬", "24h 설치"], [(r["rank"], link(r), f"{r['installs']:,}") for r in trend]), ""]

    hot = sorted(cur.get("hot", {}).values(), key=lambda r: r["rank"])[:TOP_N]
    out += [f"## Hot Top {TOP_N}", "",
            table(["순위", "스킬", "최근 1시간", "어제 같은 시간"],
                  [(r["rank"], link(r), f"{r['installs']:,}", r["installs_yesterday"]) for r in hot]), ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="리포트 대상 스냅샷 날짜 (기본: 가장 최신)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    if args.date:
        files = [f for f in files if os.path.basename(f) <= f"{args.date}.csv"]
    if not files:
        sys.exit("스냅샷 CSV 가 없음")
    cur_path = files[-1]
    prev_path = files[-2] if len(files) > 1 else None
    date = os.path.basename(cur_path)[:-4]
    prev_date = os.path.basename(prev_path)[:-4] if prev_path else None

    md = build(date, load(cur_path), prev_date, load(prev_path) if prev_path else None)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
