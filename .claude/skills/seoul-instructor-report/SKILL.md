---
name: seoul-instructor-report
description: 서울시(news.seoul.go.kr 분야별 새소식) '강사' 검색에서 지난주 월~금 강사 구인·모집 공고를 수집해 엑셀(xlsx)로 저장하고, pandas로 분야별 막대그래프를 그린 뒤, Gmail로 jhlee@8around.kr 에 그래프·수집 건수·인사말을 보내는 주간 리포트 스킬. 사용자가 "서울시 강사 공고", "강사 구인/모집 공고 정리", "지난주 강사 모집 엑셀", "강사 공고 리포트 메일 보내줘", "주간 강사 구인 현황" 처럼 서울시 강사 채용·모집 공고를 모으거나 정리·시각화·메일 발송하려 할 때는 명시적으로 스킬 이름을 말하지 않아도 반드시 이 스킬을 사용할 것. 기간(예를 들어 3월 둘째 주)이나 수신자를 바꿔 달라는 요청에도 사용.
---

# 서울시 강사 구인 공고 주간 리포트

서울시 분야별 새소식에서 '강사'로 검색되는 글 가운데 **강사를 구하는 공고**만 골라 정리하고 담당자에게 메일로 알려 주는 작업이다. 수집, 엑셀 저장, 그래프 작성은 `scripts/scrape_instructors.py`가 결정적으로 처리한다. 메일은 Gmail 커넥터로 보낸다.

## 데이터 소스에 대해 알아둘 것

- 사용자가 주는 URL `https://news.seoul.go.kr/?searchWord=강사…` 는 껍데기 페이지다. 실제 목록은 iframe
  `https://www.seoul.go.kr/realmnews/ex/exlist.do?fetchStart=<페이지>&sDate=YYYY-MM-DD&eDate=YYYY-MM-DD&searchWord=강사` 에서 온다.
  스크립트는 이 iframe을 직접 호출하고 `sDate/eDate`로 기간을 서버에서 걸러 받는다.
- 상세 글은 `news.seoul.go.kr/<분야>/archives/<id>` 에 있다. 본문은 `#post_content`, 담당부서와 문의 전화는 `dd.dept`와 `<dt>문의</dt>` 다음의 `dd`에 있다.
- 따라서 네트워크 허용 목록에 `news.seoul.go.kr`과 `www.seoul.go.kr`(또는 `*.seoul.go.kr`)이 둘 다 있어야 한다. 403 / `CONNECT tunnel failed`가 나면 우회하지 말고, 사용자에게 환경 설정의 Allowed domains에 추가해 달라고 안내한다.
- '강사'로 검색되는 글에는 특강 안내, 교육 신청, 선발 결과 발표처럼 구인 공고가 아닌 글도 섞여 있다. 스크립트가 아래 기준으로 거른다.
  - 제목에 '강사'와 모집류 단어(모집, 선발, 공모, 채용, 위촉, 구인)가 함께 있는 글은 포함한다.
  - 본문에 "강사 모집", "강사 선발" 같은 표현이 있는 글도 포함한다.
  - 제목에 '결과'나 '합격자'가 들어간 글은 뺀다.

## 실행 순서

### 1. 기간 정하기

기본값은 실행하는 날을 기준으로 **지난주 월~금**이다. 예를 들어 2026-10-22(목)에 실행하면 10/12~10/16이 된다. 사용자가 다른 기간을 말하면 `--start/--end`로 넘긴다.

### 2. 수집, 엑셀, 그래프

```bash
pip install -q pandas matplotlib openpyxl requests beautifulsoup4   # 없을 때만
python <skill>/scripts/scrape_instructors.py --out <작업폴더>/output                  # 지난주
python <skill>/scripts/scrape_instructors.py --start 2026-03-09 --end 2026-03-13 --out …   # 기간 지정
```

생성되는 파일(`<tag>` = `YYYYMMDD_YYYYMMDD`)은 다음과 같다.
- `seoul_instructor_posts_<tag>.xlsx`: 게시글 타이틀, 게시일, 분야, **담당자 이메일**, **마감일**, **공고 게시글 상세 링크**(하이퍼링크), 모집분야(세부), 모집인원(명), 담당부서, 문의전화, 첨부파일
- `seoul_instructor_chart_<tag>.png`: 분야(교통·안전·복지 등)별 구인 강사 수 막대그래프. 공고에 모집 인원이 적혀 있으면 그 명수를 쓰고, 없으면 공고 1건을 1로 센다. 사람 수가 안 적힌 공고가 많아 이렇게 집계한다는 점을 메일과 보고에서 숨기지 않는다.
- `summary_<tag>.json`: count, field_counts, subject, body, 파일 경로, posts 목록. 메일 작성과 결과 보고에 쓴다.
- `mail_<tag>.eml`: SMTP로 보낼 때 쓰는 완성된 메일(그래프 본문 삽입 + 엑셀 첨부)

실행한 뒤 PNG를 직접 열어 한글이 깨지지 않았는지 확인한다. 깨졌다면 한글 폰트(Malgun Gothic, NanumGothic, Noto Sans CJK KR, WenQuanYi Zen Hei 중 하나)가 없는 것이다.

**결과가 0건이어도 정상이다.** 이 게시판에는 강사 공고가 몇 주씩 없는 경우가 흔하다. 그래프에는 "해당 기간 강사 구인 공고 없음"이 표시된다. 0건이라는 사실 자체가 보고할 정보이므로 기간을 몰래 늘리지 않는다. 기간을 넓혀 볼지는 사용자에게 제안만 한다.

### 3. 메일 보내기 (Gmail 커넥터)

수신자는 `jhlee@8around.kr`이다. 사용자가 다른 주소를 말하면 그 주소로 보낸다. 메일 발송은 외부로 나가는 동작이므로, 사용자가 이번 요청에서 메일 발송을 요청했을 때만 보낸다. "수집만", "엑셀만" 같은 요청이면 보내지 않고, 보낼지 한 줄로 묻는다.

1. `mcp__Gmail__send_message`를 쓴다. 도구가 목록에 없으면 ToolSearch로 `select:mcp__Gmail__send_message`를 먼저 불러온다. 커넥터가 연결돼 있지 않으면 사용자에게 claude.ai Settings → Connectors에서 Gmail을 연결해 달라고 안내한다. 연결이 안 되면 대안으로 `--send`(SMTP 환경변수 필요)를 쓰거나, `.eml`, xlsx, png 파일을 전달한다.
2. 제목과 본문은 `summary.json`의 `subject`와 `body`를 그대로 쓴다. 본문에는 인사말, 기간, **수집 건수**, 첨부 안내가 들어 있다.
3. 첨부할 때는 이렇게 한다.
   - 그래프 PNG: `inline: true`를 주고 첨부 배열의 0번에 둔다. `htmlBody`에 `<img src="cid:0">`를 넣어 본문에 보이게 한다.
   - 엑셀: 일반 첨부로 넣는다(mimeType `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`).
   - 두 파일 모두 `base64 -w0`로 인코딩한다. 그래프가 크면 Pillow로 800×450 정도로 줄이고 색을 양자화해서 수 KB로 만든 뒤 붙인다. 원본 PNG는 150dpi라 30KB 안팎이다.
4. 발송 결과의 message id를 확인한다.

### 4. 보고

사용자에게 다음을 짧게 알린다.
- 기간
- '강사' 검색 건수 → 그중 구인 공고 건수
- 공고별 제목, 마감일, 담당자 이메일. 이메일이 없으면 문의전화를 적는다. 원문에 이메일이 없는 공고도 있으므로 비어 있다고 지어내지 않는다.
- 생성된 파일 경로
- 메일 발송 여부(message id)

## 문제 해결

- 목록이 비고 HTML만 받아진다면, 껍데기 페이지(news.seoul.go.kr/?…)를 요청했는지 확인한다. 목록은 iframe 주소에서 받아야 한다.
- 마감일이 비면 본문에 '접수/마감/기한/까지'가 들어간 줄이 없는 경우다. 제목의 `(접수:'26.3.20.까지)` 같은 표기도 스크립트가 함께 확인한다. 그래도 비면 상세 링크를 열어 확인하고, 확인한 값임을 밝혀서 보고에 적는다.
- 사이트 구조가 바뀌어 셀렉터(`div.item`, `em.subject`, `em.date`, `#post_content`)가 안 맞으면, 실제 HTML을 받아 스크립트의 셀렉터를 고친다.
