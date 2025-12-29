import streamlit as st
import pdfplumber
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from streamlit_cropper import st_cropper
from PIL import Image
import io
import base64

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v1.5)")

# --- [기능] 이미지 처리 함수 ---
def image_to_base64(img):
    if img is None: return ""
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

# --- 구글 시트 연결 함수 ---
def get_sheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        if "429" in str(e):
            st.error("⚠️ 구글 서버 접속이 지연되고 있습니다. 1분 후 새로고침 해주세요.")
        else:
            st.error(f"구글 시트 연결 실패: {e}")
        return None

# --- 데이터 불러오기 (컬럼 순서 및 번호 수정) ---
def load_data():
    sheet = get_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            # [수정] 목사님이 원하시는 컬럼 순서로 재배치 (이름 -> 직분 -> 상태 순)
            cols = ["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"]
            
            if not data: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data).astype(str)
            
            # 부족한 컬럼 채우기
            for c in cols:
                if c not in df.columns: df[c] = ""
            
            # 불필요한 행 제거 (헤더 중복 등)
            if '이름' in df.columns:
                df = df[~df['이름'].str.replace(' ', '').isin(['이름', 'Name', '번호'])]
            
            # [수정] 결과 데이터프레임을 지정한 컬럼 순서대로 정리
            df = df[cols]
            
            # [수정] 번호를 1번부터 시작하도록 변경
            df.index = range(1, len(df) + 1)
            
            return df
        except:
            return pd.DataFrame(columns=["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"])
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        # 저장할 때는 인덱스를 제외하고 데이터만 저장
        save_df = df.copy().fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. (관리자용) PDF 초기화"])

if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    
    if not df.empty:
        col1, col2 = st.columns([2, 1