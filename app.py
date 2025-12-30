import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from streamlit_cropper import st_cropper
from PIL import Image, ImageDraw
import io
import base64
from fpdf import FPDF

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v2.7)")

# --- [기능] 이미지 처리 함수 ---
def image_to_base64(img):
    if img is None: return ""
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

# 사진 없을 때 사용할 교회 아이콘 생성 함수
def get_church_icon():
    img = Image.new('RGB', (150, 150), color=(240, 240, 240))
    d = ImageDraw.Draw(img)
    # 간단한 교회 모양 그리기 (삼각형 지붕 + 사각형 몸통)
    d.polygon([(75, 20), (20, 70), (130, 70)], fill=(100, 149, 237))
    d.rectangle([40, 70, 110, 130], fill=(100, 149, 237))
    d.rectangle([65, 90, 85, 130], fill=(255, 255, 255)) # 문
    return img

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
        st.error(f"⚠️ 연결 오류: {e}")
        return None

# --- 데이터 불러오기 ---
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
            df = df[cols]
            df.index = range(1, len(df) + 1)
            return df
        except:
            return pd.DataFrame(columns=["사진", "이름", "직분", "상태", "전화번호", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록"])
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy().fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# 직분 리스트 정의
ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]

# 사이드바 메뉴
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 수정
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    if not df.empty:
        col1, col2 = st.columns([2, 1]) 
        with col1:
            search = st.text_input("이름/전화번호 검색")
        with col2:
            status_opts = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 필터", options=status_opts)

        results = df.copy()
        if selected_status: results = results[results['상태'].isin(selected_status)]
        if search: results = results[results['이름'].str.contains(search) | results['전화번호'].str.contains(search)]

        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
                "상태": st.column_config.SelectboxColumn("상태", options=status_opts)
            },
            use_container_width=True,
            key="v2.7_editor"
        )
        if st.button("💾 정보 저장", type="primary"):
            df.update(edited_df)
            save_to_google(df)
            st.success("저장되었습니다.")
            st.rerun()

# 3. PDF 주소록 만들기
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성 (가족 단위)")
    df = load_data()
    # 3번 요청: 생년월일 옵션 추가
    inc_cols = st.multiselect("포함 정보", options=["생년월일", "자녀", "전화번호", "주소", "비즈니스 주소"], default=["생년월일", "자녀", "전화번호", "주소"])
    
    if st.button("📄 한글 PDF 생성"):
        pdf = FPDF()
        try:
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf') 
            pdf.set_font('Nanum', '', 12)
            font_ok = True
        except:
            pdf.set_font("Arial", '', 12)
            font_ok = False
            
        pdf.add_page()
        pdf.set_font('Nanum' if font_ok else 'Arial', '', 16)
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C')
        pdf.ln(5)

        df['addr_key'] = df['주소'].str.strip()
        # 주소별로 묶기
        for addr, group in df.groupby('addr_key', sort=False):
            if not addr or addr == "nan": continue # 주소 없는 경우 건너뜀
            
            y_start = pdf.get_y()
            if y_start > 230: pdf.add_page(); y_start = pdf.get_y()
            
            # 2번 요청: 가족 구성원 사진 나란히 배치
            x_offset = 10
            for idx, member in group.iterrows():
                if x_offset > 80: break # 사진이 너무 많으면 잘림 방지 (최대 2~3명)
                
                # 1번 요청: 사진 없으면 교회 아이콘
                if member['사진'] and "base64," in member['사진']:
                    try:
                        img_data = base64.b64decode(member['사진'].split(",")[1])
                        img_obj = Image.open(io.BytesIO(img_data))
                    except: img_obj = get_church_icon()
                else:
                    img_obj = get_church_icon()
                
                pdf.image(img_obj, x=x_offset, y=y_start, w=30, h=30)
                # 사진 밑에 이름 살짝 표시
                pdf.set_xy(x_offset, y_start + 31)
                pdf.set_font('Nanum' if font_ok else 'Arial', '', 8)
                pdf.cell(30, 5, member['이름'], align='C')
                x_offset += 32

            # 정보 텍스트 (사진 옆으로 이동)
            names_full = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            pdf.set_xy(110, y_start) # 텍스트 위치를 오른쪽으로 고정
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 12)
            pdf.multi_cell(0, 7, names_full)
            
            pdf.set_x(110)
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10)
            rep = group.iloc[0] # 대표 주소 정보
            details = "\n".join([f"{c}: {rep[c]}" for c in inc_cols if rep[c] and rep[c] != "nan" and rep[c] != ""])
            pdf.multi_cell(0, 6, details)
            
            pdf.set_y(y_start + 45) # 다음 가족을 위해 줄바꿈
            pdf.ln(5)

        pdf_bytes = pdf.output()
        st.download_button("📥 PDF 다운로드", data=bytes(pdf_bytes), file_name=f"KKC_AddressBook_{datetime.now().strftime('%Y%m%d')}.pdf")

# 2. 새가족 등록 (생략된 부분 동일하게 유지)
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    # ... 이전 코드와 동일 ...