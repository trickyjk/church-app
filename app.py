import streamlit as st
import pandas as pd
import gspread
import requests
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date

# [설정]
IMGBB_API_KEY = "1bbd981a9a24f74780c2ab950a9ceeba"
SPREADSHEET_ID = "1rS7junnoO1AxUWekX1lCD9G1_KWonmXbj2KIZ1wqv_k"

st.set_page_config(page_title="킹스턴한인교회 교적부", page_icon="⛪", layout="wide")

# 데이터 연결 (온라인/로컬 공용)
@st.cache_resource
def load_data():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        # 1. 온라인(Streamlit Secrets) 먼저 시도
        if "gcp_service_account" in st.secrets:
            sa_info = dict(st.secrets["gcp_service_account"])
            # 프라이빗 키의 줄바꿈 처리
            if "private_key" in sa_info:
                sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(sa_info, scopes=scope)
        # 2. 로컬(secrets.json 파일) 시도
        else:
            creds = Credentials.from_service_account_file('secrets.json', scopes=scope)
            
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data), sheet
    except Exception as e:
        st.error(f"⚠️ 연결 실패: {e}")
        return None, None

# [스타일 및 상세 기능 - 목사님 원본 기능 100% 복구]
st.markdown("""
<style>
    div.stButton > button { width: 100%; background-color: #ffffff !important; color: #000000 !important; border: 1px solid #d0d2d6; font-weight: bold; }
    .print-card { border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px; background-color: white; display: flex; }
</style>
""", unsafe_allow_html=True)

@st.dialog("성도 상세 정보 관리", width="large")
def member_dialog(member_data, row_index, sheet, mode="edit"):
    role_options = ['성도', '서리집사', '안수집사', '협동안수집사', '은퇴안수집사', '시무권사', '협동권사', '은퇴권사', '장로', '협동장로', '은퇴장로', '협동목사', '목사']
    def get_val(col): return member_data.get(col, "") if mode == "edit" else ""

    with st.form("member_form"):
        updated_data = {}
        c1, c2, c3 = st.columns(3)
        with c1: updated_data['이름'] = st.text_input("이름", value=str(get_val('이름')))
        with c2: updated_data['직분'] = st.selectbox("직분", role_options, index=role_options.index(str(get_val('직분'))) if str(get_val('직분')) in role_options else 0)
        with c3: updated_data['전화번호'] = st.text_input("전화번호", value=str(get_val('전화번호')))
        
        updated_data['주소'] = st.text_input("주소", value=str(get_val('주소')))
        updated_data['신급'] = st.text_input("신급", value=str(get_val('신급')))
        updated_data['가족'] = st.text_area("가족 정보", value=str(get_val('가족')))
        updated_data['목양노트'] = st.text_area("목양노트 (기록용)", value=str(get_val('목양노트')), height=300)

        if st.form_submit_button("💾 서버에 저장하기", type="primary"):
            headers = sheet.row_values(1)
            row_values = [updated_data.get(h, member_data.get(h, "")) for h in headers]
            if mode == "edit":
                sheet.update(range_name=f"A{row_index+2}", values=[row_values])
            else:
                sheet.append_row(row_values)
            st.success("온라인 시트에 저장되었습니다!"); st.rerun()

# 실행
df, sheet = load_data()
if df is not None:
    st.title("⛪ 킹스턴한인교회 교적부 (온라인)")
    search = st.text_input("🔍 성도 검색")
    f_df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)] if search else df
    for idx, row in f_df.iterrows():
        cols = st.columns([1, 4, 1])
        cols[0].write(f"**{row.get('이름', '')}**")
        cols[1].write(f"{row.get('직분', '')} | {row.get('전화번호', '')} | {row.get('주소', '')}")
        if cols[2].button("✏️ 상세/수정", key=f"btn_{idx}"): member_dialog(row.to_dict(), idx, sheet, mode="edit")
        st.divider()