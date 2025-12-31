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

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v5.5)")

# --- [기능] 데이터 포맷 및 이미지 처리 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85, subsampling=0)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

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

# --- 구글 시트 연결 ---
def get_sheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception: return None

# --- 데이터 로드 및 저장 ---
def load_data():
    sheet = get_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            cols = ["사진", "이름", "직분", "신급", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록", "등록신청일", "등록일", "사역이력"]
            if not data: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data).astype(str)
            for c in cols:
                if c not in df.columns: df[c] = ""
            df['생년월일'] = df['생년월일'].apply(safe_parse_date)
            df['등록신청일'] = df['등록신청일'].apply(safe_parse_date)
            df['등록일'] = df['등록일'].apply(safe_parse_date)
            df['전화번호'] = df['전화번호'].apply(format_phone)
            df = df[cols]
            df.index = range(1, len(df) + 1)
            return df
        except: return pd.DataFrame(columns=cols)
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        for date_col in ['생년월일', '등록신청일', '등록일']:
            save_df[date_col] = save_df[date_col].apply(lambda x: str(x) if x else "")
        save_df['전화번호'] = save_df['전화번호'].apply(format_phone)
        save_df = save_df.fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
FAITH_OPTIONS = ["유아세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]

menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 수정 (동일)
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    if not df.empty:
        col1, col2 = st.columns([2, 1]) 
        with col1: search = st.text_input("이름/전화번호/사역이력 검색")
        with col2: selected_status = st.multiselect("상태별 필터", options=STATUS_OPTIONS)
        results = df.copy()
        if selected_status: results = results[results['상태'].isin(selected_status)]
        if search: 
            results = results[results['이름'].str.contains(search, na=False) | 
                              results['전화번호'].str.contains(search, na=False) | 
                              results['사역이력'].str.contains(search, na=False)]
        edited_df = st.data_editor(results, column_config={
            "사진": st.column_config.ImageColumn("사진", width="small"),
            "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
            "신급": st.column_config.SelectboxColumn("신급", options=FAITH_OPTIONS),
            "상태": st.column_config.SelectboxColumn("상태", options=STATUS_OPTIONS),
            "생년월일": st.column_config.DateColumn("생년월일", format="YYYY-MM-DD", min_value=date(1850, 1, 1), max_value=date(2100, 12, 31)),
            "전화번호": st.column_config.TextColumn("전화번호")
        }, use_container_width=True, key="v5.5_editor")
        if st.button("💾 정보 저장", type="primary"):
            edited_df['전화번호'] = edited_df['전화번호'].apply(format_phone)
            df.update(edited_df)
            save_to_google(df)
            st.success("정보가 저장되었습니다.")
            st.rerun()

# 2. 새가족 등록 (동일)
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    if 'reg_success' in st.session_state and st.session_state.reg_success:
        st.success(f"✅ {st.session_state.last_name} 성도님 등록 완료!")
        st.session_state.reg_success = False
    with st.form("new_fam", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name, role = st.text_input("이름 (필수)"), st.selectbox("직분", ROLE_OPTIONS, index=6)
            faith, birth = st.selectbox("신급", FAITH_OPTIONS), st.date_input("생년월일", value=date(2000, 1, 1), min_value=date(1850, 1, 1))
            apply_date, reg_date = st.date_input("등록 신청일", value=date.today()), st.date_input("등록일", value=date.today())
        with c2:
            phone, email, addr = st.text_input("전화번호"), st.text_input("이메일"), st.text_input("주소")
            history, note = st.text_input("사역 이력"), st.text_area("목양 노트", height=150)
        if st.form_submit_button("⛪ 성도 등록하기", type="primary"):
            if name:
                df_curr = load_data()
                new_row = pd.DataFrame([["", name, role, faith, "새가족", format_phone(phone), email, str(birth), addr, "", "", note, str(apply_date), str(reg_date), history]], columns=df_curr.columns)
                save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
                st.session_state.reg_success, st.session_state.last_name = True, name
                st.rerun()
            else: st.error("이름을 입력하세요.")

# 3. PDF 주소록 만들기 (정렬 기능 추가)
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    
    st.subheader("👥 포함할 성도 선택")
    target_status = st.multiselect("출력할 성도 상태 선택", options=STATUS_OPTIONS, default=["출석 중", "새가족"])
    
    st.subheader("📋 포함할 정보 선택")
    col_a, col_b, col_c = st.columns(3)
    with col_a: inc_birth, inc_phone = st.checkbox("생년월일 포함", True), st.checkbox("전화번호 포함", True)
    with col_b: inc_addr, inc_email = st.checkbox("주소 포함", True), st.checkbox("이메일 포함", False)
    with col_c: inc_history = st.checkbox("사역이력 포함", False)

    if st.button("📄 주소록 PDF 생성"):
        print_df = df.copy()
        if target_status:
            print_df = print_df[print_df['상태'].isin(target_status)]
            
        if print_df.empty:
            st.warning("선택한 조건에 해당하는 성도가 없습니다.")
            st.stop()

        pdf = FPDF()
        try:
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf') 
            pdf.set_font('Nanum', '', 12); font_ok = True
        except:
            pdf.set_font("Arial", '', 12); font_ok = False
        
        pdf.add_page()
        pdf.set_font('Nanum' if font_ok else 'Arial', '', 16)
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C'); pdf.ln(5)
        
        print_df['addr_key'] = print_df['주소'].str.strip()
        
        # [핵심] 주소지 그룹별로 첫 번째 사람의 이름을 기준으로 ㄱ-ㅎ 정렬
        group_list = []
        for addr, group in print_df.groupby('addr_key', sort=False):
            if not addr or addr == "nan": continue
            first_name = group.iloc[0]['이름']
            group_list.append({'addr': addr, 'group': group, 'sort_key': first_name})
        
        # 성씨 기준 가나다순 정렬
        sorted_groups = sorted(group_list, key=lambda x: x['sort_key'])
        
        for item in sorted_groups:
            addr, group = item['addr'], item['group']
            y_start = pdf.get_y()
            if y_start > 230: pdf.add_page(); y_start = pdf.get_y()
            x_pos = 10
            for _, member in group.iterrows():
                if x_pos > 85: break 
                img_to_print = None
                if member['사진'] and "base64," in member['사진']:
                    try:
                        img_data = base64.b64decode(member['사진'].split(",")[1])
                        img_to_print = Image.open(io.BytesIO(img_data))
                    except: pass
                if img_to_print:
                    if img_to_print.mode != "RGB": img_to_print = img_to_print.convert("RGB")
                    pdf.image(img_to_print, x=x_pos, y=y_start, w=30, h=30)
                else:
                    if os.path.exists("church_icon.png"): pdf.image("church_icon.png", x=x_pos, y=y_start, w=30, h=30)
                    else: pdf.rect(x_pos, y_start, 30, 30)
                pdf.set_xy(x_pos, y_start + 31); pdf.set_font('Nanum' if font_ok else 'Arial', '', 8)
                pdf.cell(30, 5, member['이름'], align='C'); x_pos += 32
            
            names_text = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            pdf.set_xy(110, y_start); pdf.set_font('Nanum' if font_ok else 'Arial', '', 12)
            pdf.multi_cell(0, 7, names_text)
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10); rep = group.iloc[0]; info_lines = []
            if inc_birth and rep['생년월일']: info_lines.append(f"생일: {rep['생년월일']}")
            if inc_phone and rep['전화번호']: info_lines.append(f"전화: {rep['전화번호']}")
            if inc_addr and rep['주소']: info_lines.append(f"주소: {rep['주소']}")
            if inc_email and rep['이메일']: info_lines.append(f"메일: {rep['이메일']}")
            if inc_history and rep['사역이력']: info_lines.append(f"사역: {rep['사역이력']}")
            pdf.set_x(110); pdf.multi_cell(0, 6, "\n".join(info_lines))
            pdf.set_y(y_start + 45); pdf.ln(5)
            
        pdf_out = pdf.output()
        st.download_button("📥 다운로드", data=bytes(pdf_out), file_name=f"KKC_AddressBook_{datetime.now().strftime('%Y%m%d')}.pdf")