import os, warnings, logging
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")
logging.getLogger("py.warnings").setLevel(logging.ERROR)
logging.disable(logging.WARNING)

import streamlit as st
import pandas as pd
from datetime import datetime

# ===========================================================
# 상수 / 헬퍼
# ===========================================================
GRADE_ABC = ["A", "B", "C"]
ABC_TO_530 = {"A": 5, "B": 3, "C": 0}

# ✅ DQI 등급 → 보정계수 (요청표 기준)
DQI_COEF = {"A": 1.10, "B": 1.05, "C": 1.00, "D": 0.90, "E": 0.80}

# 사이드바 단계 목록(라벨, 번호)
STEPS = [
    ("① 사전준비", 1),
    ("② 사업타당성", 2),
    ("③ 평가요인 분석", 3),
    ("④ 평가모델 선택", 4),
    ("⑤ 품질-가치 보정", 5),
    ("⑥ 법률리스크 조정", 6),
    ("⑦ 가격결정·보고서", 7),
]

# ✅ 품질성(DQI) 항목별 A/B/C 기준 텍스트 (표 그대로)
DQI_CRITERIA = {
    "정확성": {
        "A": "오류율 ≤1%",
        "B": "1~5%",
        "C": ">5%",
        "weight": 20,
    },
    "완전성": {
        "A": "결측 ≤1%",
        "B": "1~5%",
        "C": ">5%",
        "weight": 20,
    },
    "일관성": {
        "A": "무모순·무중복",
        "B": "경미한 불일치",
        "C": "다수 불일치",
        "weight": 20,
    },
    "적시성": {
        "A": "최신·정기갱신",
        "B": "일부 지연",
        "C": "장기 미갱신",
        "weight": 20,
    },
    "접근성": {
        "A": "표준·API 제공",
        "B": "제한적 제공",
        "C": "비표준",
        "weight": 20,
    },
}

def wscore_from_530(score_5, weight_pct):
    """5/3/0 점수를 (등급점수/5)×가중치 로 환산 (0~100)"""
    return (float(score_5) / 5.0) * float(weight_pct)

def auto_dqi_grade(dqi: float) -> str:
    """DQI 점수 → 품질등급"""
    if dqi >= 90: return "A"
    if dqi >= 80: return "B"
    if dqi >= 70: return "C"
    if dqi >= 60: return "D"
    return "E"

def risk_category(p:int, i:int) -> str:
    r = int(p) * int(i)  # 1~9
    if r >= 7:  return "심각"
    if r >= 4:  return "주의"
    return "관심"

def fmt_money(x):
    try: return f"{float(x):,.0f}"
    except: return "0"

# ===========================================================
# 앱
# ===========================================================
def main():
    st.set_page_config(page_title="데이터 가치평가 워크플로우", layout="wide")
    try:
        st.set_option('client.showErrorDetails', False)
        st.set_option('logger.level', 'error')
    except Exception:
        pass

    # ---- 세션 초기화 ----
    if "step" not in st.session_state: st.session_state.step = 1
    if "meta" not in st.session_state:
        st.session_state.meta = {"데이터명": "", "기관/담당": "", "버전": "v0.1", "설명": ""}
    if "scores" not in st.session_state: st.session_state.scores = {}
    if "model" not in st.session_state:
        st.session_state.model = {"선택": "CVM", "매출": 0.0, "비용": 0.0, "시장가": 0.0, "WTP": 0.0}
    if "quality" not in st.session_state:
        # DQI는 Step5에서만 계산·적용
        st.session_state.quality = {"DQI점수": 0.0, "자동등급": "E", "보정계수": DQI_COEF["E"]}
    if "risk" not in st.session_state:
        st.session_state.risk = {"방식": "총점기준", "행": []}

    def go_to(step: int):
        st.session_state.step = int(step)

    # 사이드바 라디오 변경 콜백
    def _on_sidebar_nav_change():
        label_to_step = dict(STEPS)
        label = st.session_state.nav_choice
        step  = label_to_step[label]
        if step > 1 and not st.session_state.meta["데이터명"].strip():
            st.session_state.nav_choice = "① 사전준비"
            st.session_state.step = 1
            st.warning("데이터명을 입력해야 2단계 이상으로 이동할 수 있어요.")
            return
        st.session_state.step = step

    # ---- 사이드바 ----
    with st.sidebar:
        st.markdown("### 워크플로우 진행")
        st.progress((st.session_state.step - 1) / 6.0)
        st.write(f"현재 단계: {st.session_state.step} / 7")
        st.button("처음으로", use_container_width=True, on_click=go_to, args=(1,))

        st.divider()
        step_to_label = {n: t for t, n in STEPS}
        default_label = step_to_label.get(int(st.session_state.step), "① 사전준비")
        st.radio(
            "단계로 이동",
            options=[t for t, _ in STEPS],
            index=[t for t, _ in STEPS].index(default_label),
            key="nav_choice",
            on_change=_on_sidebar_nav_change,
        )

        st.divider()
        st.markdown("##### 메타요약")
        st.json(st.session_state.meta, expanded=False)
        st.markdown("##### 품질요약")
        st.json(st.session_state.quality, expanded=False)
        st.markdown("##### 점수요약")
        st.json(st.session_state.scores, expanded=False)

    st.title("데이터 가치평가 워크플로우")

    # ===========================================================
    # STEP 1. 사전준비
    # ===========================================================
    if st.session_state.step == 1:
        st.subheader("① 사전준비 — 메타데이터 입력")
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.meta["데이터명"]   = st.text_input("데이터명", st.session_state.meta["데이터명"], key="m_name")
            st.session_state.meta["기관/담당"]  = st.text_input("기관/담당", st.session_state.meta["기관/담당"], key="m_org")
            st.session_state.meta["버전"]      = st.text_input("버전",     st.session_state.meta["버전"], key="m_ver")
        with c2:
            st.session_state.meta["설명"]      = st.text_area("설명",      st.session_state.meta["설명"], height=120, key="m_desc")

        _ready = bool(st.session_state.meta["데이터명"].strip())
        st.button("다음(② 사업타당성 검토)", key="n1", on_click=go_to, args=(2,), disabled=not _ready)
        if not _ready:
            st.caption("➡️ 데이터명을 입력하면 다음 단계로 이동할 수 있어요.")

    # ===========================================================
    # STEP 2. 사업타당성
    # ===========================================================
    elif st.session_state.step == 2:
        st.subheader("② 사업타당성 검토 — 표3 반영")
        with st.expander("정성 입력"):
            colA, colB, colC = st.columns(3)
            with colA: st.text_area("활용목적 (정책·서비스·연구 등)", key="p3_목적", height=80)
            with colB: st.text_area("활용범위 (산업/지리/주체)", key="p3_범위", height=80)
            with colC: st.text_area("수요자 범위 (유형·예상 수)", key="p3_수요자", height=80)

        st.markdown("##### 정량 점수 항목")
        c1, c2, c3 = st.columns(3)
        with c1:
            s1 = st.slider("수요규모 (0~5)", 0, 5, 0, key="p3_s1")
            sc1 = (s1/5)*40
            st.caption(f"가중점수: {sc1:.1f} (가중치 40%)")
        with c2:
            s2 = st.slider("대체가능성 (0~5)", 0, 5, 0, key="p3_s2")
            sc2 = (s2/5)*30
            st.caption(f"가중점수: {sc2:.1f} (가중치 30%)")
        with c3:
            s3 = st.slider("성장성 (0~5)", 0, 5, 0, key="p3_s3")
            sc3 = (s3/5)*30
            st.caption(f"가중점수: {sc3:.1f} (가중치 30%)")

        total = sc1 + sc2 + sc3
        st.metric("사업타당성 총점(0~100)", round(total, 1))
        st.session_state.scores["사업타당성"] = float(total)

        st.button("다음(③ 평가요인 분석)", key="n2", on_click=go_to, args=(3,))
        st.button("이전", key="b2", on_click=go_to, args=(1,))

    # ===========================================================
    # STEP 3. 평가요인 분석  (권리성·시장성·사업성 모두 A/B/C)
    # ===========================================================
    elif st.session_state.step == 3:
        st.subheader("③ 평가요인 분석 — 권리성·시장성·사업성")

        # 권리성 — A/B/C (각 20%)
        st.markdown("#### 권리성 — A(5)/B(3)/C(0), 각 20%")
        right_items = [("권리 명확성",20),("제3자 권리 없음",20),("개인정보 비식별",20),("제공·이용조건 명확성",20),("소유권 증빙",20)]
        cols_r = st.columns(5)
        right_score = 0.0
        for i,(name,w) in enumerate(right_items):
            with cols_r[i]:
                g = st.selectbox(name, GRADE_ABC, key=f"r_{i}")
                right_score += wscore_from_530(ABC_TO_530[g], w)
        st.caption("산식: (등급점수/5)×가중치, 총 100점")
        st.metric("권리성 점수", round(right_score,1))
        st.session_state.scores["권리성"] = float(right_score)

        # 시장성 — A/B/C (두 항목 50%씩)
        st.markdown("#### 시장성 — A(5)/B(3)/C(0), 각 50%")
        m_items = [("시장 수요",50), ("대체 가능성",50)]
        cols_m = st.columns(2)
        market_score = 0.0
        for i,(name,w) in enumerate(m_items):
            with cols_m[i]:
                g = st.selectbox(name, GRADE_ABC, key=f"m_{i}")
                market_score += wscore_from_530(ABC_TO_530[g], w)
        st.caption("산식: (등급점수/5)×가중치, 총 100점")
        st.metric("시장성 점수", round(market_score,1))
        st.session_state.scores["시장성"] = float(market_score)

        # 사업성 — A/B/C (각 20%)
        st.markdown("#### 사업성 — A(5)/B(3)/C(0), 각 20%")
        biz_items = [("수익성",20),("비용 안정성",20),("지속가능성",20),("확장성",20),("실행가능성",20)]
        cols_b = st.columns(5)
        biz_score = 0.0
        for i,(name,w) in enumerate(biz_items):
            with cols_b[i]:
                g = st.selectbox(name, GRADE_ABC, key=f"b_{i}")
                biz_score += wscore_from_530(ABC_TO_530[g], w)
        st.caption("산식: (등급점수/5)×가중치, 총 100점")
        st.metric("사업성 점수", round(biz_score,1))
        st.session_state.scores["사업성"] = float(biz_score)

        st.button("다음(④ 평가모델 선택)", key="n3", on_click=go_to, args=(4,))
        st.button("이전", key="b3", on_click=go_to, args=(2,))

    # ===========================================================
    # STEP 4. 평가모델 선택
    # ===========================================================
    elif st.session_state.step == 4:
        st.subheader("④ 평가모델 선택")
        model = st.radio(
            "선택한 모델",
            ["수익접근법", "시장접근법", "CVM"],
            index=["수익접근법", "시장접근법", "CVM"].index(st.session_state.model["선택"])
        )
        st.session_state.model["선택"] = model

        if model == "수익접근법":
            c1, c2 = st.columns(2)
            with c1:
                st.session_state.model["매출"] = st.number_input(
                    "연 매출(예상)", min_value=0.0, value=float(st.session_state.model["매출"])
                )
            with c2:
                st.session_state.model["비용"] = st.number_input(
                    "연 비용(예상)", min_value=0.0, value=float(st.session_state.model["비용"])
                )
            base_value = max(st.session_state.model["매출"] - st.session_state.model["비용"], 0.0) * 3  # 간단 NPV 근사
            st.info(f"산정값(NPV 근사): {base_value:,.0f}")
        elif model == "시장접근법":
            st.session_state.model["시장가"] = st.number_input(
                "유사 거래가격(평균)", min_value=0.0, value=float(st.session_state.model["시장가"])
            )
            base_value = st.session_state.model["시장가"]
            st.info(f"산정값(시장가 기준): {base_value:,.0f}")
        else:  # CVM
            st.session_state.model["WTP"] = st.number_input(
                "조사 기반 WTP(평균)", min_value=0.0, value=float(st.session_state.model["WTP"])
            )
            base_value = st.session_state.model["WTP"]
            st.info(f"산정값(WTP 기준): {base_value:,.0f}")

        st.session_state.scores["기초가치"] = float(base_value)

        st.button("다음(⑤ 품질-가치 보정)", key="n4", on_click=go_to, args=(5,))
        st.button("이전", key="b4", on_click=go_to, args=(3,))

    # ===========================================================
    # STEP 5. 품질-가치 보정 (DQI 기준표로 점수 산출 → 등급 → 계수)
    # ===========================================================
    elif st.session_state.step == 5:
        st.subheader("⑤ 품질-가치 보정 — DQI 점수 산출")

        # 품질성 5항목 A/B/C 선택 (기준 텍스트 표시)
        names = list(DQI_CRITERIA.keys())
        cols_q = st.columns(5)
        q_score = 0.0
        for i, name in enumerate(names):
            crit = DQI_CRITERIA[name]
            weight = crit["weight"]
            with cols_q[i]:
                st.markdown(f"**{name}**  \n<sub>A(5): {crit['A']} · B(3): {crit['B']} · C(0): {crit['C']}</sub>", unsafe_allow_html=True)
                grade = st.selectbox("", GRADE_ABC, key=f"dqi_{i}")
                q_score += wscore_from_530(ABC_TO_530[grade], weight)

        q_score = float(round(q_score, 1))
        auto_grade = auto_dqi_grade(q_score)
        coef = DQI_COEF[auto_grade]

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("DQI 점수(0~100)", q_score)
        with c2: st.metric("품질등급", auto_grade)
        with c3: st.metric("보정계수", coef)

        st.session_state.quality.update({"DQI점수": q_score, "자동등급": auto_grade, "보정계수": coef})

        base = float(st.session_state.scores.get("기초가치", 0.0))
        adj_value = base * coef
        st.session_state.scores["품질보정가치"] = float(adj_value)
        st.info(f"보정 전: {base:,.0f} → 보정 후: {adj_value:,.0f} (계수 {coef})")

        st.button("다음(⑥ 법률리스크 조정)", key="n5", on_click=go_to, args=(6,))
        st.button("이전", key="b5", on_click=go_to, args=(4,))

    # ===========================================================
    # STEP 6. 법률리스크 조정 (권리성 + 시장성 + 사업성)
    # ===========================================================
    elif st.session_state.step == 6:
        st.subheader("⑥ 법률리스크 조정 — 리스크 매트릭스")
        st.caption("발생가능성(P): 1/2/3, 영향도(I): 1/2/3, 위험도 = P×I (계수 0.6~1.0, 총점 기준)")

        def sel_p(label, key): return st.select_slider(label, options=[1, 2, 3], value=2, key=key)
        def sel_i(label, key): return st.select_slider(label, options=[1, 2, 3], value=2, key=key)

        rdata = []

        # ① 권리성 리스크
        st.markdown("#### ① 권리성 리스크")
        right_rows = [
            ("개인정보 포함·미비식별", "가명처리·동의확보·PIA 수행"),
            ("저작권 미확인 콘텐츠 포함", "저작권자 확인·라이선스 취득"),
            ("제3자 제공 조건 불명확", "계약서 수정·이용범위 명시"),
            ("영업비밀 침해 우려", "비밀관리계획 수립"),
            ("권리 취득 경로 불명확", "증빙자료 보완·소유자 확인"),
        ]
        for idx, (risk, action) in enumerate(right_rows):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            with c1: st.write(f"**{risk}**")
            with c2: p = sel_p("P", f"rp_{idx}")
            with c3: i = sel_i("I", f"ri_{idx}")
            with c4:
                cat = risk_category(p, i)
                st.write(f"카테고리: {cat} · 대응전략: {action}")
            rdata.append({"분류": "권리성", "위험항목": risk, "P": p, "I": i, "위험도": p*i, "카테고리": cat})

        # ② 시장성 리스크
        st.markdown("#### ② 시장성 리스크")
        market_rows = [
            ("대체재 급증", "지속적 제품 차별화, 독점계약 체결"),
            ("시장 성장 둔화", "신규 산업군 발굴, 활용분야 확장"),
            ("WTP 하락", "가치 기반 가격전략 재설계"),
            ("경쟁사 가격 인하", "서비스 번들링, 부가가치 제공"),
            ("법·제도 변화로 인한 수요 감소", "법규 모니터링, 대체 시장 모색"),
        ]
        for idx, (risk, action) in enumerate(market_rows):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            with c1: st.write(f"**{risk}**")
            with c2: p = sel_p("P", f"mp_{idx}")
            with c3: i = sel_i("I", f"mi_{idx}")
            with c4:
                cat = risk_category(p, i)
                st.write(f"카테고리: {cat} · 대응전략: {action}")
            rdata.append({"분류": "시장성", "위험항목": risk, "P": p, "I": i, "위험도": p*i, "카테고리": cat})

        # ③ 사업성 리스크
        st.markdown("#### ③ 사업성 리스크")
        biz_rows = [
            ("신규 서비스 개발 지연", "개발 일정 재조정, 외부 협력 강화"),
            ("해외 진출 규제 리스크", "규제 컨설팅, 현지 파트너 확보"),
            ("데이터 결합 표준 부재", "표준화 추진, 변환도구 개발"),
            ("인프라 확장 한계", "클라우드·분산처리 도입"),
            ("네트워크 효과 미흡", "사용자 참여 촉진 프로그램"),
        ]
        for idx, (risk, action) in enumerate(biz_rows):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            with c1: st.write(f"**{risk}**")
            with c2: p = sel_p("P", f"bp_{idx}")
            with c3: i = sel_i("I", f"bi_{idx}")
            with c4:
                cat = risk_category(p, i)
                st.write(f"카테고리: {cat} · 대응전략: {action}")
            rdata.append({"분류": "사업성", "위험항목": risk, "P": p, "I": i, "위험도": p*i, "카테고리": cat})

        # 결과 요약 및 계수 산정 (총점 기준, 0.6 ~ 1.0)
        rdf = pd.DataFrame(rdata)
        st.dataframe(rdf, use_container_width=True, hide_index=True)

        N = len(rdf)
        total_risk = float(rdf["위험도"].sum()) if N > 0 else 0.0
        min_total = 1 * N      # 모든 항목이 P=1, I=1
        max_total = 9 * N      # 모든 항목이 P=3, I=3

        if N == 0 or max_total == min_total:
            severity = 0.0
        else:
            severity = (total_risk - min_total) / (max_total - min_total)
            severity = max(0.0, min(1.0, severity))  # 0~1로 클리핑

        # 리스크가 높을수록 계수 1.0 → 0.6 선형 감소
        lcoef = 1.0 - 0.4 * severity
        lcoef = float(round(max(0.6, min(1.0, lcoef)), 3))

        st.metric("리스크 계수", lcoef)
        st.caption(
            f"총점 기준(0.6~1.0): 합계 위험도={total_risk:.0f}, "
            f"최소={min_total}, 최대={max_total}, 정규화(severity)={severity:.2f}"
        )

        # 최종가치 계산 및 저장
        qv = float(st.session_state.scores.get("품질보정가치", 0.0))
        final_value = qv * lcoef
        st.session_state.scores["최종가치(리스크반영)"] = float(final_value)
        st.session_state.risk["방식"] = "총점기준"
        st.session_state.risk["행"] = rdata
        st.info(f"리스크 반영 전: {qv:,.0f} → 최종: {final_value:,.0f}")

        st.button("다음(⑦ 가격결정·보고서)", key="n6", on_click=go_to, args=(7,))
        st.button("이전", key="b6", on_click=go_to, args=(5,))

    # ===========================================================
    # STEP 7. 가격결정·보고서
    # ===========================================================
    elif st.session_state.step == 7:
        st.subheader("⑦ 가격결정·보고서 작성")
        meta = st.session_state.meta
        scores = st.session_state.scores

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("##### 메타데이터")
            st.write(pd.DataFrame([meta]))

            st.markdown("##### 섹션 요약 점수")
            st.dataframe(pd.DataFrame([
                {"항목": "사업타당성",      "점수": scores.get("사업타당성", 0.0)},
                {"항목": "권리성",          "점수": scores.get("권리성", 0.0)},
                {"항목": "시장성",          "점수": scores.get("시장성", 0.0)},
                {"항목": "사업성",          "점수": scores.get("사업성", 0.0)},
                {"항목": "DQI 점수",        "점수": st.session_state.quality.get("DQI점수", 0.0)},
                {"항목": "품질등급",        "점수": st.session_state.quality.get("자동등급", "E")},
                {"항목": "보정계수",        "점수": st.session_state.quality.get("보정계수", 1.0)},
            ]), use_container_width=True, hide_index=True)

            st.markdown("##### 산정 경로")
            st.dataframe(pd.DataFrame([
                {"단계": "기초가치",     "금액": scores.get("기초가치", 0.0)},
                {"단계": f"품질보정(계수 {st.session_state.quality['보정계수']})",
                 "금액": scores.get("품질보정가치", 0.0)},
                {"단계": "법률리스크 반영", "금액": scores.get("최종가치(리스크반영)", 0.0)},
            ]), use_container_width=True, hide_index=True)

        with c2:
            st.metric("최종 산정가치", f"{scores.get('최종가치(리스크반영)', 0.0):,.0f}")
            payload = {
                "meta": meta,
                "scores": scores,
                "quality": st.session_state.quality,
                "risk_mode": st.session_state.risk.get("방식", "총점기준"),
                "timestamp": datetime.now().isoformat()
            }
            st.download_button(
                "요약 CSV 다운로드",
                data=pd.DataFrame([payload]).to_csv(index=False).encode("utf-8-sig"),
                file_name="valuation_summary.csv",
                mime="text/csv"
            )

        st.divider()
        st.button("이전", key="b7", on_click=go_to, args=(6,))

# ---- 엔트리포인트 ----
if __name__ == "__main__":
    main()
