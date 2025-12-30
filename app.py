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
st.title("⛪ 킹스턴한인교회 교적부 (v4.1)")

# --- [기능] 이미지 처리 및 날짜 변환 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85, subsampling=0)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

def safe_parse_date(val):
    """숫자 8자리 혹은 다양한 형식을 날짜 객체로 변환"""
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return None
    clean_val = "".join(filter(str.isdigit, str(val)))
    try:
        if len(clean_val) == 8: # 19701228 형식 대응
            return datetime.strptime(clean_val, "%Y%m%d").date()
        return pd.to_datetime(val).date()
    except: return None

# --- 구글 시트 연결 및 데이터 로드 ---
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

def load_data():
    sheet = get_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            cols = ["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"]
            if not data: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data).astype(str)
            for c in cols:
                if c not in df.columns: df[c] = ""
            # 날짜 형식으로 변환하여 표에 표시
            df['생년월일'] = df['생년월일'].apply(safe_parse_date)
            df = df[cols]
            df.index = range(1, len(df) + 1)
            return df
        except: return pd.DataFrame(columns=["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"])
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        # 구글 시트 저장 시에는 YYYY-MM-DD 문자열로 변환
        save_df['생년월일'] = save_df['생년월일'].apply(lambda x: str(x) if x else "")
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
        with col1: search = st.text_input("이름/전화번호 검색")
        with col2:
            status_opts = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 필터", options=status_opts)

        results = df.copy()
        if selected_status: results = results[results['상태'].isin(selected_status)]
        if search: results = results[results['이름'].str.contains(search) | results['전화번호'].str.contains(search)]

        # [수정] DateColumn의 입력 범위를 연도 4자리에 최적화
        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
                "상태": st.column_config.SelectboxColumn("상태", options=status_opts),
                "생년월일": st.column_config.DateColumn(
                    "생년월일",
                    format="YYYY-MM-DD",
                    min_value=date(1900, 1, 1),
                    max_value=date(2100, 12, 31),
                    step=1
                )
            },
            use_container_width=True,
            key="v4.1_editor"
        )
        if st.button("💾 정보 저장", type="primary"):
            df.update(edited_df)
            save_to_google(df)
            st.success("저장되었습니다.")
            st.rerun()

        st.divider()
        if not results.empty:
            sel_person = st.selectbox("🎯 대상 선택:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '직분']})")
            # 심방기록 및 사진 업로드 로직 동일 유지