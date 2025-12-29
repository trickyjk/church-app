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
import pdfplumber

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v2.6)")

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
            st.error("⚠️ 접속 과부하. 1분 후 새로고침 해주세요.")
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

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기"])

# 직분 리스트 정의 (요청하신 순서)
ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]

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

        # 메인 화면 표 설정
        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=ROLE_OPTIONS),
                "상태": st.column_config.SelectboxColumn("상태", options=status_opts)
            },
            use_container_width=True,
            key="v2.6_editor"
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

# 2. 새가족 등록
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    with st.form("new_fam"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ROLE_OPTIONS)
            status = st.selectbox("상태", ["새가족", "출석 중"])
        with c2:
            phone = st.text_input("전화번호")
            addr = st.text_input("주소")
            biz = st.text_input("비즈니스 주소")
        if st.form_submit_button("등록"):
            df_curr = load_data()
            new_row = pd.DataFrame([["", name, role, status, phone, "", addr, biz, "", ""]], columns=df_curr.columns)
            save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
            st.success("등록 완료")

# 3. PDF 주소록 만들기
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성 (가족 단위)")
    df = load_data()
    inc_cols = st.multiselect("포함 정보", options=["자녀", "전화번호", "주소", "비즈니스 주소"], default=["자녀", "전화번호", "주소", "비즈니스 주소"])
    
    if st.button("📄 한글 PDF 생성"):
        pdf = FPDF()
        try:
            # [파일명 교정] 목사님이 올리신 NanumGothic-Regular.ttf 사용
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf') 
            pdf.set_font('Nanum', '', 12)
            font_ok = True
        except Exception as e:
            st.warning(f"폰트 인식 실패(영문 출력): {e}")
            pdf.set_font("Arial", '', 12)
            font_ok = False
            
        pdf.add_page()
        pdf.set_font('Nanum' if font_ok else 'Arial', '', 16)
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C')
        pdf.ln(5)

        df['addr_key'] = df['주소'].str.strip()
        for addr, group in df.groupby('addr_key', sort=False):
            # 괄호 제거 및 김금옥 협동권사 형식
            names = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            rep = group.iloc[0]
            y = pdf.get_y()
            if y > 240: pdf.add_page(); y = pdf.get_y()
            
            # 사진 
            if rep['사진'] and "base64," in rep['사진']:
                try:
                    img_data = base64.b64decode(rep['사진'].split(",")[1])
                    pdf.image(Image.open(io.BytesIO(img_data)), x=10, y=y, w=35, h=35)
                except: pdf.rect(10, y, 35, 35)
            else: pdf.rect(10, y, 35, 35)
            
            pdf.set_xy(50, y)
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 12) # 에러 방지를 위해 Bold 제거
            pdf.cell(0, 8, names, ln=True)
            
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10)
            pdf.set_x(50)
            details = "\n".join([f"{c}: {rep[c]}" for c in inc_cols if rep[c] and rep[c] != "nan" and rep[c] != ""])
            pdf.multi_cell(0, 6, details)
            pdf.ln(12)

        pdf_bytes = pdf.output()
        st.download_button("📥 PDF 다운로드", data=bytes(pdf_bytes), file_name=f"KKC_AddressBook_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")