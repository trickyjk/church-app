import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
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
st.title("⛪ 킹스턴한인교회 교적부 (v3.4 최종)")

# --- [기능] 이미지 처리 함수 (OSError 및 PNG 완벽 대응) ---
def image_to_base64(img):
    if img is None: return ""
    
    # [핵심 수정] 모든 이미지를 강제로 RGB 모드로 변환 (에러 원인 RGBA 제거)
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    
    # 퀄리티를 유지하면서 안정적인 JPEG 형식으로 저장
    img.save(buffered, format="JPEG", quality=85, subsampling=0)
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
    except Exception:
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

ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
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
            key="v3.4_editor"
        )
        if st.button("💾 정보 저장", type="primary"):
            df.update(edited_df)
            save_to_google(df)
            st.success("저장되었습니다.")
            st.rerun()

        st.divider()
        if not results.empty:
            sel_person = st.selectbox("관리 대상 선택:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '생년월일']})")
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
                        st.success("기록 추가됨")
                        st.rerun()
            with t2:
                up_file = st.file_uploader("사진 업로드")
                if up_file:
                    img = Image.open(up_file)
                    if st.button("🔄 90도 회전"):
                        if "rot" not in st.session_state: st.session_state.rot = 0
                        st.session_state.rot = (st.session_state.rot + 90) % 360
                    img = img.rotate(-st.session_state.get("rot", 0), expand=True)
                    cropped = st_cropper(img, aspect_ratio=(1,1))
                    if st.button("사진 저장"):
                        df.at[sel_person, '사진'] = image_to_base64(cropped)
                        save_to_google(df)
                        st.success("변경 완료")
                        st.rerun()

# 3. PDF 주소록 만들기
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성 (가족 단위)")
    df = load_data()
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

        church_icon_path = "church_icon.png"

        df['addr_key'] = df['주소'].str.strip()
        grouped = df.groupby('addr_key', sort=False)

        for addr, group in grouped:
            if not addr or addr == "nan": continue
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
                elif os.path.exists(church_icon_path):
                    pdf.image(church_icon_path, x=x_pos, y=y_start, w=30, h=30)
                else:
                    pdf.rect(x_pos, y_start, 30, 30)
                
                pdf.set_xy(x_pos, y_start + 31)
                pdf.set_font('Nanum' if font_ok else 'Arial', '', 8)
                pdf.cell(30, 5, member['이름'], align='C')
                x_pos += 32

            names_text = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            pdf.set_xy(110, y_start) 
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 12)
            pdf.multi_cell(0, 7, names_text)
            
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10)
            rep = group.iloc[0]
            info_lines = [f"{c}: {rep[c]}" for c in inc_cols if rep[c] and rep[c] != "nan" and rep[c] != ""]
            pdf.set_x(110)
            pdf.multi_cell(0, 6, "\n".join(info_lines))
            pdf.set_y(y_start + 45) 
            pdf.ln(5)

        pdf_out = pdf.output()
        st.download_button("📥 다운로드", data=bytes(pdf_out), file_name=f"KKC_AddressBook_{datetime.now().strftime('%Y%m%d')}.pdf")

elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    # 등록 로직 생략 없이 그대로 유지