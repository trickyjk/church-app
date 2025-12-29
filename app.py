import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from streamlit_cropper import st_cropper
from PIL import Image
import io
import base64
from fpdf import FPDF # PDF 생성을 위한 라이브러리

# --- 구글 시트 및 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v1.6 - PDF 생성 지원)")

# --- [추가] PDF 생성을 위한 클래스 ---
class AddressBookPDF(FPDF):
    def header(self):
        self.add_font('Nanum', '', 'NanumGothic.ttf', uni=True) # 한글 폰트 설정이 필요할 수 있습니다.
        self.set_font('Nanum', '', 16)
        self.cell(0, 10, '킹스턴한인교회 성도 주소록', 0, 1, 'C')
        self.ln(5)

# --- 이미지 처리 함수 ---
def image_to_base64(img):
    if img is None: return ""
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

# --- 데이터 로드/저장 함수 (이전 버전과 동일) ---
def get_sheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        return gspread.authorize(creds).open(SHEET_NAME).sheet1
    except: return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    data = sheet.get_all_records()
    cols = ["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"]
    df = pd.DataFrame(data).astype(str)
    for c in cols:
        if c not in df.columns: df[c] = ""
    df = df[cols]
    df.index = range(1, len(df) + 1)
    return df

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# --- 1 & 2 메뉴는 이전 코드를 유지 (지면상 핵심 로직 위주 기술) ---
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    # ... [검색 및 수정 로직 동일] ...
    st.write("기존 수정 기능을 사용하세요.")
    st.data_editor(df, use_container_width=True)

elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    # ... [등록 로직 동일] ...

# --- [신규] 3. PDF 주소록 만들기 ---
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    
    st.info("주소록에 포함할 항목과 대상을 선택하세요.")
    
    col1, col2 = st.columns(2)
    with col1:
        target_status = st.multiselect("대상 상태 선택", options=["출석 중", "새가족"], default=["출석 중"])
        include_cols = st.multiselect("포함할 정보 선택", 
                                     options=["전화번호", "주소", "비즈니스 주소", "자녀", "생년월일"],
                                     default=["전화번호", "주소", "자녀"])
    
    if st.button("📄 PDF 주소록 생성 및 다운로드"):
        pdf_df = df[df['상태'].isin(target_status)]
        
        pdf = FPDF()
        pdf.add_page()
        # 한글 폰트 경로 (GitHub 업로드시 폰트 파일도 함께 올려야 합니다)
        # pdf.add_font('Nanum', '', 'NanumGothic.ttf', uni=True) 
        pdf.set_font('Arial', 'B', 16) 
        
        pdf.cell(0, 10, 'Kingston Korean Church Address Book', 0, 1, 'C')
        pdf.ln(10)
        
        for idx, row in pdf_df.iterrows():
            # 한 페이지에 5명씩 배치하기 위해 높이 조절
            start_y = pdf.get_y()
            
            # 1. 사진 넣기 (Base64 변환 이미지)
            if row['사진'] and "base64," in row['사진']:
                try:
                    img_data = base64.b64decode(row['사진'].split(",")[1])
                    img_file = io.BytesIO(img_data)
                    img = Image.open(img_file)
                    pdf.image(img, x=10, y=start_y, w=30, h=30)
                except:
                    pdf.rect(10, start_y, 30, 30) # 사진 없을시 빈 박스
            else:
                pdf.rect(10, start_y, 30, 30)

            # 2. 텍스트 정보 (사진 옆으로 배치)
            pdf.set_xy(45, start_y)
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 7, f"{row['이름']} {row['직분']}", 0, 1)
            
            pdf.set_x(45)
            pdf.set_font('Arial', '', 10)
            info_text = ""
            for col in include_cols:
                info_text += f"{col}: {row[col]}  "
            pdf.multi_cell(0, 6, info_text)
            
            pdf.ln(10) # 다음 사람과의 간격
            
            # 페이지 하단 도달시 자동 페이지 추가
            if pdf.get_y() > 250:
                pdf.add_page()

        pdf_output = pdf.output(dest='S').encode('latin-1')
        st.download_button(label="📥 PDF 파일 다운로드", 
                           data=pdf_output, 
                           file_name=f"church_address_book_{datetime.now().strftime('%Y%m%d')}.pdf",
                           mime="application/pdf")