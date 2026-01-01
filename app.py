import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
from streamlit_cropper import st_cropper
from PIL import Image
import io
import base64
import requests
from fpdf import FPDF
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

# --- 1. 설정 및 데이터 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v12.0")

# --- 2. 유틸리티 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

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
    df = pd.DataFrame(data)
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

# --- 3. 상세 정보 수정 팝업 ---
@st.dialog("성도 상세 정보")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 관리"])
    
    with tab1:
        with st.form("edit_v12"):
            if m_info['사진']: st.image(m_info['사진'], width=150)
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ["성도", "집사", "권사", "장로", "목사"], index=0)
                # 2번 해결: 생년월일 범위 1900-2100으로 확장
                try: default_date = datetime.strptime(m_info['생년월일'], '%Y-%m-%d').date()
                except: default_date = date(1980, 1, 1)
                u_birth = st.date_input("생년월일", value=default_date, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            with c2:
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_family = st.text_area("가족 관계", value=str(m_info['가족']))
            if st.form_submit_button("✅ 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'], full_df.at[idx, '생년월일'] = u_name, u_birth.strftime('%Y-%m-%d')
                full_df.at[idx, '전화번호'], full_df.at[idx, '주소'] = u_phone, u_addr
                full_df.at[idx, '가족'] = u_family
                save_to_google(full_df)
                st.success("저장되었습니다."); st.rerun()

    with tab2:
        img_file = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'])
        if img_file:
            if 'rotation' not in st.session_state: st.session_state.rotation = 0
            c_r1, c_r2 = st.columns(2)
            if c_r1.button("🔄 왼쪽 90도"): st.session_state.rotation += 90
            if c_r2.button("🔄 오른쪽 90도"): st.session_state.rotation -= 90
            img = Image.open(img_file).rotate(st.session_state.rotation, expand=True)
            cropped = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📸 사진 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = image_to_base64(cropped)
                save_to_google(full_df)
                st.session_state.rotation = 0
                st.success("사진이 변경되었습니다."); st.rerun()

# --- 4. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부")
menu = st.sidebar.radio("메뉴", ["성도 관리", "신규 등록", "PDF 주소록"])

if menu == "성도 관리":
    df = load_data()
    if not df.empty:
        search_name = st.text_input("🔍 이름 검색")
        f_df = df[df['이름'].str.contains(search_name)] if search_name else df.copy()

        # 1번 해결: 체크박스-사진-이름-직분-전화번호-이메일-주소 순서 및 자동 크기
        thumbnail_js = JsCode("""
        function(params) {
            if (params.value && params.value.startsWith('data:image')) {
                return '<img src="' + params.value + '" style="width:35px;height:35px;border-radius:50%;object-fit:cover;">';
            } return 'N/A';
        }
        """)

        gb = GridOptionsBuilder.from_dataframe(f_df[["사진", "이름", "직분", "전화번호", "이메일", "주소", "id"]])
        gb.configure_selection('single', use_checkbox=True) # 체크박스를 맨 앞으로
        gb.configure_column("사진", headerName="📸", cellRenderer=thumbnail_js, width=80)
        gb.configure_column("이름", pinned='left')
        gb.configure_column("id", hide=True)
        # 자동 크기 조정 설정
        grid_opts = gb.build()

        responses = AgGrid(f_df, gridOptions=grid_opts, theme='balham', height=500, 
                           update_mode=GridUpdateMode.SELECTION_CHANGED, 
                           allow_unsafe_jscode=True,
                           fit_columns_on_grid_load=True) # Autosize 적용

        selected = responses.get('selected_rows')
        if selected is not None and len(selected) > 0:
            member_id = int(selected.iloc[0]['id']) if isinstance(selected, pd.DataFrame) else int(selected[0]['id'])
            edit_member_dialog(member_id, df)

elif menu == "PDF 주소록":
    st.header("🖨️ PDF 주소록 (한글 지원)")
    # 3번 해결: 한글 폰트 자동 다운로드 및 PDF 로직 전면 수정
    if st.button("📄 한글 포함 PDF 생성"):
        # 나눔고딕 폰트 다운로드 (서버에 폰트가 없을 때를 대비)
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        r = requests.get(font_url)
        with open("NanumGothic.ttf", "wb") as f: f.write(r.content)

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("Nanum", "", "NanumGothic.ttf", uni=True)
        pdf.set_font("Nanum", "", 16)
        pdf.cell(0, 15, "킹스턴 한인교회 주소록", ln=True, align='C')
        
        df = load_data()
        for _, r in df[df['상태']=="출석 중"].iterrows():
            y = pdf.get_y()
            if r['사진'].startswith('data:image'):
                img_data = base64.b64decode(r['사진'].split(',')[1])
                pdf.image(io.BytesIO(img_data), x=10, y=y, w=20, h=20)
            
            pdf.set_left_margin(35)
            pdf.set_font("Nanum", "", 11)
            pdf.cell(0, 8, f"성함: {r['이름']} ({r['직분']})", ln=True)
            pdf.cell(0, 6, f"전화: {r['전화번호']} | 생일: {r['생년월일']}", ln=True)
            pdf.cell(0, 6, f"주소: {r['주소']}", ln=True)
            pdf.set_left_margin(10)
            pdf.ln(5)
        
        st.download_button("📥 PDF 다운로드", data=bytes(pdf.output()), file_name="Church_Directory.pdf")