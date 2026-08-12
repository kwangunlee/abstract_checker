# 🧹 CP949 인코딩 정제기

웹에서 복사한 텍스트(학술 초록 등)를 **CP949(EUC-KR)** 환경에 저장할 때
전각 물음표(`？`)로 깨지는 문자를 미리 찾아 안전한 문자로 바꿔주는 웹 도구입니다.

## 기능

- **자동 탐지**: `text.encode('cp949')` 실패 여부로 깨질 문자를 전부 찾음 (긴 치환 목록 불필요)
- **스마트 치환**: 대시/공백/따옴표/가운뎃점 등은 의미에 맞는 문자로, 악센트 문자(à, é, ü…)는 자동으로 발음기호 제거
- **재검증**: 정제 후 CP949 안전 여부를 다시 확인
- **엑셀 지원**: 컬럼 단위로 일괄 정제 후 새 파일로 내려받기

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 열림.

## GitHub + Streamlit Cloud 퍼블리시

### 1. GitHub에 올리기

```bash
git init
git add .
git commit -m "CP949 인코딩 정제기"
git branch -M main
git remote add origin https://github.com/<사용자명>/<저장소명>.git
git push -u origin main
```

또는 GitHub 웹에서 새 저장소를 만들고 `app.py`, `requirements.txt`, `README.md` 세 파일을 업로드해도 됩니다.

### 2. Streamlit Community Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) 접속 → GitHub 계정으로 로그인
2. **"New app"** 클릭
3. 항목 입력:
   - **Repository**: 방금 만든 저장소 선택
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. **"Deploy"** 클릭

몇 분 뒤 `https://<앱이름>.streamlit.app` 형태의 공개 URL이 생깁니다.
이후 GitHub에 push하면 자동으로 재배포됩니다.

> 무료 플랜이라 공개 저장소면 앱도 공개됩니다. 내부용이면 저장소를 private으로 두고
> Streamlit Cloud 설정에서 접근 권한을 관리하세요.

## 치환 규칙 커스터마이즈

`app.py`의 `EXPLICIT_MAP` 딕셔너리를 수정하면 됩니다.
새 문자가 미매핑으로 잡히면 여기에 `"\uXXXX": "치환문자",` 형태로 추가하세요.

## 참고

근본 해결은 저장 대상(DB/폼)을 **UTF-8**(Oracle이면 `AL32UTF8`)로 바꾸는 것입니다.
이 도구는 CP949 환경을 못 바꿀 때 쓰는 우회책입니다.
