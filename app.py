import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
from streamlit_cropper import st_cropper
from PIL import Image
import io
import base64
from fpdf import FPDF
import os
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# --- 1. 설정 및 데이터 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v8.3")

# --- 2. 유틸리티 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def format_phone(val):
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return ""
    nums = "".join(filter(str.isdigit, str(val)))
    if len(nums) == 10: return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    elif len(nums) == 11: return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return val

def get_sheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        return gspread.authorize(creds).open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # [데이터 표시 오류 해결] 모든 데이터를 깨끗한 문자열로 변환
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null', '[object Object]'], '')
    df['id'] = range(1, len(df) + 1)
    return df

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        if 'id' in save_df.columns: save_df = save_df.drop(columns=['id'])
        save_df = save_df.fillna("")
        sheet.clear()
        sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())

# 옵션 리스트
ROLE_OPTIONS = ["목사", "장로", "전도사", "시무권사", "협동목사", "협동장로", "협동권사", "협동안수집사", "은퇴장로", "은퇴권사", "은퇴협동권사", "집사", "청년", "성도"]
FAITH_OPTIONS = ["유아세례", "아동세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 3. 상세 수정 팝업 ---
@st.dialog("성도 정보 상세 수정")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 관리"])
    
    with tab1:
        with st.form("edit_form_v83"):
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else 13)
                u_birth = st.text_input("생년월일 (yyyy-mm-dd)", value=str(m_info['생년월일']))
            with c2:
                u_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS else 0)
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_history = st.text_area("사역 이력", value=str(m_info['사역이력']))
            st.write("---")
            st.info(f"**기존 심방기록:**\n{m_info['심방기록']}")
            new_note = st.text_area("신규 심방 내용 추가")
            
            if st.form_submit_button("💾 시트 저장 및 새로고침"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'], full_df.at[idx, '직분'] = u_name, u_role
                full_df.at[idx, '생년월일'], full_df.at[idx, '상태'] = u_birth, u_status
                full_df.at[idx, '전화번호'], full_df.at[idx, '주소'] = format_phone(u_phone), u_addr
                full_df.at[idx, '사역이력'] = u_history
                
                if new_note.strip():
                    log_entry = f"[{date.today()}] {new_note.strip()}"
                    old_log = str(m_info['심방기록'])
                    full_df.at[idx, '심방기록'] = f"{old_log}\n{log_entry}" if old_log != "" else log_entry
                
                save_to_google(full_df)
                st.success("데이터가 업데이트되었습니다."); st.rerun()

    with tab2:
        if m_info['사진']: st.image(m_info['사진'], width=150)
        img_file = st.file_uploader("새 사진", type=['jpg', 'jpeg', 'png'])
        if img_file:
            img = Image.open(img_file)
            cropped = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📸 사진 확정"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = image_to_base64(cropped)
                save_to_google(full_df)
                st.success("사진이 변경되었습니다."); st.rerun()

# --- 4. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부")
menu = st.sidebar.radio("메뉴", ["성도 관리", "신규 등록"])

if menu == "성도 관리":
    df = load_data()
    if not df.empty:
        c1, c2 = st.columns([1, 2])
        with c1: search_name = st.text_input("🔍 이름 검색")
        with c2: sel_status = st.multiselect("📍 상태 다중 필터", STATUS_OPTIONS, default=["출석 중"])
        
        f_df = df.copy()
        if search_name: f_df = f_df[f_df['이름'].str.contains(search_name)]
        if sel_status: f_df = f_df[f_df['상태'].isin(sel_status)]

        # AgGrid 설정
        display_df = f_df[["이름", "직분", "생년월일", "전화번호", "상태", "id"]]
        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("id", hide=True)
        gb.configure_column("이름", pinned='left', width=100)
        grid_opts = gb.build()

        st.caption("💡 왼쪽 체크박스를 클릭하면 수정 팝업이 뜹니다.")
        responses = AgGrid(display_df, gridOptions=grid_opts, theme='balham', height=500, update_mode=GridUpdateMode.SELECTION_CHANGED)

        # [에러 해결] 선택 행 감지 로직 보강
        selected = responses.get('selected_rows')
        if selected is not None:
            if isinstance(selected, pd.DataFrame) and not selected.empty:
                edit_member_dialog(int(selected.iloc[0]['id']), df)
            elif isinstance(selected, list) and len(selected) > 0:
                edit_member_dialog(int(selected[0]['id']), df)
    else:
        st.warning("데이터가 없습니다.")

elif menu == "신규 등록":
    st.header("📝 새 성도 등록")
    with st.form("new_entry_form"):
        col1, col2 = st.columns(2)
        with col1:
            n_name = st.text_input("성함 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=13)
            n_birth = st.text_input("생년월일 (yyyy-mm-dd)")
        with col2:
            n_phone = st.text_input("전화번호")
            n_addr = st.text_input("주소")
        
        if st.form_submit_button("➕ 등록하기"):
            if n_name:
                df_curr = load_data()
                new_row = {col: "" for col in df_curr.columns if col != 'id'}
                new_row.update({"이름": n_name, "직분": n_role, "생년월일": n_birth, "전화번호": format_phone(n_phone), "상태": "출석 중"})
                save_to_google(pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True))
                st.success("등록 완료!"); st.rerun()