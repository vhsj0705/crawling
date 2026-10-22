"""서울시 분야별 새소식(news.seoul.go.kr) '강사' 검색 결과 중 강사 구인 공고 수집 -> xlsx -> 막대그래프 -> 이메일.

실행 시점 기준 '지난주 월~금' 에 올라온 글만 대상으로 한다.
검색 페이지(news.seoul.go.kr/?searchWord=강사)는 실제 목록을 아래 iframe 에서 불러온다.
    https://www.seoul.go.kr/realmnews/ex/exlist.do?fetchStart=<page>&sDate=&eDate=&searchWord=강사

    python scrape_instructors.py                      # 수집 + xlsx + 그래프 + 메일(eml) 생성
    python scrape_instructors.py --send               # 위에 더해 SMTP 로 실제 발송
    python scrape_instructors.py --today 2026-10-22   # 기준일 지정
    python scrape_instructors.py --start 2026-03-09 --end 2026-03-13   # 기간 직접 지정

--send 에 필요한 환경변수: SMTP_HOST, SMTP_PORT(기본 587), SMTP_USER, SMTP_PASS, (선택) MAIL_FROM
"""
import argparse
import datetime as dt
import os
import re
import smtplib
import sys
import time
from email.message import EmailMessage

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup
from matplotlib import font_manager

LIST_URL = "https://www.seoul.go.kr/realmnews/ex/exlist.do"
SEARCH_WORD = "강사"
RECIPIENT = "jhlee@8around.kr"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# 강사 구인 공고 판별: 제목에 '강사' + 모집류 단어(결과 발표 제외), 또는 본문에 '강사 모집/선발...' 표현
RECRUIT_RE = re.compile(r"모집|선발|공모|채용|위촉|구인")
RESULT_RE = re.compile(r"결과|합격자")
INSTRUCTOR_BODY_RE = re.compile(r"강사\S*\s*(?:\([^)]*\)\s*)?(?:공개\s*)?(?:모집|선발|채용|공모|위촉)")
DEADLINE_LINE_RE = re.compile(r"접수|마감|기한|신청|모집\s*기간|지원|까지")
DATE_RE = re.compile(r"(?:(\d{4})\s*[.년-]\s*)?(\d{1,2})\s*[.월-]\s*(\d{1,2})\s*일?")


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def get(s, url, **kw):
    for i in range(5):
        try:
            r = s.get(url, timeout=30, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == 4:
                raise
            time.sleep(2 ** i)


def last_week_range(today):
    """today 가 속한 주의 직전 주 월~금 (date, date)."""
    mon = today - dt.timedelta(days=today.weekday() + 7)
    return mon, mon + dt.timedelta(days=4)


def fetch_list(s, start, end):
    """검색 목록에서 기간 내 글의 (제목, 게시일시, 분야, 링크) 를 모은다."""
    items, page = [], 1
    while True:
        params = {"fetchStart": page, "siteId": "", "detailChktxt": "",
                  "sDate": start.isoformat(), "eDate": end.isoformat(), "searchWord": SEARCH_WORD}
        soup = BeautifulSoup(get(s, LIST_URL, params=params).text, "html.parser")
        found = 0
        for item in soup.select("div.item"):
            a = item.find("a", href=re.compile(r"/archives/\d+"))
            subj = item.select_one("em.subject")
            date = item.select_one("em.date")
            if not (a and subj and date):
                continue
            found += 1
            realm = item.find("i", class_=re.compile(r"^p_"))
            posted = dt.datetime.strptime(date.get_text(" ", strip=True)[:19], "%Y-%m-%d %H:%M:%S")
            if not (start <= posted.date() <= end):
                continue
            items.append({
                "title": re.sub(r"^\[\d+\]\s*", "", subj.get_text(" ", strip=True)),
                "posted": posted,
                "realm": realm.get_text(strip=True).strip("[]") if realm else "기타",
                "url": a["href"] if a["href"].startswith("http") else "https:" + a["href"],
            })
        if not found or not soup.find("a", href=f"javascript:fnPagingMove({page + 1});"):
            break
        page += 1
    return items


def block_text(el):
    """블록 요소 단위로 줄바꿈한 본문 텍스트 (inline 요소는 한 줄로 유지)."""
    for br in el.find_all("br"):
        br.replace_with("\n")
    for blk in el.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "dd", "dt"]):
        blk.insert_after("\n")
    text = el.get_text("")
    return "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.split("\n") if ln.strip())


def fetch_detail(s, url):
    soup = BeautifulSoup(get(s, url).text, "html.parser")
    body = soup.select_one("#post_content") or soup.body
    hrefs = " ".join(a.get("href", "") for a in body.find_all("a"))
    text = block_text(body)
    dept = soup.select_one("dd.dept")
    info = {"dept": " ".join(sp.get_text(strip=True) for sp in dept.find_all("span")) if dept else "", "phone": ""}
    for dt_el in soup.find_all("dt"):
        if dt_el.get_text(strip=True) == "문의" and dt_el.find_next_sibling("dd"):
            info["phone"] = dt_el.find_next_sibling("dd").get_text(strip=True)
    info["emails"] = sorted(set(EMAIL_RE.findall(text + " " + hrefs.replace("mailto:", " "))))
    info["files"] = [a.get_text(strip=True) for a in body.find_all("a", href=True)
                     if re.search(r"\.(pdf|hwpx?|docx?|xlsx?|zip)(\?|$)|download|fileDown", a["href"], re.I)]
    info["text"] = text
    return info


def is_instructor_post(title, text):
    if RESULT_RE.search(title):
        return False
    if "강사" in title and RECRUIT_RE.search(title + " " + text[:500]):
        return True
    return bool(INSTRUCTOR_BODY_RE.search(text))


def parse_deadline(title, text, posted):
    """접수/마감 관련 줄(없으면 제목)에서 마지막 날짜를 마감일로 본다. 다음 줄로 넘어간 날짜도 확인."""
    lines = text.split("\n")
    cands = []
    for i, ln in enumerate(lines):
        if DEADLINE_LINE_RE.search(ln):
            cands.append(ln if DATE_RE.search(ln) else " ".join(lines[i:i + 2]))
    cands.append(title)  # 제목에 '(접수:'26.3.20.까지)' 같은 표기가 흔함
    for ln in cands:
        ln = re.sub(r"'(\d{2})\.", r"20\1.", ln)  # '26.3.20. -> 2026.3.20.
        found = [m for m in DATE_RE.findall(ln) if 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31]
        if not found:
            continue
        y, m, d = found[-1]
        year = int(y) if y else posted.year
        res = dt.date(year, int(m), int(d))
        if not y and res < posted.date() - dt.timedelta(days=31):  # 연도 생략 + 해 넘김
            res = res.replace(year=year + 1)
        t = re.search(r"\d{1,2}:\d{2}", ln)
        return res.isoformat() + (f" {t.group(0)}" if t else "")
    return ""


def parse_fields(text):
    """'모집분야' 이후 항목들(다음 '■' 항목 전까지)."""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if re.search(r"모집\s*분야", ln):
            tail = re.split(r"모집\s*분야\s*[:：]?", ln, maxsplit=1)[-1].strip()
            rest = [tail] if tail else []
            for nxt in lines[i + 1:i + 8]:
                if nxt.startswith(("■", "□", "○")) or re.match(r"^\d+\.\s", nxt):
                    break
                if not nxt.startswith("※"):
                    rest.append(nxt)
            parts = [p.strip(" -–·") for p in re.split(r"[,，、/]|\n", "\n".join(rest)) if p.strip(" -–·")]
            return [p for p in parts if not p.startswith("※")]
    return []


def parse_headcount(text):
    m = (re.search(r"(?:모집|선발)\s*인원[^\n\d]{0,10}(\d+)\s*명", text)
         or re.search(r"(\d+)\s*명\s*(?:내외|이내|정도)?\s*(?:모집|선발)", text))
    return int(m.group(1)) if m else None


def build_dataframe(s, items):
    recs = []
    for it in items:
        info = fetch_detail(s, it["url"])
        if not is_instructor_post(it["title"], info["text"]):
            continue
        recs.append({
            "게시글 타이틀": it["title"],
            "게시일": it["posted"].strftime("%Y-%m-%d"),
            "분야": it["realm"],
            "담당자 이메일": ", ".join(info["emails"]),
            "마감일": parse_deadline(it["title"], info["text"], it["posted"]),
            "공고 게시글 상세 링크": it["url"],
            "모집분야(세부)": ", ".join(parse_fields(info["text"])),
            "모집인원(명)": parse_headcount(info["text"]),
            "담당부서": info["dept"],
            "문의전화": info["phone"],
            "첨부파일": ", ".join(info["files"]),
        })
    cols = ["게시글 타이틀", "게시일", "분야", "담당자 이메일", "마감일", "공고 게시글 상세 링크",
            "모집분야(세부)", "모집인원(명)", "담당부서", "문의전화", "첨부파일"]
    return pd.DataFrame(recs, columns=cols)


def save_xlsx(df, path):
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="강사모집공고")
        ws = w.sheets["강사모집공고"]
        for col, wd in zip("ABCDEFGHIJK", [60, 12, 8, 30, 18, 50, 40, 12, 24, 16, 40]):
            ws.column_dimensions[col].width = wd
        for row in ws.iter_rows(min_row=2, min_col=6, max_col=6):
            for c in row:
                c.hyperlink = c.value


def setup_korean_font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "WenQuanYi Zen Hei"]:
        if name in names:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def field_counts(df):
    """분야별 구인 인원. 공고에 모집인원이 없으면 해당 공고를 1로 센다."""
    counts = {}
    for _, r in df.iterrows():
        n = r["모집인원(명)"]
        counts[r["분야"]] = counts.get(r["분야"], 0) + (int(n) if pd.notna(n) else 1)
    return pd.Series(counts, dtype=int).sort_values(ascending=False)


def save_chart(df, path, start, end):
    setup_korean_font()
    counts = field_counts(df)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if len(counts):
        ax = counts.plot.bar(ax=ax, color="#4C78A8", rot=0)
        ax.bar_label(ax.containers[0])
        ax.set_xlabel("분야")
        ax.set_ylabel("구인 강사 수 (인원 미기재 공고는 1건으로 집계)")
        ax.yaxis.get_major_locator().set_params(integer=True)
    else:
        ax.text(0.5, 0.5, "해당 기간 강사 구인 공고 없음", ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_axis_off()
    ax.set_title(f"분야별 강사 구인 현황 ({start:%Y.%m.%d} ~ {end:%m.%d})")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def mail_text(count, start, end):
    subject = f"[서울시 강사 구인] {start:%m/%d}~{end:%m/%d} 공고 {count}건 수집 결과"
    body = (
        "안녕하세요.\n\n"
        f"서울시 분야별 새소식에서 '{SEARCH_WORD}' 검색으로 지난주({start:%Y-%m-%d} ~ {end:%Y-%m-%d}, 월~금)에 "
        "올라온 강사 구인 공고를 수집해 공유드립니다.\n\n"
        f"- 수집된 공고 수: {count}건\n"
        "- 분야별 구인 현황 막대그래프와 상세 목록 엑셀 파일을 첨부했습니다.\n\n"
        "감사합니다.\n"
    )
    return subject, body


def build_mail(count, start, end, xlsx_path, png_path):
    subject, body = mail_text(count, start, end)
    msg = EmailMessage()
    msg["To"] = RECIPIENT
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "sender@example.com")
    msg["Subject"] = subject
    msg.set_content(body)
    html = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + '</p><img src="cid:chart">'
    msg.add_alternative(html, subtype="html")
    with open(png_path, "rb") as f:
        msg.get_payload()[1].add_related(f.read(), "image", "png", cid="<chart>")
    with open(xlsx_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=os.path.basename(xlsx_path))
    return msg


def send_mail(msg):
    host, user, pw = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    if not (host and user and pw):
        sys.exit("SMTP_HOST / SMTP_USER / SMTP_PASS 환경변수가 필요합니다.")
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        smtp.login(user, pw)
        smtp.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", help="기준일 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--start", help="기간 시작 YYYY-MM-DD (--end 와 함께, 지정 시 --today 무시)")
    ap.add_argument("--end", help="기간 끝 YYYY-MM-DD")
    ap.add_argument("--send", action="store_true", help="SMTP 로 이메일 발송")
    args = ap.parse_args()

    if args.start and args.end:
        start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    else:
        start, end = last_week_range(dt.date.fromisoformat(args.today) if args.today else dt.date.today())
    os.makedirs(OUT_DIR, exist_ok=True)
    tag = f"{start:%Y%m%d}_{end:%Y%m%d}"
    xlsx_path = os.path.join(OUT_DIR, f"seoul_instructor_posts_{tag}.xlsx")
    png_path = os.path.join(OUT_DIR, f"seoul_instructor_chart_{tag}.png")
    eml_path = os.path.join(OUT_DIR, f"mail_{tag}.eml")

    s = make_session()
    items = fetch_list(s, start, end)
    df = build_dataframe(s, items)
    print(f"기간 {start}~{end}: '{SEARCH_WORD}' 검색 {len(items)}건 중 강사 구인 공고 {len(df)}건")

    save_xlsx(df, xlsx_path)
    save_chart(df, png_path, start, end)
    msg = build_mail(len(df), start, end, xlsx_path, png_path)
    with open(eml_path, "wb") as f:
        f.write(bytes(msg))
    print("저장:", xlsx_path, png_path, eml_path, sep="\n  ")
    if args.send:
        send_mail(msg)
        print("발송 완료:", RECIPIENT)


if __name__ == "__main__":
    main()
