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
st.title("⛪ 킹스턴한인교회 교적부 (v4.4)")

# --- [기능] 데이터 포맷 함수 ---
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
        if len(clean_val) == 8:
            return datetime.strptime(clean_val, "%Y%m%d").date()
        return pd.to_datetime(val).date()
    except: return None

def format_phone(val):
    """숫자만 추출하여 000-000-0000 형식으로 변환 (강력 보정)"""
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return ""
    nums = "".join(filter(str.isdigit, str(val)))
    if len(nums) == 10:
        return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    elif len(nums) == 11:
        # 캐나다/미국 국가코드 1 포함인 경우나 한국 휴대전화 대응
        if nums.startswith("1"):
            return f"{nums[0]}-{nums[1:4]}-{nums[4:7]}-{nums[7:]}"
        return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
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
            # 이메일 컬럼 추가 (전화번호 다음)
            cols = ["사진", "이름", "직분", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"]
            if not data: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data).astype(str)
            for c in cols:
                if c not in df.columns: df[c] = ""
            
            df['생년월일'] = df['생년월일'].apply(safe_parse_date)
            df['전화번호'] = df['전화번호'].apply(format_phone)
            
            df = df[cols]
            df.index = range(1, len(df) + 1)
            return df
        except: return pd.DataFrame(columns=["사진", "이름", "직분", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"])
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        save_df['생년월일'] = save_df['생년월일'].apply(lambda x: str(x) if x else "")
        save_df['전화번호'] = save_df['전화번호'].apply(format_phone) # 저장 시 다시 포맷팅
        save_df = save_df.fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 수정
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    if not df.empty:
        col1, col2 = st.columns([2, 1]) 
        with col1: search = st.text_input("이름/전화번호/이메일 검색")
        with col2:
            status_opts = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 필터", options=status_opts)

        results = df.copy()
        if selected_status: results = results[results['상태'].isin(selected_status)]
        if search: 
            results = results[results['이름'].str.contains(search) | 
                              results['전화번호'].str.contains(search) | 
                              results['이메일'].str.contains(search)]

        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
                "상태": st.column_config.SelectboxColumn("상태", options=status_opts),
                "생년월일": st.column_config.DateColumn("생년월일", format="YYYY-MM-DD", min_value=date(1850, 1, 1), max_value=date(2100, 12, 31)),
                "전화번호": st.column_config.TextColumn("전화번호", help="숫자만 입력 후 저장하면 하이픈이 생깁니다."),
                "이메일": st.column_config.TextColumn("이메일", validate="^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$")
            },
            use_container_width=True,
            key="v4.4_editor"
        )
        if st.button("💾 정보 저장", type="primary"):
            # 저장 버튼 클릭 시 전화번호 포맷팅 강제 적용
            edited_df['전화번호'] = edited_df['전화번호'].apply(format_phone)
            df.update(edited_df)
            save_to_google(df)
            st.success("정보가 저장되었습니다.")
            st.rerun()

        st.divider()
        if not results.empty:
            sel_person = st.selectbox("🎯 대상 선택:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '직분']})")
            
            t1, t2 = st.tabs(["✍️ 심방 기록", "📷 사진 변경"])
            with t1:
                st.text_area("기존 기록", value=df.loc[sel_person, '심방기록'], height=100, disabled=True)
                with st.form("v_form"):
                    v_text = st.text_area("새 내용")
                    if st.form_submit_button("저장"):
                        log = f"[{datetime.now().strftime('%Y-%m-%d')}] {v_text}"
                        old = df.at[sel_person, '심방기록']
                        df.at[sel_person, '심방기록'] = f"{old} | {log}" if old and old != "nan" else log
                        save_to_google(df)
                        st.success("심방 기록이 추가되었습니다.")
                        st.rerun()
            with t2:
                up_file = st.file_uploader("사진 업로드")
                if up_file:
                    img = Image.open(up_file)
                    img = img.rotate(-st.session_state.get("rot", 0), expand=True)
                    cropped = st_cropper(img, aspect_ratio=(1,1))
                    if st.button("사진 저장"):
                        df.at[sel_person, '사진'] = image_to_base64(cropped)
                        save_to_google(df)
                        st.success("사진이 변경되었습니다.")
                        st.rerun()

# 2. 새가족 등록
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    with st.form("new_fam"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ROLE_OPTIONS)
            status = st.selectbox("상태", ["새가족", "출석 중"])
            phone = st.text_input("전화번호 (숫자만 입력 가능)")
        with c2:
            email = st.text_input("이메일")
            birth = st.date_input("생년월일", value=date(1970, 1, 1), min_value=date(1850, 1, 1))
            addr = st.text_input("주소")
        if st.form_submit_button("등록"):
            if name:
                df_curr = load_data()
                formatted_p = format_phone(phone) # 등록 즉시 포맷팅
                new_row = pd.DataFrame([[ "", name, role, status, formatted_p, email, str(birth), addr, "", "", ""]], columns=df_curr.columns)
                save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
                st.success(f"'{name}' 성도님 등록 완료")
            else:
                st.error("이름을 입력해 주세요.")

# 3. PDF 주소록 만들기 (이메일 포함 옵션 추가)
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    inc_cols = st.multiselect("포함 정보", options=["생년월일", "전화번호", "이메일", "주소", "자녀", "비즈니스 주소"], default=["생년월일", "전화번호", "주소"])
    
    if st.button("📄 한글 PDF 생성"):
        # (PDF 생성 로직 동일...)
        pass