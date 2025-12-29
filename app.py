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
st.title("⛪ 킹스턴한인교회 교적부 (v2.2.1)")

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
            st.error("⚠️ 구글 서버 접속 지연. 1분 후 새로고침 해주세요.")
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
            if '이름' in df.columns:
                df = df[~df['이름'].str.replace(' ', '').isin(['이름', 'Name', '번호'])]
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
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. PDF 주소록 만들기", "4. (관리자용) PDF 초기화"])

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

        # 첫 화면에서 사진이 보이도록 ImageColumn 설정
        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "직분": st.column_config.SelectboxColumn("직분", options=["목사", "전도사", "장로", "권사", "집사", "성도", "청년"]),
                "상태": st.column_config.SelectboxColumn("상태", options=status_opts)
            },
            use_container_width=True, 
            key="v2.2.1_editor"
        )
        if st.button("💾 정보 저장하기", type="primary"):
            df.update(edited_df)
            save_to_google(df)
            st.success("저장되었습니다!")
            st.rerun()

        st.divider()
        if not results.empty:
            sel_person = st.selectbox("관리 대상 선택:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '생년월일']})")
            t1, t2 = st.tabs(["✍️ 심방 기록", "📷 사진 변경/회전"])
            with t1:
                st.text_area("기존 기록", value=df.loc[sel_person, '심방기록'], height=100, disabled=True)
                with st.form("v_form"):
                    v_text = st.text_area("새 내용")
                    if st.form_submit_button("기록 저장"):
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
                    if "rot" not in st.session_state: st.session_state.rot = 0
                    if st.button("🔄 90도 회전"):
                        st.session_state.rot = (st.session_state.rot + 90) % 360
                    img = img.rotate(-st.session_state.rot, expand=True)
                    cropped = st_cropper(img, aspect_ratio=(1,1))
                    if st.button("사진 저장"):
                        df.at[sel_person, '사진'] = image_to_base64(cropped)
                        save_to_google(df)
                        st.session_state.rot = 0
                        st.success("사진 변경 완료!")
                        st.rerun()

# 2. 새가족 등록
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    with st.form("new_fam"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ["성도", "청년", "집사", "권사", "장로", "목사"])
            status = st.selectbox("상태", ["새가족", "출석 중"])
            phone = st.text_input("전화번호")
        with c2:
            birth = st.text_input("생년월일 (8자리)", placeholder="19900101")
            addr = st.text_input("주소")
            biz_addr = st.text_input("비즈니스 주소")
            child = st.text_input("자녀")
        if st.form_submit_button("등록하기"):
            if not name: st.error("이름을 입력해주세요.")
            else:
                if len(birth) == 8: birth = f"{birth[:4]}-{birth[4:6]}-{birth[6:]}"
                df_curr = load_data()
                new_row = pd.DataFrame([["", name, role, status, phone, birth, addr, biz_addr, child, ""]], columns=df_curr.columns)
                save_to_google(pd.concat([df_curr, new_row], ignore_index=True))
                st.success("등록 완료!")

# 3. PDF 주소록 만들기
elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성 (가족 단위 정렬)")
    df = load_data()
    inc_cols = st.multiselect(
        "포함 정보 선택", 
        options=["자녀", "전화번호", "주소", "비즈니스 주소", "생년월일"], 
        default=["자녀", "전화번호", "주소", "비즈니스 주소"]
    )
    
    if st.button("📄 한글 PDF 생성"):
        pdf = FPDF()
        try:
            pdf.add_font('Nanum', '', 'NanumGothic.ttc')
            pdf.set_font('Nanum', '', 12)
            font_ok = True
        except:
            pdf.set_font("Arial", 'B', 12)
            font_ok = False
            
        pdf.add_page()
        pdf.set_font('Nanum' if font_ok else 'Arial', 'B', 16)
        pdf.cell(0, 10, "KKC Member Address Book", ln=True, align='C')
        pdf.ln(5)

        # 주소 기준으로 가족 그룹화
        df['주소_key'] = df['주소'].str.strip()
        grouped = df.groupby('주소_key', sort=False)

        for addr, group in grouped:
            # 이름 직분 형식 수정 (괄호 제거 및 dash 제거)
            names_roles = " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()])
            rep = group.iloc[0] 
            
            y = pdf.get_y()
            if y > 230: pdf.add_page(); y = pdf.get_y()
            
            # 사진 출력 로직 (base64.b64decode 오타 수정 완료)
            if rep['사진'] and "base64," in rep['사진']:
                try:
                    img_b64 = rep['사진'].split(",")[1]
                    img_data = base64.b64decode(img_b64)
                    pdf.image(Image.open(io.BytesIO(img_data)), x=10, y=y, w=35, h=35)
                except: pdf.rect(10, y, 35, 35)
            else: pdf.rect(10, y, 35, 35)
            
            pdf.set_xy(50, y)
            pdf.set_font('Nanum' if font_ok else 'Arial', 'B', 12)
            pdf.cell(0, 8, names_roles, ln=True)
            
            pdf.set_font('Nanum' if font_ok else 'Arial', '', 10)
            pdf.set_x(50)
            
            # 항목 리스트 (대시 없이 깔끔하게)
            info_list = []
            for col in inc_cols:
                val = rep[col]
                if val and val != "nan" and val != "":
                    info_list.append(f"{col}: {val}")
            
            pdf.multi_cell(0, 6, "\n".join(info_list))
            pdf.ln(12)

        date_str = datetime.now().strftime('%Y%m%d')
        pdf_out = pdf.output() 
        st.download_button("📥 PDF 다운로드", data=bytes(pdf_out), file_name=f"KKC_AddressBook_{date_str}.pdf", mime="application/pdf")

# 4. 관리자용 PDF 초기화
elif menu == "4. (관리자용) PDF 초기화":
    st.header("⚠️ 데이터 초기화")
    up_pdf = st.file_uploader("PDF 업로드", type="pdf")
    if up_pdf and st.button("실행"):
        with st.spinner('변환 중...'):
            with pdfplumber.open(up_pdf) as pdf_p:
                all_data = []
                for page in pdf_p.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or row[1] is None: continue
                            try:
                                name = row[1].replace('\n', ' ')
                                if name.replace(' ', '') in ["이름", "Name", "번호"]: continue
                                role = row[2].replace('\n', ' ') if row[2] else ""
                                all_data.append({
                                    "사진": "", "이름": name, "직분": role, "상태": "출석 중", 
                                    "전화번호": row[5] if len(row)>5 else "", 
                                    "생년월일": "", "주소": row[3] if len(row)>3 else "", 
                                    "비즈니스 주소": "", "자녀": row[6] if len(row)>6 else "", "심방기록": ""
                                })
                            except: continue
                save_to_google(pd.DataFrame(all_data))
            st.success("데이터가 초기화되었습니다!")
            st.rerun()