"""
CP949 정제 핵심 로직 (공유 모듈)
──────────────────────────────────────────────
웹에서 복사한 텍스트를 CP949(EUC-KR) 환경에 저장할 때
전각 물음표(？)로 깨지는 문자를 미리 찾아 안전한 문자로 치환한다.
"""

import unicodedata

TARGET_ENCODING = "cp949"  # = ks_c_5601-1987 / EUC-KR 계열

# 명시적 치환맵 — accent-stripping으로 처리하면 안 되는(의미가 다른) 문자
EXPLICIT_MAP = {
    # ── 공백류 → 스페이스 또는 제거 ──
    "\u00A0": " ", "\u202F": " ", "\u2009": " ", "\u2007": " ",
    "\u2002": " ", "\u2003": " ", "\u2008": " ", "\u200A": " ",
    "\u200B": "", "\u200C": "", "\u200D": "", "\u00AD": "", "\uFEFF": "",
    # ── 하이픈·대시·마이너스류 → - ──
    # 주의: CP949에는 하이픈과 마이너스를 구분하는 문자가 없어서
    #       ASCII 하이픈-마이너스 '-'(U+002D) 하나로 모두 합침.
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2013": "-",   # en dash –
    "\u2014": "-",   # em dash —
    "\u2015": "-",   # horizontal bar
    "\u2212": "-",   # minus sign −  (수학 마이너스)
    "\u2E3A": "-",   # two-em dash
    "\u2E3B": "-",   # three-em dash
    "\uFF0D": "-",   # fullwidth hyphen-minus －
    "\uFE63": "-",   # small hyphen-minus ﹣
    "\uFE58": "-",   # small em dash ﹘
    "\u2043": "-",   # hyphen bullet ⁃
    # ── 따옴표·구두점류 ──
    "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'",
    "\u201C": '"', "\u201D": '"', "\u201E": '"',
    "\u2032": "'", "\u2033": '"', "\u2026": "...",
    "\u2039": "<", "\u203A": ">", "\u00AB": "<<", "\u00BB": ">>",
    # ── 불릿류 → - ──
    "\u2022": "-",   # • bullet
    "\u2023": "-",   # ‣ triangular bullet
    # ── 가운뎃점(중점)류 → . ── (전각/반각/변종 모두)
    # "\u00B7": ".",   # · middle dot (라틴)
    "\u0387": ".",   # · greek ano teleia
    "\u2027": ".",   # ‧ hyphenation point
    "\u2219": ".",   # ∙ bullet operator
    "\u22C5": ".",   # ⋅ dot operator
    "\u2E31": ".",   # word separator middle dot
    "\u30FB": "\u00B7",   # ・ 전각 → · 라틴 가운뎃점
    "\uFF65": "\u00B7",   # ･ 반각 → ·
    "\u2219": "\u00B7",   # ∙ → ·
    "\u22C5": "\u00B7",   # ⋅ → ·
    # "\u30FB": ".",   # ・ 전각 가운뎃점 (CJK katakana middle dot)
    # "\uFF65": ".",   # ･ 반각 가운뎃점 (halfwidth katakana middle dot)
    # ── 기타 자주 나오는 기호 ──
    "\u00D7": "x", "\u00F7": "/", "\u2044": "/",
    "\u2122": "(TM)", "\u00A9": "(C)", "\u00AE": "(R)",
    "\u2192": "->", "\u2190": "<-",
    # ── 통화 기호 (CP949에서 깨지는 것) ──
    "\u00A3": "GBP ",   # £ 파운드
    "\u00A2": "cents",  # ¢ 센트
    "\u00A5": "JPY ",   # ¥ 엔
}

# 독일어 움라우트: 이름 보존용 확장 표기 (항상 적용)
GERMAN_EXPANSION = {
    "\u00FC": "ue", "\u00F6": "oe", "\u00E4": "ae", "\u00DF": "ss",
    "\u00DC": "Ue", "\u00D6": "Oe", "\u00C4": "Ae",
}

CONTEXT_WINDOW = 20  # 문맥 표시 시 앞뒤로 보여줄 글자 수


def find_breaking_chars(text: str):
    """CP949로 인코딩 불가능한 문자를 (위치, 문자, 코드포인트)로 반환."""
    broken = []
    for i, ch in enumerate(text):
        try:
            ch.encode(TARGET_ENCODING)
        except UnicodeEncodeError:
            broken.append((i, ch, ord(ch)))
    return broken


def _visible(s: str) -> str:
    """문맥 안의 안 보이는 공백류를 눈에 보이게 치환."""
    return (
        s.replace("\u00A0", "·").replace("\u202F", "·")
        .replace("\u2009", "·").replace("\u200B", "∅")
    )


def context_around(text: str, i: int) -> str:
    """i번째 문자 앞뒤 문맥을 반환. 해당 문자는 【 】로 강조."""
    start = max(0, i - CONTEXT_WINDOW)
    end = min(len(text), i + CONTEXT_WINDOW + 1)
    before = _visible(text[start:i])
    ch = text[i]
    after = _visible(text[i + 1:end])
    lead = "…" if start > 0 else ""
    tail = "…" if end < len(text) else ""
    shown = ch if ch.strip() else f"U+{ord(ch):04X}"
    return f"{lead}{before}【{shown}】{after}{tail}"


def strip_accents(ch: str) -> str:
    """NFKD 정규화로 발음기호 제거 (à→a, é→e 등)."""
    decomposed = unicodedata.normalize("NFKD", ch)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped if stripped else ch


def clean_text(text: str):
    """
    (정제본, 변경내역, 미매핑목록) 반환.
    독일어 확장 항상 적용. 치환 못 한 문자는 원본 유지 + 미매핑 기록.
    """
    changes = []
    unmapped = []
    out = []

    for idx, ch in enumerate(text):
        try:
            ch.encode(TARGET_ENCODING)
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass

        cp = ord(ch)

        if ch in GERMAN_EXPANSION:
            rep = GERMAN_EXPANSION[ch]
            out.append(rep)
            changes.append((ch, cp, rep, "독일어확장"))
            continue

        if ch in EXPLICIT_MAP:
            rep = EXPLICIT_MAP[ch]
            out.append(rep)
            changes.append((ch, cp, rep if rep else "(제거)", "치환맵"))
            continue

        stripped = strip_accents(ch)
        if stripped != ch:
            try:
                stripped.encode(TARGET_ENCODING)
                out.append(stripped)
                changes.append((ch, cp, stripped, "악센트제거"))
                continue
            except UnicodeEncodeError:
                pass

        # 치환 못 함 → 원본 유지 + 미매핑 기록 (삭제·물음표 안 함)
        out.append(ch)
        unmapped.append((idx, ch, cp))

    return "".join(out), changes, unmapped


def suggest_map_snippet(unmapped):
    """미매핑 문자들을 EXPLICIT_MAP에 붙여넣을 코드 조각으로 생성."""
    seen = {}
    for _, ch, cp in unmapped:
        seen[ch] = cp
    lines = []
    for ch, cp in seen.items():
        name = unicodedata.name(ch, "이름없음")
        lines.append(f'    "\\u{cp:04X}": "",   # {ch} ({name}) ← 치환문자 입력')
    return "\n".join(lines)
