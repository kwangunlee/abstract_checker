"""
CP949 인코딩 정제기 (CP949 Encoding Cleaner)
──────────────────────────────────────────────
웹에서 복사한 텍스트를 CP949(EUC-KR) 환경에 저장할 때
전각 물음표(？)로 깨지는 문자를 미리 찾아 안전한 문자로 치환한다.

- 깨질 문자 자동 탐지: text.encode('cp949') 실패 여부로 판정
- 명시적 치환맵: 대시/공백/따옴표/가운뎃점 등 "의미가 있는" 문자
- 악센트 자동 처리: unicodedata NFKD 정규화로 발음기호 제거
- 정제 후 재검증
"""

import io
import unicodedata

import pandas as pd
import streamlit as st

TARGET_ENCODING = "cp949"  # = ks_c_5601-1987 / EUC-KR 계열

# ────────────────────────────────────────────────────────────
# 명시적 치환맵 — accent-stripping으로 처리하면 안 되는(의미가 다른) 문자
# key: 원본 문자, value: 치환 문자
# ────────────────────────────────────────────────────────────
EXPLICIT_MAP = {
    # ── 공백류 → 스페이스 또는 제거 ──
    "\u00A0": " ",   # nbsp
    "\u202F": " ",   # narrow nbsp
    "\u2009": " ",   # thin space
    "\u2007": " ",   # figure space
    "\u2002": " ",   # en space
    "\u2003": " ",   # em space
    "\u2008": " ",   # punctuation space
    "\u200A": " ",   # hair space
    "\u200B": "",    # zero-width space
    "\u200C": "",    # zero-width non-joiner
    "\u200D": "",    # zero-width joiner
    "\u00AD": "",    # soft hyphen
    "\uFEFF": "",    # BOM / zero-width nbsp
    # ── 하이픈·대시류 → - ──
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2013": "-",   # en dash –
    "\u2014": "-",   # em dash —
    "\u2015": "-",   # horizontal bar
    "\u2212": "-",   # minus sign −
    # ── 따옴표·구두점류 ──
    "\u2018": "'",   # '
    "\u2019": "'",   # '
    "\u201A": "'",   # ‚
    "\u201B": "'",   # ‛
    "\u201C": '"',   # "
    "\u201D": '"',   # "
    "\u201E": '"',   # „
    "\u2032": "'",   # prime ′
    "\u2033": '"',   # double prime ″
    "\u2026": "...",  # … ellipsis
    "\u2039": "<",   # ‹
    "\u203A": ">",   # ›
    "\u00AB": "<<",  # «
    "\u00BB": ">>",  # »
    # ── 가운뎃점·불릿류 ──
    "\u2022": "-",   # • bullet
    "\u2023": "-",   # ‣ triangular bullet
    "\u2043": "-",   # ⁃ hyphen bullet
    "\u00B7": ".",   # · middle dot
    "\u2027": ".",   # ‧ hyphenation point
    "\u30FB": ".",   # ・ 전각 가운뎃점 (CJK)
    "\u2219": ".",   # ∙ bullet operator
    "\u22C5": ".",   # ⋅ dot operator
    # ── 기타 자주 나오는 기호 ──
    "\u00D7": "x",   # × 곱셈
    "\u00F7": "/",   # ÷ 나눗셈
    "\u2044": "/",   # ⁄ fraction slash
    "\u2122": "(TM)",  # ™
    "\u00A9": "(C)",   # ©
    "\u00AE": "(R)",   # ®
    "\u2192": "->",  # →
    "\u2190": "<-",  # ←
}

# ── 독일어 움라우트: 이름 보존용 확장 표기(옵션) ──
GERMAN_EXPANSION = {
    "\u00FC": "ue",  # ü
    "\u00F6": "oe",  # ö
    "\u00E4": "ae",  # ä
    "\u00DF": "ss",  # ß
    "\u00DC": "Ue",  # Ü
    "\u00D6": "Oe",  # Ö
    "\u00C4": "Ae",  # Ä
}


def find_breaking_chars(text: str):
    """CP949로 인코딩 불가능한 문자를 (위치, 문자, 코드포인트)로 반환."""
    broken = []
    for i, ch in enumerate(text):
        try:
            ch.encode(TARGET_ENCODING)
        except UnicodeEncodeError:
            broken.append((i, ch, ord(ch)))
    return broken


def strip_accents(ch: str) -> str:
    """NFKD 정규화로 발음기호 제거 (à→a, é→e 등). 실패 시 원본 반환."""
    decomposed = unicodedata.normalize("NFKD", ch)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped if stripped else ch


def clean_text(text: str, expand_german: bool, unmappable_to: str):
    """
    텍스트를 정제하고 (정제본, 변경내역 리스트)를 반환.
    변경내역: (원본문자, 코드포인트, 치환결과, 방식)
    """
    changes = []
    out = []

    for ch in text:
        # CP949에 이미 있는 문자는 그대로 통과
        try:
            ch.encode(TARGET_ENCODING)
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass

        cp = ord(ch)

        # 1) 독일어 확장 (옵션, 명시맵보다 우선)
        if expand_german and ch in GERMAN_EXPANSION:
            rep = GERMAN_EXPANSION[ch]
            out.append(rep)
            changes.append((ch, cp, rep, "독일어확장"))
            continue

        # 2) 명시적 치환맵
        if ch in EXPLICIT_MAP:
            rep = EXPLICIT_MAP[ch]
            out.append(rep)
            changes.append((ch, cp, rep if rep else "(제거)", "치환맵"))
            continue

        # 3) 악센트 자동 제거
        stripped = strip_accents(ch)
        if stripped != ch and stripped.encode(TARGET_ENCODING, errors="ignore").decode(
            TARGET_ENCODING, errors="ignore"
        ) == stripped:
            # 제거 결과가 CP949 안전한 경우에만 채택
            try:
                stripped.encode(TARGET_ENCODING)
                out.append(stripped)
                changes.append((ch, cp, stripped, "악센트제거"))
                continue
            except UnicodeEncodeError:
                pass

        # 4) 그래도 안 되면 fallback
        if unmappable_to == "물음표(?)":
            rep = "?"
        elif unmappable_to == "제거":
            rep = ""
        else:  # 원본유지(경고)
            rep = ch
        out.append(rep)
        changes.append((ch, cp, rep if rep else "(제거)", "미매핑"))

    return "".join(out), changes


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
    st.header("⚙️ 옵션")
    expand_german = st.checkbox(
        "독일어 움라우트 확장 (ü→ue)",
        value=True,
        help="저자명 등 고유명사 보존에 유리. 끄면 ü→u로 단순화됩니다.",
    )
    unmappable_to = st.radio(
        "치환 불가 문자 처리",
        ["물음표(?)", "제거", "원본유지(경고)"],
        index=0,
        help="치환맵·악센트제거로도 안 되는 희귀 문자를 어떻게 할지.",
    )
    st.divider()
    st.markdown(
        "**처리 순서**\n\n"
        "1. CP949 인코딩 시도\n"
        "2. 실패 시 → 독일어확장 → 치환맵 → 악센트제거 → fallback\n"
        "3. 정제 후 재검증"
    )

tab_text, tab_excel = st.tabs(["📝 텍스트 붙여넣기", "📊 엑셀 업로드"])

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
            with st.expander(f"🔍 깨질 문자 {len(broken)}개 상세 보기", expanded=True):
                df_broken = pd.DataFrame(
                    [
                        {
                            "위치": i,
                            "문자": repr(ch)[1:-1],
                            "유니코드": f"U+{cp:04X}",
                            "이름": unicodedata.name(ch, "(이름없음)"),
                        }
                        for i, ch, cp in broken
                    ]
                )
                st.dataframe(df_broken, use_container_width=True, hide_index=True)

        cleaned, changes = clean_text(src, expand_german, unmappable_to)

        st.subheader("✅ 정제 결과")
        st.text_area("정제된 텍스트 (복사해서 사용)", cleaned, height=220)

        # 정제본 재검증
        recheck = find_breaking_chars(cleaned)
        if recheck:
            st.warning(
                f"⚠️ 정제 후에도 {len(recheck)}개 문자가 남아있어요. "
                "'치환 불가 문자 처리'를 '물음표' 또는 '제거'로 바꿔보세요."
            )
        else:
            st.success("🎉 정제본은 CP949에 100% 안전합니다. 그대로 저장하면 안 깨져요.")

        if changes:
            with st.expander(f"🔧 변경 내역 {len(changes)}건"):
                df_changes = pd.DataFrame(
                    [
                        {
                            "원본": repr(o)[1:-1],
                            "유니코드": f"U+{cp:04X}",
                            "→ 치환": r,
                            "방식": how,
                        }
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
            results = df[col].astype(str).apply(
                lambda t: clean_text(t, expand_german, unmappable_to)[0]
            )
            df[f"{col}_정제"] = results

            # 각 행별 남은 깨짐 개수도 표시
            df[f"{col}_남은깨짐"] = results.apply(
                lambda t: len(find_breaking_chars(t))
            )

            st.success("정제 완료. 아래에서 결과 확인 후 내려받으세요.")
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
