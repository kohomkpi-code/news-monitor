"""영업일·공휴일 판단과 자동 조회 기간.

자동 조회 기간 = '직전 영업일 오전 9시' ~ 지금.
- 평일(공휴일 아님) 화요일 → 월요일 09:00 부터
- 월요일 → 금요일 09:00 부터 (주말 포함)
- 공휴일 다음 날 → 공휴일 앞 영업일 09:00 부터 (예: 추석 연휴 뒤 첫 출근일)
- 주말·공휴일에 조회해도 → 직전 영업일 09:00 부터
공휴일 목록은 config.json 의 "holidays"([설정] 탭)에서 고친다. 임시공휴일이 생기면 한 줄 추가.
"""

import datetime as dt

KST = dt.timezone(dt.timedelta(hours=9))
START_HOUR = 9

# 관공서 공휴일(주말과 겹쳐도 적어 둠). 2026-04 규정 개정으로 노동절·제헌절 공휴일 포함.
# 출처: 행정안전부 「관공서의 공휴일에 관한 규정」 및 언론 정리 기사 — 새해 발표 때 확인·추가할 것.
DEFAULT_HOLIDAYS = [
    "2026-01-01 신정", "2026-02-16 설날 연휴", "2026-02-17 설날", "2026-02-18 설날 연휴",
    "2026-03-01 삼일절", "2026-03-02 대체공휴일(삼일절)", "2026-05-01 노동절", "2026-05-05 어린이날",
    "2026-05-24 부처님오신날", "2026-05-25 대체공휴일(부처님오신날)", "2026-06-03 전국동시지방선거",
    "2026-06-06 현충일", "2026-07-17 제헌절", "2026-08-15 광복절", "2026-08-17 대체공휴일(광복절)",
    "2026-09-24 추석 연휴", "2026-09-25 추석", "2026-09-26 추석 연휴", "2026-10-03 개천절",
    "2026-10-05 대체공휴일(개천절)", "2026-10-09 한글날", "2026-12-25 성탄절",
    "2027-01-01 신정", "2027-02-06 설날 연휴", "2027-02-07 설날", "2027-02-08 설날 연휴",
    "2027-02-09 대체공휴일(설날)", "2027-03-01 삼일절", "2027-05-01 노동절", "2027-05-03 대체공휴일(노동절)",
    "2027-05-05 어린이날", "2027-05-13 부처님오신날", "2027-06-06 현충일", "2027-07-17 제헌절",
    "2027-07-19 대체공휴일(제헌절)", "2027-08-15 광복절", "2027-08-16 대체공휴일(광복절)",
    "2027-09-14 추석 연휴", "2027-09-15 추석", "2027-09-16 추석 연휴", "2027-10-03 개천절",
    "2027-10-04 대체공휴일(개천절)", "2027-10-09 한글날", "2027-10-11 대체공휴일(한글날)",
    "2027-12-25 성탄절", "2027-12-27 대체공휴일(성탄절)",
]


def parse_holidays(lines: list[str]) -> set[dt.date]:
    """'2026-10-05 대체공휴일' 같은 줄에서 앞의 날짜만 읽는다. 형식이 틀린 줄은 건너뛴다."""
    out = set()
    for line in lines:
        head = line.strip()[:10]
        try:
            out.add(dt.date.fromisoformat(head))
        except ValueError:
            continue
    return out


def is_business_day(d: dt.date, holidays: set[dt.date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def previous_business_day(d: dt.date, holidays: set[dt.date]) -> dt.date:
    p = d - dt.timedelta(days=1)
    for _ in range(60):  # 60일 넘게 쉬는 일은 없다고 본다
        if is_business_day(p, holidays):
            return p
        p -= dt.timedelta(days=1)
    return d - dt.timedelta(days=1)


def auto_start(now: dt.datetime, holidays: set[dt.date]) -> dt.datetime:
    """자동 조회 시작 시각: 직전 영업일 09:00 (한국시간)."""
    now = now.astimezone(KST) if now.tzinfo else now.replace(tzinfo=KST)
    day = previous_business_day(now.date(), holidays)
    return dt.datetime(day.year, day.month, day.day, START_HOUR, tzinfo=KST)


def describe(start: dt.datetime) -> str:
    wd = "월화수목금토일"[start.weekday()]
    return f"{start.month}.{start.day}({wd}) {start:%H:%M}"
