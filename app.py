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
st.title("⛪ 킹스턴한인교회 교적부 (v4.7)")

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
            # 최신 컬럼 정의 (신급, 사역이력 포함)
            cols = ["사진", "이름", "직분", "신급", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록", "등록신청일", "등록일", "사역이력"]
            
            if not data: return pd.DataFrame(columns=cols)
            
            df = pd.DataFrame(data).astype(str)
            # 없는 컬럼은 빈 칸으로 자동 생성 (매뉴얼 추가 불필요)
            for c in cols:
                if c not in df.columns: df[c] = ""
            
            df['생년월일'] = df['생년월일'].apply(safe_parse_date)
            df['등록신청일'] = df['등록신청일'].apply(safe_parse_date)
            df['등록일'] = df['등록일'].apply(safe_parse_date)
            df['전화번호'] = df['전화번호'].apply(format_phone)
            
            df = df[cols]
            df.index = range(1, len(df) + 1)
            return df
        except: return pd.DataFrame(columns=["사진", "이름", "직분", "신급", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록", "등록신청일", "등록일", "사역이력"])
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

# 옵션 설정
ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
FAITH_OPTIONS = ["유아세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]

menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 수정
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
            results = results[results['이름'].str.contains(search) | 
                              results['전화번호'].str.contains(search) | 
                              results['사역이력'].str.contains(search)]

        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
                "신급": st.column_config.SelectboxColumn("신급", options=FAITH_OPTIONS),
                "생년월일": st.column_config.DateColumn("생년월일", format="YYYY-MM-DD", min_value=date(1850, 1, 1)),
                "전화번호": st.column_config.TextColumn("전화번호")
            },
            use_container_width=True,
            key="v4.7_editor"
        )
        if st.button("💾 정보 저장", type="primary"):
            edited_df['전화번호'] = edited_df['전화번호'].apply(format_phone)
            df.update(edited_df)
            save_to_google(df)
            st.success("정보가 저장되었습니다.")
            st.rerun()

        st.divider()
        if not results.empty:
            sel_person = st.selectbox("🎯 대상 선택:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '직분']})")
            t1, t2 = st.tabs(["✍️ 사역 및 목양 기록", "📷 사진 변경"])
            with t1:
                c_a, c_b = st.columns(2)
                with c_a:
                    st.write("**현재 사역 이력**")
                    st.info(df.loc[sel_person, '사역이력'] if df.loc[sel_person, '사역이력'] != "nan" else "기록 없음")
                with c_b:
                    st.write("**목양/심방 기록**")
                    st.text_area("기록 요약", value=df.loc[sel_person, '심방기록'], height=100, disabled=True)
                
                with st.form("update_form"):
                    new_h = st.text_input("새 사역 (예: 2026년 찬양팀장)")
                    new_v = st.text_area("새 목양 내용")
                    if st.form_submit_button("기록 업데이트"):
                        if new_h:
                            old_h = df.at[sel_person, '사역이력']
                            df.at[sel_person, '사역이력'] = f"{old_h} / {new_h}" if old_h and old_h != "nan" else new_h
                        if new_v:
                            log = f"[{datetime.now().strftime('%Y-%m-%d')}] {new_v}"
                            old_v = df.at[sel_person, '심방기록']
                            df.at[sel_person, '심방기록'] = f"{old_v}\n{log}" if old_v and old_v != "nan" else log
                        save_to_google(df)
                        st.success("수정되었습니다.")
                        st.rerun()
            with t2:
                up_file = st.file_uploader("사진 업로드")
                if up_file:
                    img = Image.open(up_file)
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
            role = st.selectbox("직분", ROLE_OPTIONS, index=6)
            faith = st.selectbox("신급", FAITH_OPTIONS)
            birth = st.date_input("생년월일", value=date(1980, 1, 1), min_value=date(1850, 1, 1))
        with c2:
            phone = st.text_input("전화번호 (숫자만)")
            email = st.text_input("이메일")
            addr = st.text_input("주소")
            history = st.text_input("사역 이력 (있는 경우)")
        
        note = st.text_area("목양 노트 (상담 내용)")
        
        if st.form_submit_button("⛪ 등록"):
            if name:
                df_curr = load_data()
                initial_log = f"[{datetime.now().strftime('%Y-%m-%d')} 등록상담] {note}" if note else ""
                new_row = pd.DataFrame([[
                    "", name, role, faith, "새가족", format_phone(phone), email, str(birth), addr, "", "", initial_log, str(date.today()), "", history
                ]], columns=df_curr.columns)
                save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
                st.success(f"'{name}' 성도님 등록 완료!")
            else:
                st.error("이름을 입력하세요.")

# 3. PDF 주소록 만들기
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    if st.button("📄 주소록 PDF 생성"):
        # (PDF 생성 로직 동일...)
        pass