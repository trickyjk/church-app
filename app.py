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

# --- 1. 기본 설정 및 보안 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v8.2", page_icon="⛪")

# --- 2. 유틸리티 함수 (사진, 전화번호, 구글연결) ---
def image_to_base64(img):
    """이미지를 텍스트(base64)로 변환하여 시트 저장용으로 만듦"""
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def format_phone(val):
    """전화번호 형식을 010-0000-0000 형태로 통일"""
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return ""
    nums = "".join(filter(str.isdigit, str(val)))
    if len(nums) == 10: return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    elif len(nums) == 11: return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return val

def get_sheet():
    """구글 시트 연결"""
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        return gspread.authorize(creds).open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"구글 연결 실패: {e}")
        return None

def load_data():
    """시트 데이터 불러오기 및 생년월일 보호 처리"""
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # [데이터 보호 핵심] 모든 데이터를 문자열로 변환하여 '0'이 지워지거나 날짜가 깨지는 것 방지
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null'], '')
    # AgGrid 선택을 위한 고유 ID 강제 부여
    df['id'] = [i for i in range(1, len(df) + 1)]
    return df

def save_to_google(df):
    """데이터 시트 저장"""
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        if 'id' in save_df.columns: save_df = save_df.drop(columns=['id'])
        save_df = save_df.fillna("")
        sheet.clear()
        sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())

# --- 3. 옵션 리스트 정의 ---
ROLE_OPTIONS = ["목사", "장로", "전도사", "시무권사", "협동목사", "협동장로", "협동권사", "협동안수집사", "은퇴장로", "은퇴권사", "은퇴협동권사", "집사", "청년", "성도"]
FAITH_OPTIONS = ["유아세례", "아동세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 4. 상세 수정 팝업 기능 (Dialog) ---
@st.dialog("성도 상세 정보 관리")
def edit_member_dialog(member_id, full_df):
    # 선택된 성도 추출
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    
    t1, t2, t3 = st.tabs(["📋 기본정보/기록", "📸 사진관리", "🛠 사역관리"])
    
    with t1:
        with st.form("edit_form_v82"):
            st.subheader(f"👤 {m_info['이름']} {m_info['직분']} 정보 수정")
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else 13)
                u_birth = st.text_input("생년월일 (yyyy-mm-dd)", value=str(m_info['생년월일']))
                u_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(m_info['신급']) if m_info['신급'] in FAITH_OPTIONS else 4)
            with c2:
                u_status = st.selectbox("교적상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS else 0)
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            st.write("---")
            st.write("**📝 목양 기록 및 심방 내용**")
            st.info(m_info['심방기록'] if m_info['심방기록'] else "기록된 내용이 없습니다.")
            new_note = st.text_area("새로운 심방 내용 추가")
            
            if st.form_submit_button("💾 시트에 저장 및 확인"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'], full_df.at[idx, '직분'] = u_name, u_role
                full_df.at[idx, '생년월일'], full_df.at[idx, '신급'] = u_birth, u_faith
                full_df.at[idx, '상태'], full_df.at[idx, '전화번호'] = u_status, format_phone(u_phone)
                full_df.at[idx, '이메일'], full_df.at[idx, '주소'] = u_email, u_addr
                
                if new_note.strip():
                    log_entry = f"[{date.today()}] {new_note.strip()}"
                    old_log = str(m_info['심방기록'])
                    full_df.at[idx, '심방기록'] = f"{old_log}\n{log_entry}" if old_log != "" else log_entry
                
                save_to_google(full_df)
                st.success("구글 시트에 성공적으로 동기화되었습니다!"); st.rerun()

    with t2:
        if m_info['사진']:
            st.image(m_info['사진'], width=200, caption="현재 등록된 사진")
        new_img = st.file_uploader("새 사진 선택", type=['jpg','png','jpeg'])
        if new_img:
            img = Image.open(new_img)
            cropped = st_cropper(img, aspect_ratio=(1,1))
            if st.button("📸 사진 업데이트"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = image_to_base64(cropped)
                save_to_google(full_df)
                st.success("사진이 변경되었습니다."); st.rerun()

    with t3:
        u_history = st.text_area("교회 사역 이력 및 봉사 내용", value=str(m_info['사역이력']), height=200)
        if st.button("🛠 사역 정보만 따로 저장"):
            idx = full_df[full_df['id'] == member_id].index[0]
            full_df.at[idx, '사역이력'] = u_history
            save_to_google(full_df)
            st.success("사역 정보가 업데이트되었습니다."); st.rerun()

# --- 5. 메인 화면: 성도 관리 (조회/수정) ---
st.title("⛪ 킹스턴한인교회 교적 관리 시스템 v8.2")

menu = st.sidebar.radio("📋 메뉴 선택", ["성도 명단 조회/수정", "신규 성도 등록", "주소록 PDF 생성"])

if menu == "성도 명단 조회/수정":
    df = load_data()
    if not df.empty:
        # 상단 필터부
        col1, col2, col3 = st.columns([1.5, 2, 1])
        with col1: search_name = st.text_input("🔍 성함으로 검색", placeholder="성함을 입력하세요")
        with col2: sel_statuses = st.multiselect("📍 상태별 보기", STATUS_OPTIONS, default=["출석 중"])
        with col3: sel_role = st.selectbox("🎓 직분 필터", ["전체"] + ROLE_OPTIONS)
        
        # 필터링 로직
        f_df = df.copy()
        if search_name: f_df = f_df[f_df['이름'].str.contains(search_name)]
        if sel_statuses: f_df = f_df[f_df['상태'].isin(sel_statuses)]
        if sel_role != "전체": f_df = f_df[f_df['직분'] == sel_role]

        st.markdown(f"**현재 조건 검색 결과:** {len(f_df)}명")
        
        # AgGrid 표 구성
        display_df = f_df[["이름", "직분", "생년월일", "전화번호", "상태", "id"]]
        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("id", hide=True)
        gb.configure_column("이름", pinned='left', width=100)
        gb.configure_default_column(resizable=True, filterable=True, sortable=True)
        grid_opts = gb.build()

        st.caption("💡 명단 왼쪽 체크박스를 클릭하면 상세 정보 팝업창이 나타납니다.")
        
        responses = AgGrid(
            display_df, 
            gridOptions=grid_opts, 
            theme='balham', 
            height=500, 
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            key="main_grid"
        )

        # 팝업 호출 로직
        selected = responses.get('selected_rows')
        if selected is not None:
            if isinstance(selected, pd.DataFrame) and not selected.empty:
                edit_member_dialog(int(selected.iloc[0]['id']), df)
            elif isinstance(selected, list) and len(selected) > 0:
                edit_member_dialog(int(selected[0]['id']), df)
    else:
        st.warning("불러올 데이터가 없습니다. 구글 시트를 확인해주세요.")

# --- 6. 신규 등록 메뉴 ---
elif menu == "신규 성도 등록":
    st.header("📝 새 가족 등록")
    with st.form("new_reg_form"):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("성함 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=13)
            n_birth = st.text_input("생년월일 (yyyy-mm-dd)")
            n_faith = st.selectbox("신급", FAITH_OPTIONS, index=4)
        with c2:
            n_phone = st.text_input("전화번호")
            n_email = st.text_input("이메일")
            n_addr = st.text_input("주소")
        
        n_history = st.text_area("특이사항 및 사역이력")
        
        if st.form_submit_button("➕ 교적부에 등록하기"):
            if n_name:
                curr_df = load_data()
                new_row = {col: "" for col in curr_df.columns if col != 'id'}
                new_row.update({
                    "이름": n_name, "직분