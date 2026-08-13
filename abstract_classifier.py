"""
연구자료 초록 다듬기 & 주제분류 (OpenAI GPT 버전)
────────────────────────────────────────────────
업로드한 규칙 파일의 4단계 처리를 GPT로 수행한다.
1) "A는 B를 분석한(모색한/살펴본/위한) 보고서를 발표하였다." 요약 문장
2) 원문 내용 보존 + 어미 음슴체 + 띄어쓰기 교정
3) 주제 최대 3개 (연구자료주제분류.xlsx 리스트 안에서만)
4) 영문이면 한글로 번역
+ TFOK 태그 (T:무역·통상 / F:금융·통화 / O:경제동향·전망 / K:한국)

초록을 입력하고 맨 아래 '주제분류 생성' 버튼을 누르면 최종 결과가 나온다.
"""

import json

import streamlit as st

# ────────────────────────────────────────────────────────────
# 주제 리스트 (연구자료주제분류.xlsx에서 추출, 29개 고유값)
# 여기 목록 안에서만 주제를 고르도록 강제한다.
# ────────────────────────────────────────────────────────────
TOPIC_LIST = [
    "경제일반", "법·제도경제", "통계", "경제동향·전망", "금융·통화",
    "국제금융(외환)", "재정·조세", "과학·기술", "정보통신", "무역·통상",
    "농림·수산", "산업", "기업", "건설", "교통", "노동", "보건",
    "복지(빈곤)", "교육", "환경", "자원", "국내지역", "세계경제일반",
    "미국·미주", "유럽", "아시아", "국제기구", "국제관계", "북한",
]

# TFOK 태그 정의 (규칙 파일)
TFOK = {
    "T": "무역·통상, 공급망, 통상정책 중심",
    "F": "금융·통화, 은행, 자본시장, 보험 중심",
    "O": "경제동향·전망, 경기흐름, 거시전망 중심",
    "K": "한국 관련 보고서·정책·사례 중심",
}

FLAGSHIP_MODEL = "gpt-5.6-sol"   # OpenAI 최상위(플래그십) 모델

# 모델 선택지 (기본 = 플래그십)
MODELS = {
    "GPT-5.6 Sol (플래그십, 기본)": "gpt-5.6-sol",
    "GPT-5.6 Terra (균형)": "gpt-5.6-terra",
    "GPT-5.6 Luna (저비용·대량)": "gpt-5.6-luna",
}


def build_system_prompt() -> str:
    topics = "\n".join(f"- {t}" for t in TOPIC_LIST)
    tfok = "\n".join(f"- {k}: {v}" for k, v in TFOK.items())
    return (
        "당신은 KDI 경제정책 연구자료의 초록을 다듬고 주제분류하는 전문가입니다.\n"
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


def process_abstract(abstract: str, model: str, api_key: str):
    """초록을 4단계 처리. (결과dict, 원본응답) 반환."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": f"[초록]\n{abstract}"},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    data = json.loads(raw)
    return data, raw


def validate_topics(topics):
    """리스트에 없는 주제는 걸러내고, 유효/무효 나눠 반환."""
    valid, invalid = [], []
    for t in topics:
        if t in TOPIC_LIST:
            valid.append(t)
        elif t in ("없음", "", None):
            continue
        else:
            invalid.append(t)
    return valid, invalid


# ────────────────────────────────────────────────────────────
# UI
# ────────────────────────────────────────────────────────────
st.set_page_config(page_title="초록 다듬기 & 주제분류", page_icon="📑", layout="wide")

st.title("📑 연구자료 초록 다듬기 & 주제분류")
st.caption(
    "초록을 넣고 맨 아래 '주제분류 생성'을 누르면, 규칙에 따라 "
    "요약 문장 · 음슴체 교정 · 주제 3개 · TFOK 태그를 생성합니다."
)

with st.sidebar:
    st.header("🔑 API 설정")
    default_key = ""
    try:
        default_key = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        pass
    api_key = st.text_input(
        "OpenAI API Key",
        value=default_key,
        type="password",
        help="배포 시 Streamlit Secrets에 OPENAI_API_KEY로 넣으면 이 칸은 비워도 됩니다.",
    )
    model_label = st.selectbox("모델", list(MODELS.keys()))
    model = MODELS[model_label]

    st.divider()
    st.markdown("**처리 규칙 (4단계)**")
    st.markdown(
        "1. `A는 B를 …한 보고서를 발표하였다` 요약\n"
        "2. 내용 보존 + 음슴체 + 띄어쓰기 교정\n"
        "3. 주제 최대 3개 (리스트 내에서만)\n"
        "4. 영문이면 한글 번역"
    )
    with st.expander(f"주제 리스트 ({len(TOPIC_LIST)}개)"):
        st.write(", ".join(TOPIC_LIST))
    with st.expander("TFOK 태그"):
        for k, v in TFOK.items():
            st.markdown(f"- **{k}**: {v}")

abstract = st.text_area(
    "초록 입력 (국문/영문 모두 가능)",
    height=260,
    placeholder="여기에 초록을 붙여넣으세요…",
)

# 최종 단계 버튼
if st.button("🏷️ 주제분류 생성", type="primary", use_container_width=True):
    if not api_key:
        st.error("OpenAI API 키가 필요해요. 사이드바에 입력하거나 Secrets에 등록하세요.")
    elif not abstract.strip():
        st.error("초록을 입력해 주세요.")
    else:
        with st.spinner(f"{model_label}로 생성 중…"):
            try:
                data, raw = process_abstract(abstract, model, api_key)

                summary = data.get("summary", "")
                refined = data.get("refined", "")
                topics = data.get("topics", [])
                tfok = data.get("tfok", [])

                valid_topics, invalid_topics = validate_topics(topics)

                # ── 최종 결과 (규칙 형식: 1 <br><br> 2 <br><br> 3) ──
                st.subheader("✅ 최종 결과")

                st.markdown("**① 요약 문장**")
                st.write(summary)

                st.markdown("**② 다듬은 초록 (음슴체·띄어쓰기 교정)**")
                st.write(refined)

                st.markdown("**③ 주제분류**")
                if valid_topics:
                    st.write(" / ".join(valid_topics))
                else:
                    st.write("없음")

                if tfok:
                    st.markdown(f"**TFOK:** {', '.join(tfok)}")

                if invalid_topics:
                    st.warning(
                        "리스트에 없는 주제가 제안돼 제외했어요: "
                        + ", ".join(invalid_topics)
                    )

                # 복사용 합본 (규칙 형식 그대로)
                st.divider()
                st.markdown("**📋 합본 (복사용)**")
                combined = (
                    f"{summary}\n\n{refined}\n\n"
                    f"주제: {' / '.join(valid_topics) if valid_topics else '없음'}"
                )
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
    "⚠️ 초록 텍스트가 OpenAI API로 전송됩니다. 공개 논문 초록은 위험이 낮지만, "
    "내부 미공개 자료라면 정보보안 정책을 먼저 확인하세요. "
    "· 주제는 연구자료주제분류.xlsx의 29개 리스트 안에서만 선택됩니다."
)
