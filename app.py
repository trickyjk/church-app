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

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v7.8")

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
    # [생년월일 유실 방지 핵심] 모든 컬럼을 문자열로 읽고 결측치 제거
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null'], '')
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
STATUS_OPTIONS = ["전체", "출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 3. 상세 정보 수정 팝업 (Dialog) ---
@st.dialog("성도 상세 정보 및 수정")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    
    tab1, tab2 = st.tabs(["📄 정보 및 심방기록", "📷 사진 변경"])
    
    with tab1:
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("이름", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else 13)
                u_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(m_info['신급']) if m_info['신급'] in FAITH_OPTIONS else 4)
                u_birth = st.text_input("생년월일", value=str(m_info['생년월일']))
            with c2:
                u_status = st.selectbox("상태", STATUS_OPTIONS[1:], index=STATUS_OPTIONS[1:].index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS[1:] else 0)
                u_phone = st.text_input("전화번호", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_history = st.text_area("사역 이력", value=str(m_info['사역이력']))
            st.write("---")
            st.write("**📝 목양 기록 (심방 등)**")
            st.info(m_info['심방기록'] if m_info['심방기록'] else "기록된 심방 내용이 없습니다.")
            new_note = st.text_area("새로운 심방/특이사항 기록 추가")
            
            if st.form_submit_button("💾 데이터 저장 (구글 시트 동기화)"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'] = u_name
                full_df.at[idx, '직분'] = u_role
                full_df.at[idx, '신급'] = u_faith
                full_df.at[idx, '생년월일'] = u_birth
                full_df.at[idx, '상태'] = u_status
                full_df.at[idx, '전화번호'] = format_phone(u_phone)
                full_df.at[idx, '이메일'] = u_email
                full_df.at[idx, '주소'] = u_addr
                full_df.at[idx, '사역이력'] = u_history
                
                if new_note.strip():
                    log_entry = f"[{date.today()}] {new_note.strip()}"
                    old_log = str(m_info['심방기록'])
                    full_df.at[idx, '심방기록'] = f"{old_log}\n{log_entry}" if old_log and old_log != "" else log_entry
                
                save_to_google(full_df)
                st.success("성공적으로 저장되었습니다."); st.rerun()

    with tab2:
        if m_info['사진']:
            st.image(m_info['사진'], width=150, caption="현재 사진")
        img_file = st.file_uploader("새 사진 업로드", type=['jpg', 'png', 'jpeg'])
        if img_file:
            img = Image.open(img_file)
            cropped_img = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📷 사진 확정 및 저장"):
                b64_img = image_to_base64(cropped_img)
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = b64_img
                save_to_google(full_df)
                st.success("사진이 업데이트되었습니다."); st.rerun()

# --- 4. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부 시스템")
menu = st.sidebar.radio("메뉴 이동", ["성도 관리 (조회/수정)", "신규 성도 등록", "주소록 PDF 생성"])

if menu == "성도 관리 (조회/수정)":
    df = load_data()
    if not df.empty:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1: search = st.text_input("🔍 성함으로 찾기")
        with c2: f_status = st.selectbox("📍 상태 필터", STATUS_OPTIONS)
        with c3: f_role = st.selectbox("🎓 직분 필터", ["전체"] + ROLE_OPTIONS)
        
        filtered = df.copy()
        if search: filtered = filtered[filtered['이름'].str.contains(search)]
        if f_status != "전체": filtered = filtered[filtered['상태'] == f_status]
        if f_role != "전체": filtered = filtered[filtered['직분'] == f_role]

        st.markdown("---")
        # AgGrid 표시용 데이터 (사진 등 무거운 데이터 제외)
        display_df = filtered[["이름", "직분", "신급", "생년월일", "전화번호", "주소", "상태", "id"]]
        
        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("id", hide=True)
        gb.configure_column("이름", pinned='left', width=100)
        gb.configure_default_column(resizable=True, filterable=True, sortable=True)
        grid_opts = gb.build()

        st.caption("💡 명단 왼쪽의 체크박스를 선택하면 상세 정보 및 심방기록을 수정할 수 있는 팝업창이 나타납니다.")
        
        responses = AgGrid(
            display_df, 
            gridOptions=grid_opts, 
            theme='balham', 
            height=500, 
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            fit_columns_on_grid_load=True
        )

        # 행 선택 감지 및 팝업 호출
        selected = responses.get('selected_rows', [])
        if isinstance(selected, pd.DataFrame):
            if not selected.empty: edit_member_dialog(int(selected.iloc[0]['id']), df)
        elif len(selected) > 0:
            edit_member_dialog(int(selected[0]['id']), df)
    else:
        st.error("데이터를 가져오지 못했습니다. Google Sheets 연결 설정을 확인해 주세요.")

elif menu == "신규 성도 등록":
    st.header("📝 신규 성도 등록")
    with st.form("new_entry_form"):
        col1, col2 = st.columns(2)
        with col1:
            n_name = st.text_input("이름 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=13)
            n_faith = st.selectbox("신급", FAITH_OPTIONS, index=4)
            n_birth = st.text_input("생년월일 (YYYY-MM-DD)")
        with col2:
            n_phone = st.text_input("전화번호")
            n_email = st.text_input("이메일")
            n_addr = st.text_input("주소")
        n_history = st.text_area("사역 이력 및 자기소개")
        
        if st.form_submit_button("신규 등록 실행"):
            if n_name:
                df_curr = load_data()
                new_row = {col: "" for col in df_curr.columns if col != 'id'}
                new_row.update({
                    "이름": n_name, "직분": n_role, "신급": n_faith, 
                    "생년월일": n_birth, "전화번호": format_phone(n_phone), 
                    "이메일": n_email, "주소": n_addr, "사역이력": n_history, "상태": "출석 중"
                })
                save_to_google(pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True))
                st.success(f"{n_name} 성도님이 성공적으로 등록되었습니다."); st.rerun()
            else:
                st.warning("이름은 필수 입력 항목입니다.")

elif menu == "주소록 PDF 생성":
    st.header("🖨️ 교구 주소록 PDF 출력")
    df = load_data()
    t_status = st.multiselect("출력 대상 상태", STATUS_OPTIONS[1:], default=["출석 중"])
    
    if st.button("📄 PDF 주소록 생성 시작"):
        pdf = FPDF()
        pdf.add_page()
        # 한글 폰트 설정 (폰트 파일이 없을 경우 대비 예외처리)
        try:
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf')
            pdf.set_font('Nanum', '', 14)
        except:
            pdf.set_font('Arial', '', 14)
            
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C')
        pdf.ln(10)
        
        target_df = df[df['상태'].isin(t_status)]
        for _, row in target_df.iterrows():
            pdf.set_font('', 'B', 12)
            pdf.cell(0, 8, f"{row['이름']} {row['직분']} ({row['상태']})", ln=True)
            pdf.set_font('', '', 10)
            pdf.cell(0, 6, f"전화: {row['전화번호']} | 주소: {row['주소']}", ln=True)
            pdf.ln(3)
            
        st.download_button("📥 생성된 PDF 다운로드", data=bytes(pdf.output()), file_name="Church_AddressBook.pdf")