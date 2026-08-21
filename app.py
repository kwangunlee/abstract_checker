"""
연구자료 초록 처리 통합 도구 (원페이지)
────────────────────────────────────────
한 화면에서 위→아래로 이어짐:
  [위]  CP949 인코딩 정제 (？ 깨짐 방지·복구)
  [아래] 다듬기 & 주제분류 (GPT, 4단계 규칙)

사이드바에서 국내/국외 연구자료를 선택하면 주제분류 프롬프트가 갈린다.
(현재는 국내·국외 프롬프트 내용이 동일 — 나중에 국내용만 따로 수정 가능)
"""

import io
import json
import unicodedata

import pandas as pd
import streamlit as st

from cp949_core import (
    clean_text,
    context_around,
    find_breaking_chars,
    suggest_map_snippet,
)

# ────────────────────────────────────────────────────────────
# 주제분류 설정 (연구자료주제분류.xlsx의 29개 고유 주제)
# ────────────────────────────────────────────────────────────
TOPIC_LIST = [
    "경제일반", "법·제도경제", "통계", "경제동향·전망", "금융·통화",
    "국제금융(외환)", "재정·조세", "과학·기술", "정보통신", "무역·통상",
    "농림·수산", "산업", "기업", "건설", "교통", "노동", "보건",
    "복지(빈곤)", "교육", "환경", "자원", "국내지역", "세계경제일반",
    "미국·미주", "유럽", "아시아", "국제기구", "국제관계", "북한",
]

TFOK = {
    "T": "무역·통상, 공급망, 통상정책 중심",
    "F": "금융·통화, 은행, 자본시장, 보험 중심",
    "O": "경제동향·전망, 경기흐름, 거시전망 중심",
    "K": "한국 관련 보고서·정책·사례 중심",
}

MODELS = {
    "GPT-5.6 Sol (플래그십, 기본)": "gpt-5.6-sol",
    "GPT-5.6 Terra (균형)": "gpt-5.6-terra",
    "GPT-5.6 Luna (저비용·대량)": "gpt-5.6-luna",
}


def _topics_and_tfok_block() -> str:
    topics = "\n".join(f"- {t}" for t in TOPIC_LIST)
    tfok = "\n".join(f"- {k}: {v}" for k, v in TFOK.items())
    return topics, tfok


def build_system_prompt_overseas() -> str:
    """국외 연구자료용 프롬프트 (기존 규칙 4단계)."""
    topics, tfok = _topics_and_tfok_block()
    return (
        "당신은 KDI 경제정책 연구자료(국외)의 초록을 다듬고 주제분류하는 전문가입니다.\n"
        "아래 4단계를 순서대로 수행하고, 마지막에 지정된 JSON으로만 출력하세요.\n\n"
        "[1단계 — 요약 문장]\n"
        '"A는 B를 분석한(모색한/살펴본/위한) 보고서를 발표하였다." 형식의 한 문장을 완성합니다.\n'
        "- A는 고정값으로 굳이 생성하지 않아도 됩니다. 'A' 그대로 표시 가능.\n"
        "- B의 성격에 따라 '분석한/모색한/살펴본/위한' 등 맥락에 맞는 서술어를 고릅니다.\n"
        "- B는 초록의 핵심을 아주 짧게 담습니다.\n\n"
        "[2단계 — 원문 다듬기]\n"
        "초록에 오타가 있어도 절대 내용을 바꾸지 말고, 오직 (1) 어미를 음슴체(-음/-ㅁ)로 바꾸고, "
        "(2) 띄어쓰기만 교정합니다.\n\n"
        "[3단계 — 주제 분류]\n"
        "초록을 바탕으로 주제를 최대 3개까지 지정합니다. 관련 주제가 없으면 '없음' 또는 1개만도 가능.\n"
        "반드시 아래 주제 리스트 안에서만 고르세요. 리스트에 없는 주제를 만들지 마세요.\n"
        f"[주제 리스트]\n{topics}\n\n"
        "[TFOK 태그]\n"
        "아래 기준에 해당하면 태그를 표기합니다. 여러 개 동시 해당 시 함께 표기(예: T, O, K). "
        "해당 없으면 빈 배열.\n"
        f"{tfok}\n\n"
        "[4단계 — 번역]\n"
        "초록이 영문이면 1·2단계 결과를 한글로 작성(번역)합니다. 이미 한글이면 그대로.\n\n"
        "[출력 형식] — 아래 JSON만, 다른 텍스트·마크다운 없이:\n"
        "{\n"
        '  "summary": "1단계 결과 문장",\n'
        '  "refined": "2단계 결과 (음슴체+띄어쓰기 교정, 필요 시 한글 번역)",\n'
        '  "topics": ["주제1", "주제2", "주제3"],\n'
        '  "tfok": ["T", "O"]\n'
        "}"
    )


def build_system_prompt_domestic() -> str:
    """
    국내 연구자료용 프롬프트.
    ※ 현재는 국외와 내용 동일. 나중에 이 함수만 국내 규칙에 맞게 수정하면 된다.
    """
    topics, tfok = _topics_and_tfok_block()
    return (
        "당신은 KDI 경제정책 연구자료(국내)의 초록을 다듬고 주제분류하는 전문가입니다.\n"
        "아래 4단계를 순서대로 수행하고, 마지막에 지정된 JSON으로만 출력하세요.\n\n"
        "[1단계 — 요약 문장]\n"
        '"A는 B를 분석한(모색한/살펴본/위한) 보고서를 발표하였다." 형식의 한 문장을 완성합니다.\n'
        "- A는 고정값으로 굳이 생성하지 않아도 됩니다. 'A' 그대로 표시 가능.\n"
        "- B의 성격에 따라 '분석한/모색한/살펴본/위한' 등 맥락에 맞는 서술어를 고릅니다.\n"
        "- B는 초록의 핵심을 아주 짧게 담습니다.\n\n"
        "[2단계 — 원문 다듬기]\n"
        "초록에 오타가 있어도 절대 내용을 바꾸지 말고, 오직 (1) 어미를 음슴체(-음/-ㅁ)로 바꾸고, "
        "(2) 띄어쓰기만 교정합니다.\n\n"
        "[3단계 — 주제 분류]\n"
        "초록을 바탕으로 주제를 최대 3개까지 지정합니다. 관련 주제가 없으면 '없음' 또는 1개만도 가능.\n"
        "반드시 아래 주제 리스트 안에서만 고르세요. 리스트에 없는 주제를 만들지 마세요.\n"
        f"[주제 리스트]\n{topics}\n\n"
        "[TFOK 태그]\n"
        "아래 기준에 해당하면 태그를 표기합니다. 여러 개 동시 해당 시 함께 표기(예: T, O, K). "
        "해당 없으면 빈 배열.\n"
        f"{tfok}\n\n"
        "[4단계 — 번역]\n"
        "초록이 영문이면 1·2단계 결과를 한글로 작성(번역)합니다. 이미 한글이면 그대로.\n\n"
        "[출력 형식] — 아래 JSON만, 다른 텍스트·마크다운 없이:\n"
        "{\n"
        '  "summary": "1단계 결과 문장",\n'
        '  "refined": "2단계 결과 (음슴체+띄어쓰기 교정, 필요 시 한글 번역)",\n'
        '  "topics": ["주제1", "주제2", "주제3"],\n'
        '  "tfok": ["T", "O"]\n'
        "}"
    )


# 자료 구분 → 프롬프트 함수 매핑 (나중에 국내용만 바꾸면 됨)
PROMPT_BUILDERS = {
    "국외 연구자료": build_system_prompt_overseas,
    "국내 연구자료": build_system_prompt_domestic,
}


def process_abstract(abstract: str, model: str, api_key: str, system_prompt: str):
    """초록을 4단계 처리. (결과dict, 원본응답) 반환."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"[초록]\n{abstract}"},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw), raw


def validate_topics(topics):
    valid, invalid = [], []
    for t in topics:
        if t in TOPIC_LIST:
            valid.append(t)
        elif t in ("없음", "", None):
            continue
        else:
            invalid.append(t)
    return valid, invalid


def get_openai_key():
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        return ""


# ────────────────────────────────────────────────────────────
# 페이지 설정 + 세션 상태
# ────────────────────────────────────────────────────────────
st.set_page_config(page_title="연구자료 초록 처리 도구", page_icon="📑", layout="wide")

# 정제본을 분류 입력으로 넘기는 세션 저장소
if "abstract_for_classify" not in st.session_state:
    st.session_state.abstract_for_classify = ""

# ── 사이드바: 국내/국외 선택 + API 설정 ──
with st.sidebar:
    st.title("📑 초록 처리 도구")
    source_type = st.radio(
        "연구자료 구분",
        list(PROMPT_BUILDERS.keys()),
        help="정제는 동일. 주제분류 프롬프트가 구분에 따라 달라집니다 "
        "(현재는 내용 동일, 추후 국내용 별도 조정 가능).",
    )
    st.divider()

    st.markdown("**🔑 API 설정**")
    default_key = get_openai_key()
    api_key_input = st.text_input(
        "OpenAI API Key",
        value="",
        type="password",
        help="배포 시 Secrets에 OPENAI_API_KEY를 넣으면 이 칸은 비워도 됩니다.",
    )
    api_key = api_key_input or default_key
    model_label = st.selectbox("모델", list(MODELS.keys()))
    model = MODELS[model_label]

    st.divider()
    with st.expander(f"주제 리스트 ({len(TOPIC_LIST)}개)"):
        st.write(", ".join(TOPIC_LIST))
    with st.expander("TFOK 태그"):
        for k, v in TFOK.items():
            st.markdown(f"- **{k}**: {v}")

    # ── 자주 쓰는 특수문자 팔레트 (모두 CP949 안전) ──
    st.divider()
    st.markdown("**⌨️ 특수문자 (CP949 안전)**")
    st.caption("칸을 클릭하면 전체 선택 → Ctrl+C로 복사하세요.")
    CHAR_GROUPS = {
        "괄호·따옴표": "「」『』‘’“”",
        "기호·구두점": "· ： … ※ ＞ >",
        "도형": "▲ △ □ ■ ○ ● ◎ ◇ ◆ ★ ☆",
        "번호(원숫자)": "①②③④⑤⑥⑦⑧⑨⑩⑪ Ⅰ",
        "체크·전화": "√ ☎",
        "화살표": "↔ → ↑ ← ↓",
    }
    for label, chars in CHAR_GROUPS.items():
        st.text_input(label, value=chars, key=f"palette_{label}")
    st.caption(
        "※ 유니코드 체크(✓)는 CP949에서 깨져서 루트기호 √로 대체했어요."
    )

st.title(f"📑 초록 처리 — {source_type}")

# ════════════════════════════════════════════════════════════
# 1단계 — CP949 인코딩 정제 (위)
# ════════════════════════════════════════════════════════════
st.header("1️⃣ 인코딩 정제")
st.caption(
    "웹에서 복사한 초록이 CP949 저장 시 전각 물음표(？)로 깨지는 걸 "
    "미리 잡아 안전한 문자로 바꿉니다."
)

tab_text, tab_excel = st.tabs(["📝 텍스트", "📊 엑셀 일괄"])

with tab_text:
    src = st.text_area(
        "정제할 초록",
        height=200,
        placeholder="여기에 초록을 붙여넣기…",
    )

    if src:
        broken = find_breaking_chars(src)
        c1, c2 = st.columns(2)
        c1.metric("전체 글자 수", len(src))
        c2.metric("깨질 문자 수", len(broken))

        if broken:
            with st.expander(f"🔍 깨질 문자 {len(broken)}개 (앞뒤 문맥)", expanded=True):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "유니코드": f"U+{cp:04X}",
                                "이름": unicodedata.name(ch, "(이름없음)"),
                                "문맥 (【】=문제 문자)": context_around(src, i),
                            }
                            for i, ch, cp in broken
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

        cleaned, changes, unmapped = clean_text(src)

        st.subheader("✅ 정제 결과")
        st.text_area("정제된 초록", cleaned, height=200)

        if unmapped:
            distinct = sorted({(ch, cp) for _, ch, cp in unmapped}, key=lambda x: x[1])
            st.error(
                f"🚨 치환 못 한 문자 {len(distinct)}종이 남아 있어요. "
                "무엇으로 바꿀지 정한 뒤 아래 코드로 cp949_core.py의 EXPLICIT_MAP에 추가하세요."
            )
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "유니코드": f"U+{cp:04X}",
                            "문자": ch,
                            "이름": unicodedata.name(ch, "(이름없음)"),
                            "문맥": " / ".join(
                                context_around(src, i)
                                for i, c, _ in unmapped if c == ch
                            )[:200],
                        }
                        for ch, cp in distinct
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.code(suggest_map_snippet(unmapped), language="python")

        recheck = find_breaking_chars(cleaned)
        if not recheck:
            st.success("🎉 정제본은 CP949에 100% 안전합니다.")

        # ── 흐름 연결: 정제본을 아래 분류 입력으로 ──
        if st.button("⬇️ 이 정제본으로 아래에서 주제분류 하기", type="primary"):
            st.session_state.abstract_for_classify = cleaned
            st.toast("정제본을 아래 분류 입력에 넣었어요.")

        if changes:
            with st.expander(f"🔧 변경 내역 {len(changes)}건"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"원본": o, "유니코드": f"U+{cp:04X}", "→ 치환": r, "방식": how}
                            for o, cp, r, how in changes
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

with tab_excel:
    st.markdown("엑셀 파일을 올리고 컬럼을 고르면 정제본 컬럼을 추가해 내려받아요.")
    up = st.file_uploader("엑셀 (.xlsx)", type=["xlsx"])
    if up is not None:
        df = pd.read_excel(up)
        st.dataframe(df.head(), use_container_width=True)
        col = st.selectbox("정제할 컬럼", df.columns)
        if st.button("정제 실행", type="primary"):
            cleaned_col, remain_col = [], []
            for t in df[col].astype(str):
                c, _, _ = clean_text(t)
                cleaned_col.append(c)
                remain_col.append(len(find_breaking_chars(c)))
            df[f"{col}_정제"] = cleaned_col
            df[f"{col}_남은깨짐"] = remain_col
            total = sum(remain_col)
            if total == 0:
                st.success("정제 완료. 모든 행이 CP949에 안전합니다.")
            else:
                st.warning(f"정제 후에도 {total}곳이 남았어요 (희귀 문자).")
            st.dataframe(
                df[[col, f"{col}_정제", f"{col}_남은깨짐"]].head(20),
                use_container_width=True,
            )
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df.to_excel(w, index=False)
            buf.seek(0)
            st.download_button(
                "📥 정제된 엑셀 내려받기",
                data=buf,
                file_name="cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# ════════════════════════════════════════════════════════════
# 2단계 — 다듬기 & 주제분류 (아래, 같은 페이지)
# ════════════════════════════════════════════════════════════
st.divider()
st.header("2️⃣ 다듬기 & 주제분류")
st.caption(
    f"[{source_type}] 기준으로 요약 문장 · 음슴체 교정 · 주제 3개 · TFOK 태그를 생성합니다 "
    "(주제는 29개 리스트 내에서만)."
)

abstract = st.text_area(
    "분류할 초록 (위에서 정제본을 넘기면 자동으로 채워집니다)",
    height=220,
    value=st.session_state.abstract_for_classify,
    placeholder="초록을 붙여넣거나, 위 정제 결과의 '⬇️ 주제분류 하기' 버튼으로 채우세요.",
)

if st.button("🏷️ 주제분류 생성", type="primary", use_container_width=True):
    if not api_key:
        st.error("OpenAI API 키가 필요해요. 사이드바에 입력하거나 Secrets에 등록하세요.")
    elif not abstract.strip():
        st.error("초록을 입력해 주세요.")
    else:
        system_prompt = PROMPT_BUILDERS[source_type]()   # 국내/국외에 맞는 프롬프트
        with st.spinner(f"{model_label} · {source_type}로 생성 중…"):
            try:
                data, raw = process_abstract(abstract, model, api_key, system_prompt)
                summary = data.get("summary", "")
                refined = data.get("refined", "")
                valid_topics, invalid_topics = validate_topics(data.get("topics", []))
                tfok = data.get("tfok", [])

                st.subheader("✅ 최종 결과")
                st.markdown("**① 요약 문장**")
                st.write(summary)
                st.markdown("**② 다듬은 초록 (음슴체·띄어쓰기 교정)**")
                st.write(refined)
                st.markdown("**③ 주제분류**")
                st.write(" / ".join(valid_topics) if valid_topics else "없음")
                if tfok:
                    st.markdown(f"**TFOK:** {', '.join(tfok)}")
                if invalid_topics:
                    st.warning("리스트에 없어 제외: " + ", ".join(invalid_topics))

                st.divider()
                st.markdown("**📋 합본 (복사용)**")
                combined = f"{summary}\n\n{refined}\n\n"
                combined += f"주제: {' / '.join(valid_topics) if valid_topics else '없음'}"
                if tfok:
                    combined += f"\nTFOK: {', '.join(tfok)}"
                st.text_area("합본", combined, height=200)

                with st.expander("🔧 원본 응답 (디버그)"):
                    st.code(raw, language="json")
            except ImportError:
                st.error(
                    "openai 라이브러리가 없어요. requirements.txt에 'openai'를 추가하고 "
                    "재배포하세요. (로컬은 pip install openai)"
                )
            except json.JSONDecodeError:
                st.error("응답을 JSON으로 파싱하지 못했어요. 다시 시도하거나 모델을 바꿔보세요.")
            except Exception as e:
                st.error(f"생성 중 오류: {e}")

st.divider()
st.caption(
    "⚠️ 초록이 OpenAI API로 전송됩니다. 내부 미공개 자료면 정보보안 정책을 먼저 확인하세요. "
    "· 공개 배포 시 API 키 과금 위험이 있으니 접근 제한을 권장합니다."
)
