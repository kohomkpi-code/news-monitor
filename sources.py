"""언론사 원문 링크의 도메인을 매체명으로 바꾼다.

표에 없는 매체는 도메인(예: example.co.kr)을 그대로 보여 준다.
자주 나오는 매체가 도메인으로 표시되면 여기에 한 줄 추가하면 된다.
"""

from urllib.parse import urlparse

DOMAIN_TO_NAME = {
    "yna.co.kr": "연합뉴스",
    "newsis.com": "뉴시스",
    "news1.kr": "뉴스1",
    "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보",
    "donga.com": "동아일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "kmib.co.kr": "국민일보",
    "seoul.co.kr": "서울신문",
    "segye.com": "세계일보",
    "munhwa.com": "문화일보",
    "hankookilbo.com": "한국일보",
    "mk.co.kr": "매일경제",
    "hankyung.com": "한국경제",
    "sedaily.com": "서울경제",
    "edaily.co.kr": "이데일리",
    "mt.co.kr": "머니투데이",
    "fnnews.com": "파이낸셜뉴스",
    "asiae.co.kr": "아시아경제",
    "heraldcorp.com": "헤럴드경제",
    "etoday.co.kr": "이투데이",
    "ajunews.com": "아주경제",
    "dt.co.kr": "디지털타임스",
    "etnews.com": "전자신문",
    "kbs.co.kr": "KBS",
    "imbc.com": "MBC",
    "sbs.co.kr": "SBS",
    "ytn.co.kr": "YTN",
    "jtbc.co.kr": "JTBC",
    "news.mtn.co.kr": "머니투데이방송",
    "newspim.com": "뉴스핌",
    "dnews.co.kr": "대한경제",
    "cnews.co.kr": "건설경제",
    "ohmynews.com": "오마이뉴스",
    "pressian.com": "프레시안",
    "nocutnews.co.kr": "노컷뉴스",
    "mediatoday.co.kr": "미디어오늘",
    "newdaily.co.kr": "뉴데일리",
    "kukinews.com": "쿠키뉴스",
    "news.kbs.co.kr": "KBS",
    "newstapa.org": "뉴스타파",
    "korea.kr": "정책브리핑",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "lh.or.kr": "LH",
    "aptn.co.kr": "아파트관리신문",
    "hapt.co.kr": "한국아파트신문",
    "electimes.com": "전기신문",
}


def source_name(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if host in DOMAIN_TO_NAME:
        return DOMAIN_TO_NAME[host]
    # news.xxx.co.kr 처럼 앞에 하위 도메인이 붙은 경우 뒷부분으로 재시도
    parts = host.split(".")
    for i in range(1, len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in DOMAIN_TO_NAME:
            return DOMAIN_TO_NAME[cand]
    return host
