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
    # PNG 등 투명도가 있는 이미지 모드를 JPEG용 RGB로 변환
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
        save_df['생년월일'] = save_df['생년월일'].apply(lambda x: str(x) if x else "")
        save_df = save_df.fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# 직분 리스트 정의
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

        # 표 설정: 생년월일 연도 4자리 입력 유도
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
                    max_value=date(2100, 12, 31)
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
            # "대상 선택"으로 명칭 변경 및 이름(직분) 표시
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
            birth = st.date_input("생년월일", value=date(1980, 1, 1))
            addr = st.text_input("주소")
        if st.form_submit_button("등록"):
            df_curr = load_data()
            new_row = pd.DataFrame([[ "", name, role, status, phone, str(birth), addr, "", "", ""]], columns=df_curr.columns)
            save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
            st.success("등록 완료")

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

        # 흑백 교회 아이콘 파일 경로
        church_icon_path = "church_icon.png"
        df['addr_key'] = df['주소'].str.strip()
        grouped = df.groupby('addr_key', sort=False)

        for addr, group in grouped:
            if not addr or addr == "nan": continue
            y_start = pdf.get_y()
            if y_start > 230: pdf.add_page(); y_start = pdf.get_y()
            
            x_pos = 10
            # 가족 사진 나란히 배치
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

            # 정보 출력
            names_text = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            pdf.set_xy(110, y_start) 
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 12)
            pdf.multi_cell(0, 7, names_text)
            
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10)
            rep = group.iloc[0]
            info_lines = [f"{c}: {rep[c]}" for c in inc_cols if rep[c] and str(rep[c]) not in ["nan", "None", ""]]
            
            pdf.set_x(110)
            pdf.multi_cell(0, 6, "\n".join(info_lines))
            pdf.set_y(y_start + 45) 
            pdf.ln(5)

        pdf_out = pdf.output()
        st.download_button("📥 다운로드", data=bytes(pdf_out), file_name=f"KKC_AddressBook_{datetime.now().strftime('%Y%m%d')}.pdf")