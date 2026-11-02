"""숫자를 한글 읽기로 바꾼다 — 한국어 TTS 전처리(설정 「숫자를 한글로」).

WanAvatar `services/ko_numbers.py`(2026-09-24)에서 옮겼다 — import 하지 않고 복사한다(이 프로젝트는 독립).
엔진들이 아라비아 숫자를 뭉갠 실측("12로" → "슛비로", "3~4개" → "상상계")이 이 모듈의 이유다.

읽는 법:
  한자어(기본)   3도 → 삼도 · 1722년 → 천칠백이십이년
  고유어(단위)   4마디 → 네 마디 · 8개 → 여덟 개 · 5번째 → 다섯 번째   (1~99 만)
  범위           3~4개 → 서너 개 · 1600~1722년 → 천육백에서 천칠백이십이년
  비율·분수      5:4 → 오 대 사 · 9/8 → 팔분의 구
  소수·퍼센트    0.74 → 영점칠사 · 70% → 칠십퍼센트
"""
from __future__ import annotations

import re

_SINO = "영일이삼사오육칠팔구"
_SMALL = ["", "십", "백", "천"]
_BIG = ["", "만", "억", "조"]

# 관형형(단위 앞) / 독립형(범위의 앞 숫자처럼 뒤에 단위가 안 올 때)
_NATIVE_ONES = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_ONES_ALONE = ["", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]

# 고유어로 세는 단위. 긴 것을 앞에 둬야 "번째" 가 "번" 보다 먼저 잡힌다.
_NATIVE = ("번째", "시간", "군데", "가지", "사람", "마디", "마리",
           "개", "곡", "명", "살", "줄", "잔", "병", "장", "달", "해", "시")
# 붙어 있는 두 수를 한 낱말로 읽는 범위
_NATIVE_PAIR = {(1, 2): "한두", (2, 3): "두세", (3, 4): "서너", (4, 5): "너덧",
                (5, 6): "대여섯", (6, 7): "예닐곱", (7, 8): "일고여덟"}

_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_TOKEN = re.compile(
    r"(?<![A-Za-z0-9.])"                                   # 코드 이름(Bm7)·소수 안쪽은 제외
    r"(?:(?P<a>" + _NUM + r")\s?[~\-–]\s?(?P<b>" + _NUM + r")"   # 범위
    r"|(?P<r1>\d+):(?P<r2>\d+)"                            # 비율
    r"|(?P<f1>\d+)/(?P<f2>\d+)"                            # 분수
    r"|(?P<n>" + _NUM + r"))"
    r"(?P<pct>%)?"
    r"(?P<sp> ?)(?P<after>[가-힣]*)"                          # 뒤따르는 한글(단위·조사)
)


def sino(n: int) -> str:
    """한자어 읽기. 1722 → 천칠백이십이, 10000 → 만, 12000 → 만이천."""
    if n == 0:
        return "영"
    parts = []
    big = 0
    while n > 0:
        chunk = n % 10000
        if chunk:
            s = "" if (chunk == 1 and big > 0) else _sino_chunk(chunk)
            parts.append(s + _BIG[big])
        n //= 10000
        big += 1
    return "".join(reversed(parts))


def _sino_chunk(n: int) -> str:
    out = ""
    for i, unit in enumerate(_SMALL):
        d = n % 10
        n //= 10
        if d == 0:
            continue
        digit = "" if (d == 1 and i > 0) else _SINO[d]   # 십·백·천 앞의 '일' 은 뺀다
        out = digit + unit + out
    return out


def native(n: int, before_unit: bool = True) -> str:
    """고유어 읽기(1~99). 단위 앞이면 관형형(한·두·세·네·스무)."""
    if not 1 <= n <= 99:
        return sino(n)
    if n == 20:
        return "스무" if before_unit else "스물"
    t, o = divmod(n, 10)
    ones = _NATIVE_ONES if before_unit else _NATIVE_ONES_ALONE
    return _NATIVE_TENS[t] + ones[o]


def _read(num: str) -> str:
    """정수·소수 한 개를 한자어로."""
    num = num.replace(",", "")
    if "." in num:
        whole, frac = num.split(".", 1)
        return sino(int(whole)) + "점" + "".join(_SINO[int(c)] for c in frac)
    return sino(int(num))


def _native_unit(after: str) -> str | None:
    for u in _NATIVE:
        if after.startswith(u):
            return u
    return None


def _sub(m: re.Match) -> str:
    after = m.group("after")
    sp = m.group("sp")
    pct = "퍼센트" if m.group("pct") else ""
    unit = None if pct else _native_unit(after)
    rest = after[len(unit):] if unit else after

    if m.group("r1") is not None:
        body = f"{sino(int(m.group('r1')))} 대 {sino(int(m.group('r2')))}"
        return body + sp + after

    if m.group("f1") is not None:
        f1, f2 = int(m.group("f1")), int(m.group("f2"))
        body = f"{sino(f2)}분의 {sino(f1)}" if f1 < 100 and f2 < 100 else f"{sino(f1)}, {sino(f2)}"
        return body + sp + after

    if m.group("a") is not None:
        a, b = m.group("a"), m.group("b")
        if unit and "." not in a + b:
            ia, ib = int(a), int(b)
            pair = _NATIVE_PAIR.get((ia, ib))
            if pair:
                return f"{pair} {unit}{rest}"
            if ia <= 99 and ib <= 99:
                return f"{native(ia, False)}에서 {native(ib)} {unit}{rest}"
        return f"{_read(a)}에서 {_read(b)}{pct}{sp}{after}"

    n = m.group("n")
    if unit and "." not in n:
        v = int(n.replace(",", ""))
        # 99 를 넘으면 한자어로 세되, 고유어 단위 앞이라 띄운다(백 개 · 천 명)
        return f"{native(v) if v <= 99 else sino(v)} {unit}{rest}"
    return _read(n) + pct + sp + after


def read_numbers(text: str) -> str:
    """본문의 숫자 표현을 전부 한글로. 숫자가 없으면 그대로."""
    return _TOKEN.sub(_sub, text)


_LATIN_KO = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                     ["에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠", "엔", "오", "피", "큐",
                      "아르", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"]))


def latin_letters_ko(text: str) -> str:
    """받아쓰기 비교용 — 로마자를 한글 글자 이름으로(「LLM」→「엘엘엠」). ASR 이 약어를 로마자로 적어 일치율이 낮게 나오는 것을 줄인다."""
    return "".join(_LATIN_KO.get(c.upper(), c) if c.isascii() and c.isalpha() else c for c in text)
