import os, warnings, logging
# ---- Squelch everything (console warnings/logs) ----
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")              # Python warnings 전부 숨김
logging.getLogger("py.warnings").setLevel(logging.ERROR)
logging.disable(logging.WARNING)               # 모든 WARNING 이하 로그 전면 비활성화

import streamlit as st
import pandas as pd
from datetime import datetime

# ===========================================================
# 데이터 가치평가 워크플로우 (7단계 마법사)
# - 표3~표10 반영
# - ScriptRunContext 경고 방지: 모든 st.* 호출을 main() 내부로 이동
# ===========================================================

# ---------------------------
# 전역 매핑/계수표 & 순수 유틸 (st.* 미사용)
# ---------------------------
GRADE_530 = ["5","3","0"]
GRADE_530_LABEL = {"5":"높음/우위/대형/있음", "3":"중간/유사/중형/일부", "0":"낮음/열위/소형/없음"}
GRADE_ABC = ["A","B","C"]
ABC_TO_530 = {"A":5, "B":3, "C":0}
DQI_COEF = {"A":1.10, "B":1.05, "C":1.00, "D":0.90, "E":0.80}
DQI_TO_GRADE = [(90,"A"),(80,"B"),(70,"C"),(60,"D"),(0,"E")]
RISK_COEF = {"관심":1.00, "주의":0.90, "심각":0.80}

# ---- 순수 파이썬 유틸 ----
def wscore_from_530(grade_530:int, weight_percent:float)->float:
    return (grade_530/5.0) * weight_percent

def wscore_from_slider(slide:int, weight_percent:float)->float:
    return (slide/5.0) * weight_percent

def auto_dqi_grade(total:float)->str:
    for thr,g in DQI_TO_GRADE:
        if total >= thr: return g
    return "E"

def risk_category(p:int, i:int)->str:
    s = p*i
    return "심각" if s>=7 else ("주의" if s>=4 else "관심")

# ===========================================================
# main() 안에서만 Streamlit API 사용
# ===========================================================

def main():
    st.set_page_config(page_title="데이터 가치평가 워크플로우", layout="wide")
    # UI 쪽 경고/에러 표시는 최소화 (핵폭탄 옵션)
    try:
        st.set_option('client.showErrorDetails', False)  # 트레이스백 숨김
        st.set_option('logger.level', 'error')           # Streamlit 내부 로그 레벨
    except Exception:
        pass

    # ---- 세션 초기화 ----
    if "step" not in st.session_state: st.session_state.step = 1
    if "meta" not in st.session_state:
        st.session_state.meta = {"데이터명":"","기관/담당":"","버전":"v0.1","설명":""}
    if "scores" not in st.session_state: st.session_state.scores = {}
    if "model" not in st.session_state:
        st.session_state.model = {"선택":"CVM","매출":0.0,"비용":0.0,"시장가":0.0,"WTP":0.0}
    if "quality" not in st.session_state:
        st.session_state.quality = {"DQI점수":0.0,"자동등급":"E","보정계수":DQI_COEF["E"]}
    if "risk" not in st.session_state: st.session_state.risk = {"방식":"최대 위험","행":[]}
    # ---- 세션 초기화 ----
    if "step" not in st.session_state: st.session_state.step = 1
    if "meta" not in st.session_state:
        st.session_state.meta = {"데이터명":"","기관/담당":"","버전":"v0.1","설명":""}
    if "scores" not in st.session_state: st.session_state.scores = {}
    if "model" not in st.session_state:
        st.session_state.model = {"선택":"CVM","매출":0.0,"비용":0.0,"시장가":0.0,"WTP":0.0}
    if "quality" not in st.session_state:
        st.session_state.quality = {"DQI점수":0.0,"자동등급":"E","보정계수":DQI_COEF["E"]}
    if "risk" not in st.session_state: st.session_state.risk = {"방식":"최대 위험","행":[]}

    def go_to(step:int):
        st.session_state.step = step

    # ---- 사이드바 ----
    with st.sidebar:
        st.header("워크플로우")
        steps = ["① 사전준비","② 사업타당성 검토","③ 평가요인 분석","④ 평가모델 선택","⑤ 품질-가치 보정","⑥ 법률리스크 조정","⑦ 가격결정·보고서"]
        st.write(" → ".join([s if i+1<=st.session_state.step else s for i,s in enumerate(steps)]))
        jump = st.selectbox("단계로 이동", options=list(range(1,8)), index=st.session_state.step-1, key="jump")
        if jump != st.session_state.step:
            go_to(jump)

    st.title("데이터 가치평가 프로세스")

# ===========================================================
# STEP 1. 사전준비
# ===========================================================
    if st.session_state.step == 1:
        st.subheader("① 사전준비 — 메타데이터 입력")
        c1,c2 = st.columns(2)
        with c1:
            st.session_state.meta["데이터명"] = st.text_input("데이터명", st.session_state.meta["데이터명"], key="m_name")
            st.session_state.meta["기관/담당"] = st.text_input("기관/담당", st.session_state.meta["기관/담당"], key="m_org")
            st.session_state.meta["버전"] = st.text_input("버전", st.session_state.meta["버전"], key="m_ver")
        with c2:
            st.session_state.meta["설명"] = st.text_area("설명", st.session_state.meta["설명"], height=120, key="m_desc")

        if st.button("다음(② 사업타당성 검토)", key="n1"):
            if st.session_state.meta["데이터명"].strip():
                go_to(2)
            else:
                st.warning("데이터명을 입력해 주세요.")

    # ===========================================================
    # STEP 2. 사업타당성 (표3)
    # ===========================================================
    elif st.session_state.step == 2:
        st.subheader("② 사업타당성 검토 — 표3 반영")
        with st.expander("정성 입력(점수 없음)"):
            colA,colB,colC = st.columns(3)
            with colA: st.text_area("활용목적 (정책·서비스·연구 등)", key="p3_목적", height=80)
            with colB: st.text_area("활용범위 (산업/지리/주체)", key="p3_범위", height=80)
            with colC: st.text_area("수요자 범위 (유형·예상 수)", key="p3_수요자", height=80)

        st.markdown("##### 정량 점수 항목")
        c1,c2,c3 = st.columns(3)
        with c1:
            s1 = st.slider("수요규모 (0~5)", 0, 5, 0, key="p3_s1")
            sc1 = wscore_from_slider(s1, 40)
            st.caption(f"가중점수: {sc1:.1f} (가중치 40%)")
        with c2:
            s2 = st.slider("대체가능성 (0~5)", 0, 5, 0, key="p3_s2")
            sc2 = wscore_from_slider(s2, 30)
            st.caption(f"가중점수: {sc2:.1f} (가중치 30%)")
        with c3:
            s3 = st.slider("성장성 (0~5)", 0, 5, 0, key="p3_s3")
            sc3 = wscore_from_slider(s3, 30)
            st.caption(f"가중점수: {sc3:.1f} (가중치 30%)")
        total = sc1+sc2+sc3
        st.metric("사업타당성 총점(0~100)", round(total,1))
        st.session_state.scores["사업타당성"] = float(total)

        st.button("다음(③ 평가요인 분석)", key="n2", on_click=go_to, args=(3,))
        st.button("이전", key="b2", on_click=go_to, args=(1,))

    # ===========================================================
    # STEP 3. 평가요인 분석 (표4~7)
    # ===========================================================
    elif st.session_state.step == 3:
        st.subheader("③ 평가요인 분석 — 품질성·권리성·시장성·사업성")
        # 품질성(표4)
        st.markdown("#### 품질성 (표4) — A(5)/B(3)/C(0), 각 20%")
        p4_items = [("정확성",20),("완전성",20),("일관성",20),("적시성",20),("접근성",20)]
        cols = st.columns(5)
        p4_score = 0.0
        for i,(name,w) in enumerate(p4_items):
            with cols[i]:
                g = st.selectbox(name, GRADE_ABC, key=f"p4_{i}")
                p4_score += wscore_from_530(ABC_TO_530[g], w)
        st.caption("산식: (등급점수/5)×가중치, 총 100점")
        st.metric("품질성(DQI) 점수", round(p4_score,1))
        st.session_state.quality["DQI점수"] = float(p4_score)

        # 권리성(표5)
        st.markdown("#### 권리성 (표5)")
        p5_rows = [
            ("소유권","생성·가공 주체 명확성",20),
            ("이용권","권리 취득 경로의 합법성",15),
            ("이용권","이용 목적·범위의 명확성",15),
            ("이용권","제3자 제공 가능 여부",10),
            ("법적 하자 가능성","지식재산권 침해 위험",15),
            ("법적 하자 가능성","개인정보·민감정보 포함 여부",15),
            ("법적 하자 가능성","영업비밀·부정경쟁 가능성",10),
        ]
        cols5 = st.columns(3)
        p5_data = []
        for i,(area,item,w) in enumerate(p5_rows):
            with cols5[i%3]:
                g = st.selectbox(f"{area} - {item}", GRADE_ABC, key=f"p5_{i}")
                p5_data.append({"평가영역":area,"세부항목":item,"가중치":w,"등급":g,"가중점수":wscore_from_530(ABC_TO_530[g],w)})
        p5_df = pd.DataFrame(p5_data)
        st.dataframe(p5_df, use_container_width=True, hide_index=True)
        p5_total = float(p5_df["가중점수"].sum()) if len(p5_df)>0 else 0.0
        st.metric("권리성 총점", round(p5_total,1))
        st.session_state.scores["권리성"] = p5_total

        # 시장성(표6)
        st.markdown("#### 시장성 (표6)")
        p6_rows = [
            ("대체가능성","경쟁 데이터 존재 여부",20),
            ("대체가능성","대체재 품질·가격 비교",20),
            ("대체가능성","전환비용",10),
            ("수요규모","시장 규모(현재)",20),
            ("수요규모","시장 성장률(3~5년)",15),
            ("수요규모","평균 WTP",15),
        ]
        def pick_530(label,key):
            return int(st.selectbox(label, GRADE_530, format_func=lambda x:f"{x} ({GRADE_530_LABEL[x]})", key=key))
        cols6 = st.columns(3)
        p6_data = []
        for i,(area,item,w) in enumerate(p6_rows):
            with cols6[i%3]:
                g530 = pick_530(f"{area} - {item}", f"p6_{i}")
                p6_data.append({"평가영역":area,"세부항목":item,"가중치":w,"등급(5/3/0)":g530,"가중점수":wscore_from_530(g530,w)})
        p6_df = pd.DataFrame(p6_data)
        st.dataframe(p6_df, use_container_width=True, hide_index=True)
        p6_total = float(p6_df["가중점수"].sum()) if len(p6_df)>0 else 0.0
        st.metric("시장성 총점", round(p6_total,1))
        st.session_state.scores["시장성"] = p6_total

        # 사업성(표7)
        st.markdown("#### 사업성 (표7)")
        p7_rows = [
            ("활용잠재력","다분야 적용 가능성",20),
            ("활용잠재력","결합·재가공 용이성",15),
            ("활용잠재력","정책·산업 수요 부합성",15),
            ("확장성","시장 확장 가능성",20),
            ("확장성","서비스·제품 확장성",15),
            ("확장성","기술 인프라 대응력",15),
        ]
        cols7 = st.columns(3)
        p7_data = []
        for i,(area,item,w) in enumerate(p7_rows):
            with cols7[i%3]:
                g530 = pick_530(f"{area} - {item}", f"p7_{i}")
                p7_data.append({"평가영역":area,"세부항목":item,"가중치":w,"등급(5/3/0)":g530,"가중점수":wscore_from_530(g530,w)})
        p7_df = pd.DataFrame(p7_data)
        st.dataframe(p7_df, use_container_width=True, hide_index=True)
        p7_total = float(p7_df["가중점수"].sum()) if len(p7_df)>0 else 0.0
        st.metric("사업성 총점", round(p7_total,1))
        st.session_state.scores["사업성"] = p7_total

        st.session_state.scores["DQI"] = float(p4_score)

        st.button("다음(④ 평가모델 선택)", key="n3", on_click=go_to, args=(4,))
        st.button("이전", key="b3", on_click=go_to, args=(2,))

    # ===========================================================
    # STEP 4. 평가모델 선택
    # ===========================================================
    elif st.session_state.step == 4:
        st.subheader("④ 평가모델 선택")
        model = st.radio("선택한 모델", ["수익접근법","시장접근법","CVM"], index=["수익접근법","시장접근법","CVM"].index(st.session_state.model["선택"]))
        st.session_state.model["선택"] = model

        if model == "수익접근법":
            c1,c2 = st.columns(2)
            with c1: st.session_state.model["매출"] = st.number_input("연 매출(예상)", min_value=0.0, value=float(st.session_state.model["매출"]))
            with c2: st.session_state.model["비용"] = st.number_input("연 비용(예상)", min_value=0.0, value=float(st.session_state.model["비용"]))
            base_value = max(st.session_state.model["매출"]-st.session_state.model["비용"],0.0)*3
            st.info(f"예시 산정값(NPV 근사): {base_value:,.0f}")
        elif model == "시장접근법":
            st.session_state.model["시장가"] = st.number_input("유사 거래가격(평균)", min_value=0.0, value=float(st.session_state.model["시장가"]))
            base_value = st.session_state.model["시장가"]
            st.info(f"예시 산정값(시장가 기준): {base_value:,.0f}")
        else:
            st.session_state.model["WTP"] = st.number_input("조사 기반 WTP(평균)", min_value=0.0, value=float(st.session_state.model["WTP"]))
            base_value = st.session_state.model["WTP"]
            st.info(f"예시 산정값(WTP 기준): {base_value:,.0f}")

        st.session_state.scores["기초가치"] = float(base_value)

        st.button("다음(⑤ 품질-가치 보정)", key="n4", on_click=go_to, args=(5,))
        st.button("이전", key="b4", on_click=go_to, args=(3,))

    # ===========================================================
    # STEP 5. 품질-가치 보정
    # ===========================================================
    elif st.session_state.step == 5:
        st.subheader("⑤ 품질-가치 보정 — DQI 등급→보정계수")
        dqi = float(st.session_state.scores.get("DQI", st.session_state.quality["DQI점수"]))
        auto_grade = auto_dqi_grade(dqi); coef = DQI_COEF[auto_grade]
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("DQI 점수(0~100)", round(dqi,1))
        with c2: st.metric("자동 등급(표8)", auto_grade)
        with c3: st.metric("보정계수", coef)
        st.session_state.quality.update({"DQI점수":dqi,"자동등급":auto_grade,"보정계수":coef})
        base = st.session_state.scores.get("기초가치",0.0)
        adj_value = base * coef
        st.session_state.scores["품질보정가치"] = float(adj_value)
        st.info(f"보정 전: {base:,.0f} → 보정 후: {adj_value:,.0f}")
        st.button("다음(⑥ 법률리스크 조정)", key="n5", on_click=go_to, args=(6,))
        st.button("이전", key="b5", on_click=go_to, args=(4,))

    # ===========================================================
    # STEP 6. 법률리스크 조정 (표10)
    # ===========================================================
    elif st.session_state.step == 6:
        st.subheader("⑥ 법률리스크 조정 — 리스크 매트릭스")
        st.caption("발생가능성(P): 낮음1/중간2/높음3, 영향도(I): 낮음1/중간2/높음3, 위험도=P×I")
        risk_rows = [
            ("개인정보 포함·미비식별", "가명처리·동의확보·PIA 수행"),
            ("저작권 미확인 콘텐츠 포함", "저작권자 확인·라이선스 취득"),
            ("제3자 제공 조건 불명확", "계약서 수정·이용범위 명시"),
            ("영업비밀 침해 우려", "비밀관리계획 수립"),
            ("권리 취득 경로 불명확", "증빙자료 보완·소유자 확인"),
        ]
        def sel_p(label,key): return st.select_slider(label, options=[1,2,3], value=2, key=key)
        def sel_i(label,key): return st.select_slider(label, options=[1,2,3], value=2, key=key)
        rdata = []
        for idx,(risk,action) in enumerate(risk_rows):
            c1,c2,c3,c4 = st.columns([2,1,1,2])
            with c1: st.write(f"**{risk}**")
            with c2: p = sel_p("P", f"rp_{idx}")
            with c3: i = sel_i("I", f"ri_{idx}")
            with c4:
                cat = risk_category(p,i)
                st.write(f"카테고리: {cat} — 대응전략: {action}")
            rdata.append({"위험항목":risk,"P":p,"I":i,"위험도":p*i,"카테고리":cat})
        rdf = pd.DataFrame(rdata)
        st.dataframe(rdf, use_container_width=True, hide_index=True)
        mode = st.radio("계수 적용 방식", ["최대 위험","평균 위험"], index=0, key="riskmode")
        if mode == "최대 위험":
            order = {"관심":0,"주의":1,"심각":2}
            max_cat = rdf["카테고리"].iloc[rdf["카테고리"].map(order).fillna(0).idxmax()] if len(rdf)>0 else "관심"
            lcoef = RISK_COEF[max_cat]; desc = max_cat
        else:
            avg = rdf["위험도"].mean() if len(rdf)>0 else 0
            desc = "심각" if avg>=7 else ("주의" if avg>=4 else "관심")
            lcoef = RISK_COEF[desc]
        st.metric("리스크 계수", lcoef); st.caption(f"적용 기준: {mode} ({desc})")
        qv = st.session_state.scores.get("품질보정가치",0.0)
        final_value = qv * lcoef
        st.session_state.scores["최종가치(리스크반영)"] = float(final_value)
        st.info(f"리스크 반영 전: {qv:,.0f} → 최종: {final_value:,.0f}")
        st.button("다음(⑦ 가격결정·보고서)", key="n6", on_click=go_to, args=(7,))
        st.button("이전", key="b6", on_click=go_to, args=(5,))

    # ===========================================================
    # STEP 7. 가격결정·보고서
    # ===========================================================
    elif st.session_state.step == 7:
        st.subheader("⑦ 가격결정·보고서 작성")
        meta = st.session_state.meta; scores = st.session_state.scores
        c1,c2 = st.columns([2,1])
        with c1:
            st.markdown("##### 메타데이터"); st.write(pd.DataFrame([meta]))
            st.markdown("##### 섹션 요약 점수")
            st.dataframe(pd.DataFrame([
                {"항목":"사업타당성","점수":scores.get("사업타당성",0.0)},
                {"항목":"품질성(DQI)","점수":scores.get("DQI",0.0)},
                {"항목":"권리성","점수":scores.get("권리성",0.0)},
                {"항목":"시장성","점수":scores.get("시장성",0.0)},
                {"항목":"사업성","점수":scores.get("사업성",0.0)},
            ]), use_container_width=True, hide_index=True)
            st.markdown("##### 산정 경로")
            st.dataframe(pd.DataFrame([
                {"단계":"기초가치","금액":scores.get("기초가치",0.0)},
                {"단계":f"품질보정({st.session_state.quality['자동등급']}, 계수 {st.session_state.quality['보정계수']})","금액":scores.get("품질보정가치",0.0)},
                {"단계":"법률리스크 반영","금액":scores.get("최종가치(리스크반영)",0.0)},
            ]), use_container_width=True, hide_index=True)
        with c2:
            st.metric("최종 산정가치", f"{scores.get('최종가치(리스크반영)',0.0):,.0f}")
            payload = {"meta":meta,"scores":scores,"quality":st.session_state.quality,"risk_mode":st.session_state.risk.get("방식","최대 위험"),"timestamp":datetime.now().isoformat()}
            st.download_button("요약 CSV 다운로드", data=pd.DataFrame([payload]).to_csv(index=False).encode("utf-8-sig"), file_name="valuation_summary.csv", mime="text/csv")
        st.divider()
        st.button("이전", key="b7", on_click=go_to, args=(6,))

# ---- 스크립트 엔트리 ----
if __name__ == "__main__":
    # Streamlit는 자체 런처가 스크립트를 __main__으로 실행하므로 main() 내부에서만 st.*를 사용
    main()
