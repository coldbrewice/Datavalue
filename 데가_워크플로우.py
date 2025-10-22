import os, warnings, logging
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import streamlit as st
import pandas as pd

# ===============================================
# 기본 설정
# ===============================================
st.set_page_config(page_title="데이터 가치평가 대시보드", layout="wide")
st.markdown("<h1 style='text-align:center; color:#0078D7;'>📊 데이터 가치평가 대시보드</h1>", unsafe_allow_html=True)
st.caption("기본가치(V₀)에 보정요인(DQI·α·β·γ)과 법률리스크(Δ, 0.8~1.1)를 적용하여 최종가치를 산정합니다.")
st.divider()

# ===============================================
# 공통 상수/함수
# ===============================================
GRADE_ABC = ["", "A", "B", "C"]  # 공란 선택 가능(미입력시 1.0)
ABC_TO_530 = {"A": 5, "B": 3, "C": 0}
COEF_BY_GRADE = {"A": 1.10, "B": 1.05, "C": 1.00, "D": 0.90, "E": 0.80}  # 0.8~1.1

def fmt_money(x):
    try: return f"{float(x):,.0f}"
    except: return "0"

def wscore_from_530(score_5, weight_pct): return (float(score_5)/5.0)*float(weight_pct)

def auto_grade(score):
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "E"

# ===============================================
# 표 원문 반영 — 항목/가중치/평가기준(요약)
# ===============================================
# DQI(품질성) 5항목 (각 20%)
DQI_CRITERIA = {
    "정확성": {"A":"오류율 ≤1%", "B":"1~5%", "C":">5%", "weight":20},
    "완전성": {"A":"결측 ≤1%", "B":"1~5%", "C":">5%", "weight":20},
    "일관성": {"A":"무모순·무중복", "B":"경미한 불일치", "C":"다수 불일치", "weight":20},
    "적시성": {"A":"최신·정기 갱신", "B":"일부 지연", "C":"장기 미갱신", "weight":20},
    "접근성": {"A":"표준·API 제공", "B":"부분·제한 제공", "C":"비표준", "weight":20},
}

# α(권리성) — 이미지 표 그대로 7항목/가중치
ALPHA_TABLE = [
    ("생성·가공 주체 명확성",        "생성·가공 주체 및 증빙 여부",         20),
    ("권리 취득 경로의 합법성",      "직접생성·적법한 양수·위탁개발 여부",   15),
    ("이용 목적·범위 명확성",        "계약·약관에 이용 목적·범위 명시 여부", 15),
    ("제3자 제공 가능 여부",         "제3자 제공·재판매 조건 명확성",       10),
    ("지식재산권 침해 위험",         "특허·저작권·상표 무단 포함 여부",     15),
    ("개인정보·민감정보 포함 여부",  "비식별·가명처리·동의절차 이행 여부",   15),
    ("영업비밀·부정경쟁 가능성",      "부정경쟁방지법 위반 가능성",          10),
]

# β(시장성) — 이미지 표 그대로 6항목/가중치
BETA_TABLE = [
    ("대체재 존재 여부",       "없음·일부·다수",         20),
    ("대체재 품질·가격 비교",  "우위·유사·열위",         20),
    ("전환비용",              "높음·중간·낮음",         10),
    ("시장 규모",            "대형·중형·소형",         20),
    ("시장 성장률",          "고성장·보통·정체",       15),
    ("평균 WTP",            "높음·중간·낮음",         15),
]

# γ(사업성) — 이미지 표 그대로 6항목/가중치
GAMMA_TABLE = [
    ("다분야 적용 가능성",      "3개 이상 / 1~2개 / 제한적", 20),
    ("결합·재가공 용이성",      "표준포맷·부분지원·비표준",   15),
    ("정책·산업 수요 부합성",   "고부합·보통·낮음",          15),
    ("시장 확장 가능성",        "국내+해외 / 제한 / 불가",    20),
    ("서비스·제품 확장성",      "2개 이상 / 1개 / 없음",     15),
    ("기술 인프라 대응력",      "고도화·보통·미비",          15),
]

# Δ(법률리스크) — 이미지 표 그대로(권리/시장/사업 각각 5개)
RISK_SETS = {
    "권리성 리스크": [
        ("개인정보 포함·미비식별", "가명처리·동의확보·PIA 수행"),
        ("저작권 미확인 콘텐츠 포함", "저작권자 확인·라이선스 취득"),
        ("제3자 제공 조건 불명확", "계약서 수정·이용범위 명시"),
        ("영업비밀 침해 우려", "비밀관리계획 수립"),
        ("권리 취득 경로 불명확", "증빙자료 보완·소유자 확인"),
    ],
    "시장성 리스크": [
        ("대체재 급증", "지속적 제품 차별화·독점계약 체결"),
        ("시장 성장 둔화", "신규 산업군 발굴·활용분야 확장"),
        ("WTP 하락", "가치 기반 가격전략 재설계"),
        ("경쟁사 가격 인하", "서비스 번들링·부가가치 제공"),
        ("법·제도 변화로 인한 수요 감소", "법규 모니터링·대체 시장 모색"),
    ],
    "사업성 리스크": [
        ("신규 서비스 개발 지연", "개발 일정 재조정·외부 협력 강화"),
        ("해외 진출 규제 리스크", "규제 컨설팅·현지 파트너 확보"),
        ("데이터 결합 표준 부재", "표준화 추진·변환도구 개발"),
        ("인프라 확장 한계", "클라우드·분산처리 도입"),
        ("네트워크 효과 미흡", "사용자 참여 촉진 프로그램"),
    ],
}

# ===============================================
# 세션 상태
# ===============================================
if "step" not in st.session_state: st.session_state.step = 0
if "scores" not in st.session_state:
    st.session_state.scores = {"V0":0,"DQI":1.0,"ALPHA":1.0,"BETA":1.0,"GAMMA":1.0,"DELTA":1.0}

def go_to(step:int): st.session_state.step = step

# ===============================================
# 좌측 패널 (라디오 내비)
# ===============================================
STEPS = [
    "📘 설명서", "① 기본가치(V₀)", "② 품질성(DQI)",
    "③ 권리·시장·사업성(αβγ)", "④ 법률리스크(Δ)", "⑤ 결과요약"
]
with st.sidebar:
    st.markdown("### ⚙️ 단계 이동")
    st.progress(st.session_state.step / (len(STEPS)-1))
    sel = st.radio("단계 선택", options=STEPS, index=st.session_state.step)
    go_to(STEPS.index(sel))

# ===============================================
# 0️⃣ 설명서
# ===============================================
if st.session_state.step == 0:
    st.subheader("📘 평가 설명서")
    st.markdown("""
    1) **기본가치(V₀)**: 수익·시장·CVM 접근 중 선택  
    2) **품질성(DQI)**: 정확성/완전성/일관성/적시성/접근성 (각 20%)  
    3) **α·β·γ**: 권리성(7항목), 시장성(6항목), 사업성(6항목) — **표의 가중치 그대로**  
       - 각 항목은 A/B/C 중 택1 (5/3/0점) → 가중합(0~100) → 등급(A~E) → **계수(0.8~1.1)**  
       - **미입력 시 계수=1.0**  
    4) **Δ(법률리스크)**: 권리/시장/사업 5항목씩, P×I 합계로 **0.8~1.1** 산식 적용  
    5) **결과요약**: V_adj = V₀ × DQI × α × β × γ × Δ
    """)
    st.button("다음 ▶", on_click=go_to, args=(1,), key="next_0")

# ===============================================
# 1️⃣ 기본가치
# ===============================================
elif st.session_state.step == 1:
    st.subheader("① 기본가치(V₀)")
    model = st.radio("평가모델 선택", ["수익접근법", "시장접근법", "CVM"], index=1)
    if model == "수익접근법":
        rev  = st.number_input("예상 연 매출", min_value=0.0, key="rev")
        cost = st.number_input("예상 연 비용", min_value=0.0, key="cost")
        v0 = max(rev - cost, 0.0) * 3
    elif model == "시장접근법":
        v0 = st.number_input("유사 거래가격(평균)", min_value=0.0, key="mkt_price")
    else:
        v0 = st.number_input("지불의사(WTP 평균)", min_value=0.0, key="wtp")
    st.session_state.scores["V0"] = v0
    st.metric("기초가치(V₀)", fmt_money(v0))
    st.button("다음 ▶", on_click=go_to, args=(2,), key="next_1")

# ===============================================
# 2️⃣ 품질성(DQI)
# ===============================================
elif st.session_state.step == 2:
    st.subheader("② 품질성(DQI)")
    q_score = 0.0
    cols = st.columns(5)
    for i,(name,crit) in enumerate(DQI_CRITERIA.items()):
        with cols[i%5]:
            st.markdown(
                f"**{name}**<br><span style='font-size:12px;'>A(5): {crit['A']}<br>B(3): {crit['B']}<br>C(0): {crit['C']}</span>",
                unsafe_allow_html=True)
            sel = st.selectbox("등급", GRADE_ABC, key=f"dqi_{i}")
            if sel != "": q_score += wscore_from_530(ABC_TO_530[sel], crit["weight"])
            st.caption(f"가중치 {crit['weight']}%")
    grade = auto_grade(q_score)
    coef = COEF_BY_GRADE[grade] if q_score>0 else 1.0
    st.metric("DQI 점수", round(q_score,1))
    st.caption(f"등급 {grade if q_score>0 else '미입력'} → 계수 {coef}")
    st.session_state.scores["DQI"] = coef
    c1,c2 = st.columns(2)
    with c1: st.button("◀ 이전", on_click=go_to, args=(1,), key="back_2")
    with c2: st.button("다음 ▶", on_click=go_to, args=(3,), key="next_2")

# ===============================================
# 3️⃣ α·β·γ 통합 (표 그대로)
# ===============================================
elif st.session_state.step == 3:
    st.subheader("③ 권리성·시장성·사업성(αβγ) 통합 평가")

    def render_factor_block(title, table, key_prefix):
        st.markdown(f"#### {title}")
        score = 0.0
        cols = st.columns(3)
        for idx,(name,rule,weight) in enumerate(table):
            with cols[idx % 3]:
                st.markdown(f"**{name}**<br><span style='font-size:12px;'>{rule}</span>", unsafe_allow_html=True)
                sel = st.selectbox("등급", GRADE_ABC, key=f"{key_prefix}_{idx}")
                if sel != "": score += wscore_from_530(ABC_TO_530[sel], weight)
                st.caption(f"가중치 {weight}%")
        grade = auto_grade(score)
        coef  = COEF_BY_GRADE[grade] if score>0 else 1.0
        st.metric(f"{title} 점수", round(score,1))
        st.caption(f"등급 {grade if score>0 else '미입력'} → 계수 {coef}")
        st.session_state.scores[key_prefix] = coef
        st.divider()

    render_factor_block("α 권리성", ALPHA_TABLE, "ALPHA")
    render_factor_block("β 시장성", BETA_TABLE,  "BETA")
    render_factor_block("γ 사업성", GAMMA_TABLE, "GAMMA")

    c1,c2 = st.columns(2)
    with c1: st.button("◀ 이전", on_click=go_to, args=(2,), key="back_3")
    with c2: st.button("다음 ▶", on_click=go_to, args=(4,), key="next_3")

# ===============================================
# 4️⃣ Δ(법률리스크) — 0.8~1.1
# ===============================================
elif st.session_state.step == 4:
    st.subheader("④ 법률리스크(Δ) — 위험도(P×I) 기반(0.8~1.1)")

    risk_rows = []
    for category, rows in RISK_SETS.items():
        st.markdown(f"#### {category}")
        for j,(risk,action) in enumerate(rows):
            c1,c2,c3,c4 = st.columns([2,1,1,2])
            with c1: st.write(risk)
            with c2: p = st.select_slider("P", [1,2,3], value=1, key=f"p_{category}_{j}")
            with c3: i = st.select_slider("I", [1,2,3], value=1, key=f"i_{category}_{j}")
            with c4: st.caption(action)
            risk_rows.append({"분류":category, "위험도":p*i})
    rdf = pd.DataFrame(risk_rows)
    total = rdf["위험도"].sum(); N = len(rdf)
    # 최소합(N)~최대합(9N)을 [0,1]로 정규화 → 1.1~0.8 선형 맵핑
    severity = 0.0 if N==0 else max(0.0, min(1.0, (total - N) / (9*N - N)))
    delta = round(1.1 - 0.3 * severity, 3)   # 1.1(최저위험) → 0.8(최고위험)
    st.metric("리스크 계수 Δ", delta)
    st.session_state.scores["DELTA"] = delta

    c1,c2 = st.columns(2)
    with c1: st.button("◀ 이전", on_click=go_to, args=(3,), key="back_4")
    with c2: st.button("다음 ▶", on_click=go_to, args=(5,), key="next_4")

# ===============================================
# 5️⃣ 결과요약 (다운로드 미리보기)
# ===============================================
elif st.session_state.step == 5:
    st.subheader("⑤ 결과요약 — 다운로드 미리보기")
    s = st.session_state.scores
    V0 = s["V0"]; M = s["DQI"] * s["ALPHA"] * s["BETA"] * s["GAMMA"]; Δ = s["DELTA"]
    V_adj = V0 * M * Δ
    df = pd.DataFrame([
        {"요인":"V₀(기초가치)","값":V0},
        {"요인":"DQI(품질성)","값":s["DQI"]},
        {"요인":"α(권리성)","값":s["ALPHA"]},
        {"요인":"β(시장성)","값":s["BETA"]},
        {"요인":"γ(사업성)","값":s["GAMMA"]},
        {"요인":"Δ(법률리스크)","값":Δ},
        {"요인":"최종가치(V_adj)","값":V_adj},
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.metric("최종 산정가치(V_adj)", fmt_money(V_adj))
    st.caption(f"V_adj = V₀ × DQI × α × β × γ × Δ = {fmt_money(V0)} × {M:.3f} × {Δ:.3f}")
    st.download_button("📥 결과 CSV 다운로드",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="data_value_summary.csv", mime="text/csv", key="download_csv")
    st.button("◀ 이전", on_click=go_to, args=(4,), key="back_5")
