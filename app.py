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

# --- 설정 및 데이터 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v6.2)")

# --- [기능] 유틸리티 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85, subsampling=0)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def safe_parse_date(val):
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return None
    clean_val = "".join(filter(str.isdigit, str(val)))
    try:
        if len(clean_val) == 8: return datetime.strptime(clean_val, "%Y%m%d").date()
        return pd.to_datetime(val).date()
    except: return None

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
    except: return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    data = sheet.get_all_records()
    cols = ["사진", "이름", "직분", "신급", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록", "등록신청일", "등록일", "사역이력"]
    df = pd.DataFrame(data).astype(str)
    for c in cols:
        if c not in df.columns: df[c] = ""
    df['생년월일'] = df['생년월일'].apply(safe_parse_date)
    df.index = range(1, len(df) + 1)
    return df[cols]

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        for d in ['생년월일', '등록신청일', '등록일']:
            save_df[d] = save_df[d].apply(lambda x: str(x) if x else "")
        save_df = save_df.fillna("")
        sheet.clear()
        sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())

# 직분 및 신급 옵션
ROLE_OPTIONS = [
    "목사", "장로", "전도사", "시무권사", 
    "협동목사", "협동장로", "협동권사", "협동안수집사",
    "은퇴장로", "은퇴권사", "은퇴협동권사", "집사", "청년", "성도"
]
FAITH_OPTIONS = ["유아세례", "아동세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- [상세 정보 수정 팝업 함수] ---
@st.dialog("성도 상세 정보 및 수정")
def edit_member_dialog(member_id, df):
    m_info = df.loc[member_id]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📷 사진 변경"])
    with tab1:
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("이름", value=m_info['이름'])
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else len(ROLE_OPTIONS)-1)
                u_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(m_info['신급']) if m_info['신급'] in FAITH_OPTIONS else 4)
                u_birth = st.date_input("생년월일", value=m_info['생년월일'] if m_info['생년월일'] else date(2000,1,1))
            with c2:
                u_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS else 0)
                u_phone = st.text_input("전화번호", value=m_info['전화번호'])
                u_email = st.text_input("이메일", value=m_info['이메일'])
                u_addr = st.text_input("주소", value=m_info['주소'])
            u_history = st.text_area("사역 이력", value=m_info['사역이력'])
            new_note = st.text_area("신규 목양 기록 추가")
            if st.form_submit_button("💾 저장하기", type="primary"):
                df.at[member_id, '이름'], df.at[member_id, '직분'], df.at[member_id, '신급'] = u_name, u_role, u_faith
                df.at[member_id, '생년월일'], df.at[member_id, '상태'], df.at[member_id, '전화번호'] = u_birth, u_status, format_phone(u_phone)
                df.at[member_id, '이메일'], df.at[member_id, '주소'], df.at[member_id, '사역이력'] = u_email, u_addr, u_history
                if new_note:
                    log = f"[{date.today()}] {new_note}"; old = m_info['심방기록']
                    df.at[member_id, '심방기록'] = f"{old}\n{log}" if old else log
                save_to_google(df); st.success("성공적으로 저장되었습니다."); st.rerun()
    with tab2:
        if m_info['사진']: st.image(m_info['사진'], width=200)
        up_file = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'])
        if up_file:
            cropped = st_cropper(Image.open(up_file), aspect_ratio=(1,1))
            if st.button("📷 사진 확정"):
                df.at[member_id, '사진'] = image_to_base64(cropped)
                save_to_google(df); st.rerun()

# --- 메인 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 관리", "2. 신규 등록", "3. PDF 주소록 만들기"])

if menu == "1. 성도 검색 및 관리":
    df = load_data()
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1: search = st.text_input("이름, 전화번호, 사역 검색")
    with col_s2: s_status = st.multiselect("상태 필터", STATUS_OPTIONS, default=["출석 중"])
    
    results = df.copy()
    if s_status: results = results[results['상태'].isin(s_status)]
    if search:
        results = results[results['이름'].str.contains(search, na=False) | 
                          results['전화번호'].str.contains(search, na=False) | 
                          results['사역이력'].str.contains(search, na=False)]
    
    st.write(f"총 {len(results)}명")

    # [수정 포인트] Column Config를 통한 Cell 너비 최적화 (Autosize 효과)
    st.dataframe(
        results[["사진", "이름", "직분", "전화번호", "상태", "주소", "사역이력"]],
        column_config={
            "사진": st.column_config.ImageColumn("사진", width="small"),
            "이름": st.column_config.TextColumn("이름", width="small"),
            "직분": st.column_config.TextColumn("직분", width="small"),
            "전화번호": st.column_config.TextColumn("전화번호", width="medium"),
            "상태": st.column_config.TextColumn("상태", width="small"),
            "주소": st.column_config.TextColumn("주소", width="large"),
            "사역이력": st.column_config.TextColumn("사역이력", width="large"),
        },
        use_container_width=True,
        hide_index=True
    )

    selected_target = st.selectbox("✏️ 수정을 원하는 성도 이름을 선택하면 팝업이 열립니다:", 
                                  options=[None] + list(results.index),
                                  format_func=lambda x: f"▶ {results.loc[x, '이름']} {results.loc[x, '직분']}" if x else "성도를 선택하세요")
    
    if selected_target:
        edit_member_dialog(selected_target, df)

elif menu == "2. 신규 등록":
    st.header("📝 신규 성도 등록")
    with st.form("new_reg"):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("이름 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=len(ROLE_OPTIONS)-1)
            n_faith = st.selectbox("신급", FAITH_OPTIONS, index=4)
            n_birth = st.date_input("생년월일", value=date(2000, 1, 1))
        with c2:
            n_phone, n_addr = st.text_input("전화번호"), st.text_input("주소")
            n_status = st.selectbox("상태", STATUS_OPTIONS)
        if st.form_submit_button("등록하기", type="primary"):
            if n_name:
                df_curr = load_data()
                new_row = [["", n_name, n_role, n_faith, n_status, format_phone(n_phone), "", str(n_birth), n_addr, "", "", "", str(date.today()), str(date.today()), ""]]
                save_to_google(pd.concat([df_curr, pd.DataFrame(new_row, columns=df_curr.columns)], ignore_index=True))
                st.success("등록되었습니다!"); st.rerun()

elif menu == "3. PDF 주소록 만들기":
    # 이전 버전과 동일 (안정적)
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    t_status = st.multiselect("대상 상태", STATUS_OPTIONS, default=["출석 중"])
    if st.button("📄 PDF 생성"):
        pdf = FPDF()
        try: pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf'); f_name = 'Nanum'
        except: f_name = 'Arial'
        pdf.add_page(); pdf.set_font(f_name, '', 16)
        pdf.cell(0, 10, "KKC Address Book", ln=True, align='C'); pdf.ln(5)
        p_df = df[df['상태'].isin(t_status)].copy()
        for _, m in p_df.sort_values('이름').iterrows():
            pdf.set_font(f_name, '', 12)
            pdf.cell(0, 10, f"{m['이름']} {m['직분']} | {m['전화번호']} | {m['주소']}", ln=True)
        st.download_button("📥 다운로드", data=bytes(pdf.output()), file_name="AddressBook.pdf")