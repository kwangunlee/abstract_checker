"""
CP949 인코딩 정제기 (CP949 Encoding Cleaner)
──────────────────────────────────────────────
웹에서 복사한 텍스트를 CP949(EUC-KR) 환경에 저장할 때
전각 물음표(？)로 깨지는 문자를 미리 찾아 안전한 문자로 치환한다.
"""

import io
import unicodedata

import pandas as pd
import streamlit as st

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
    "\u00B7": ".",   # · middle dot (라틴)
    "\u0387": ".",   # · greek ano teleia
    "\u2027": ".",   # ‧ hyphenation point
    "\u2219": ".",   # ∙ bullet operator
    "\u22C5": ".",   # ⋅ dot operator
    "\u2E31": ".",   # word separator middle dot
    "\u30FB": ".",   # ・ 전각 가운뎃점 (CJK katakana middle dot)
    "\uFF65": ".",   # ･ 반각 가운뎃점 (halfwidth katakana middle dot)
    # ── 기타 자주 나오는 기호 ──
    "\u00D7": "x", "\u00F7": "/", "\u2044": "/",
    "\u2122": "(TM)", "\u00A9": "(C)", "\u00AE": "(R)",
    "\u2192": "->", "\u2190": "<-",
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


# ────────────────────────────────────────────────────────────
# UI
# ────────────────────────────────────────────────────────────
st.set_page_config(page_title="CP949 인코딩 정제기", page_icon="🧹", layout="wide")

st.title("🧹 CP949 인코딩 정제기")
st.caption(
    "웹에서 복사한 텍스트가 CP949(EUC-KR) 저장 시 전각 물음표(？)로 깨지는 걸 "
    "미리 잡아 안전한 문자로 바꿔줍니다."
)

with st.sidebar:
    st.header("ℹ️ 처리 방식")
    st.markdown(
        "**정제 순서**\n\n"
        "1. CP949 인코딩 시도 (되면 그대로 둠)\n"
        "2. 안 되면 → **독일어 확장**(ü→ue) → **치환맵**(대시·공백·따옴표 등) "
        "→ **악센트 제거**(é→e)\n"
        "3. 그래도 안 되는 문자는 **원본 유지 + 경고** "
        "(임의 삭제·물음표 치환 안 함)\n"
        "4. 정제 후 재검증"
    )
    st.divider()
    st.markdown(
        "- 독일어 움라우트 확장은 **항상 적용**돼요 (저자명 보존).\n"
        "- 치환 못 한 문자는 지우지 않고 **그대로 두고 알려드려요.**\n"
        "- 미매핑 문자가 나오면 **치환맵 추가 코드**를 만들어드려요."
    )

tab_text, tab_excel = st.tabs(["📝 텍스트 붙여넣기", "📊 엑셀 업로드"])


def render_unmapped_alert(unmapped, full_text):
    """미매핑 문자 경고 + 문맥 + 추가 코드 조각을 렌더."""
    if not unmapped:
        return
    distinct = sorted({(ch, cp) for _, ch, cp in unmapped}, key=lambda x: x[1])
    st.error(
        f"🚨 치환하지 못한 문자 {len(distinct)}종 (총 {len(unmapped)}곳)이 "
        "원본 그대로 남아 있어요. 이대로 저장하면 이 문자들은 깨집니다. "
        "무엇으로 바꿀지 정한 뒤 아래 코드로 치환맵에 추가하세요."
    )
    rows = []
    for ch, cp in distinct:
        ctx = " / ".join(
            context_around(full_text, i) for i, c, _ in unmapped if c == ch
        )
        rows.append(
            {
                "유니코드": f"U+{cp:04X}",
                "문자": ch,
                "이름": unicodedata.name(ch, "(이름없음)"),
                "출현 위치(문맥)": ctx[:250],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown("**치환맵에 추가할 코드** (`app.py`의 `EXPLICIT_MAP`에 붙여넣기):")
    st.code(suggest_map_snippet(unmapped), language="python")


# ── 텍스트 모드 ──
with tab_text:
    src = st.text_area(
        "정제할 텍스트를 붙여넣으세요",
        height=220,
        placeholder="여기에 초록/본문을 붙여넣기…",
    )

    if src:
        broken = find_breaking_chars(src)
        col1, col2 = st.columns(2)
        col1.metric("전체 글자 수", len(src))
        col2.metric("깨질 문자 수", len(broken))

        if broken:
            with st.expander(
                f"🔍 깨질 문자 {len(broken)}개 상세 (앞뒤 문맥)", expanded=True
            ):
                df_broken = pd.DataFrame(
                    [
                        {
                            "유니코드": f"U+{cp:04X}",
                            "이름": unicodedata.name(ch, "(이름없음)"),
                            "앞뒤 문맥 (【】가 문제 문자)": context_around(src, i),
                        }
                        for i, ch, cp in broken
                    ]
                )
                st.dataframe(df_broken, use_container_width=True, hide_index=True)
                st.caption(
                    "· 위치 번호 대신 앞뒤 문맥으로 표시했어요. 【】 안이 문제 문자이고, "
                    "문맥 속 안 보이는 공백은 · 또는 ∅로 표시됩니다."
                )

        cleaned, changes, unmapped = clean_text(src)

        st.subheader("✅ 정제 결과")
        st.text_area("정제된 텍스트 (복사해서 사용)", cleaned, height=220)

        render_unmapped_alert(unmapped, src)

        recheck = find_breaking_chars(cleaned)
        if not recheck:
            st.success("🎉 정제본은 CP949에 100% 안전합니다. 그대로 저장하면 안 깨져요.")
        elif not unmapped:
            st.warning(f"⚠️ 예상 못 한 잔여 깨짐 {len(recheck)}개. 확인이 필요해요.")

        if changes:
            with st.expander(f"🔧 변경 내역 {len(changes)}건"):
                df_changes = pd.DataFrame(
                    [
                        {"원본": o, "유니코드": f"U+{cp:04X}", "→ 치환": r, "방식": how}
                        for o, cp, r, how in changes
                    ]
                )
                st.dataframe(df_changes, use_container_width=True, hide_index=True)

# ── 엑셀 모드 ──
with tab_excel:
    st.markdown(
        "엑셀 파일을 올리고 **정제할 컬럼**을 고르면, 정제본 컬럼을 추가해 "
        "새 파일로 내려받을 수 있어요."
    )
    up = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"])

    if up is not None:
        df = pd.read_excel(up)
        st.write("미리보기 (상위 5행)")
        st.dataframe(df.head(), use_container_width=True)

        col = st.selectbox("정제할 컬럼 선택", df.columns)

        if st.button("정제 실행", type="primary"):
            cleaned_col, remain_col, all_unmapped = [], [], []
            for t in df[col].astype(str):
                c, _, um = clean_text(t)
                cleaned_col.append(c)
                remain_col.append(len(find_breaking_chars(c)))
                all_unmapped.extend(um)

            df[f"{col}_정제"] = cleaned_col
            df[f"{col}_남은깨짐"] = remain_col

            total_remain = sum(remain_col)
            if total_remain == 0:
                st.success("정제 완료. 모든 행이 CP949에 안전합니다.")
            else:
                st.error(
                    f"🚨 정제 후에도 {total_remain}곳이 남았어요. "
                    "아래 미매핑 문자를 치환맵에 추가한 뒤 다시 실행하세요."
                )
                distinct = sorted(
                    {(ch, cp) for _, ch, cp in all_unmapped}, key=lambda x: x[1]
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "유니코드": f"U+{cp:04X}",
                                "문자": ch,
                                "이름": unicodedata.name(ch, "(이름없음)"),
                            }
                            for ch, cp in distinct
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                st.code(suggest_map_snippet(all_unmapped), language="python")

            st.dataframe(
                df[[col, f"{col}_정제", f"{col}_남은깨짐"]].head(20),
                use_container_width=True,
            )

            out_buf = io.BytesIO()
            with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False)
            out_buf.seek(0)

            st.download_button(
                "📥 정제된 엑셀 내려받기",
                data=out_buf,
                file_name="cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

st.divider()
st.caption(
    "💡 근본 해결은 저장 대상(DB/폼)을 UTF-8(Oracle이면 AL32UTF8)로 바꾸는 것. "
    "이 도구는 CP949 환경에서 어쩔 수 없을 때 쓰는 우회책입니다."
)
