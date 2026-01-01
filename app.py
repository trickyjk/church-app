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
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

# --- 1. 설정 및 데이터 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v10.0")

# --- 2. 유틸리티 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def format_phone(val):
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return ""
    nums = "".join(filter(str.isdigit, str(val)))
    if len(nums) == 10: return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    elif len(nums) == 11: return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return val

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
    # [생년월일 보호] 모든 데이터 문자열 변환 및 필수 컬럼 확인
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null'], '')
    required_cols = ["사진", "이름", "직분", "생년월일", "전화번호", "가족", "상태", "이메일", "주소", "신급", "등록신청일", "등록일", "심방기록", "사역이력"]
    for col in required_cols:
        if col not in df.columns: df[col] = ""
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

ROLE_OPTIONS = ["목사", "장로", "전도사", "시무권사", "협동목사", "협동장로", "협동권사", "협동안수집사", "은퇴장로", "은퇴권사", "은퇴협동권사", "집사", "청년", "성도"]
FAITH_OPTIONS = ["유아세례", "아동세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 3. 상세 정보 수정 팝업 ---
@st.dialog("성도 상세 정보")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 및 회전"])
    
    with tab1:
        with st.form("pop_edit_v10"):
            if m_info['사진']: st.image(m_info['사진'], width=150)
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else 13)
                u_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(m_info['신급']) if m_info['신급'] in FAITH_OPTIONS else 4)
                # 생년월일 입력 가이드 강화
                u_birth = st.text_input("생년월일 (yyyy-mm-dd)", value=str(m_info['생년월일']), placeholder="예: 1980-05-01")
            with c2:
                u_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS else 0)
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_family = st.text_input("가족 관계", value=str(m_info['가족']))
            u_history = st.text_area("사역 이력", value=str(m_info['사역이력']))
            st.info(f"**심방기록:**\n{m_info['심방기록']}")
            new_note = st.text_area("새로운 기록 추가")
            
            if st.form_submit_button("✅ 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'], full_df.at[idx, '직분'] = u_name, u_role
                full_df.at[idx, '신급'], full_df.at[idx, '생년월일'] = u_faith, u_birth
                full_df.at[idx, '상태'], full_df.at[idx, '전화번호'] = u_status, format_phone(u_phone)
                full_df.at[idx, '이메일'], full_df.at[idx, '주소'] = u_email, u_addr
                full_df.at[idx, '가족'], full_df.at[idx, '사역이력'] = u_family, u_history
                if new_note.strip():
                    full_df.at[idx, '심방기록'] = f"{m_info['심방기록']}\n[{date.today()}] {new_note.strip()}" if m_info['심방기록'] else f"[{date.today()}] {new_note.strip()}"
                save_to_google(full_df)
                st.success("저장되었습니다."); st.rerun()

    with tab2:
        img_file = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'])
        if img_file:
            img = Image.open(img_file)
            rot = st.slider("사진 회전", 0, 270, 0, step=90)
            img = img.rotate(-rot, expand=True)
            cropped = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📸 사진 확정"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = image_to_base64(cropped)
                save_to_google(full_df)
                st.success("사진이 변경되었습니다."); st.rerun()

# --- 4. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부")
menu = st.sidebar.radio("메뉴", ["성도 관리", "신규 등록", "PDF 주소록 생성"])

if menu == "성도 관리":
    df = load_data()
    if not df.empty:
        c1, c2 = st.columns([1, 2])
        with c1: search_name = st.text_input("🔍 이름 검색")
        with c2: sel_status = st.multiselect("📍 상태 필터", STATUS_OPTIONS, default=["출석 중"])
        
        f_df = df.copy()
        if search_name: f_df = f_df[f_df['이름'].str.contains(search_name)]
        if sel_status: f_df = f_df[f_df['상태'].isin(sel_status)]

        # [수정] 썸네일 표시 및 에러 방지용 ID 컬럼 확인
        thumbnail_js = JsCode("""
        function(params) {
            if (params.value && params.value.startsWith('data:image')) {
                return '<img src="' + params.value + '" style="width:35px;height:35px;border-radius:50%;">';
            } return 'N/A';
        }
        """)

        gb = GridOptionsBuilder.from_dataframe(f_df[["사진", "이름", "직분", "생년월일", "전화번호", "가족", "상태", "id"]])
        gb.configure_column("사진", headerName="🖼️", cellRenderer=thumbnail_js, width=70)
        gb.configure_column("이름", editable=True, pinned='left', width=100)
        # 생년월일 더블클릭 수정 가이드
        gb.configure_column("생년월일", editable=True, headerName="생년월일(yyyy-mm-dd)")
        gb.configure_column("id", hide=True)
        gb.configure_selection('single', use_checkbox=True)
        grid_opts = gb.build()

        responses = AgGrid(f_df, gridOptions=grid_opts, theme='balham', height=500, update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED, allow_unsafe_jscode=True)

        if st.button("💾 표의 수정 내용 저장"):
            save_to_google(responses['data'])
            st.success("저장되었습니다."); st.rerun()

        selected = responses.get('selected_rows')
        if selected is not None:
            if isinstance(selected, pd.DataFrame) and not selected.empty:
                edit_member_dialog(int(selected.iloc[0]['id']), df)
            elif isinstance(selected, list) and len(selected) > 0:
                edit_member_dialog(int(selected[0]['id']), df)

elif menu == "신규 등록":
    st.header("📝 모든 항목 포함 신규 등록")
    with st.form("full_reg_form"):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("성함 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=13)
            n_faith = st.selectbox("신급", FAITH_OPTIONS, index=4)
            n_birth = st.text_input("생년월일 (yyyy-mm-dd)", placeholder="예: 1980-05-01")
        with c2:
            n_phone = st.text_input("전화번호")
            n_email = st.text_input("이메일")
            n_req_date = st.date_input("등록 신청일", value=date.today())
            n_reg_date = st.date_input("등록일", value=date.today())
        
        n_family = st.text_input("가족 구성")
        n_addr = st.text_input("주소")
        n_history = st.text_area("사역 이력")
        n_note = st.text_area("최초 목양 기록")
        
        if st.form_submit_button("➕ 교적부 최종 등록"):
            if n_name:
                df_curr = load_data()
                new_row = {col: "" for col in df_curr.columns if col != 'id'}
                new_row.update({
                    "이름": n_name, "직분": n_role, "신급": n_faith, "생년월일": n_birth,
                    "전화번호": format_phone(n_phone), "이메일": n_email, "가족": n_family, "주소": n_addr,
                    "등록신청일": str(n_req_date), "등록일": str(n_reg_date), "사역이력": n_history,
                    "심방기록": f"[{date.today()}] 등록기록: {n_note}", "상태": "출석 중"
                })
                save_to_google(pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True))
                st.success(f"{n_name} 성도님 등록 완료!"); st.rerun()

elif menu == "PDF 주소록 생성":
    st.header("🖨️ 주소록 PDF 출력 (사진/가족 포함)")
    df = load_data()
    p_status = st.multiselect("출력 대상 상태", STATUS_OPTIONS, default=["출석 중"])
    p_cols = st.multiselect("출력할 정보 선택", ["직분", "생년월일", "전화번호", "주소", "가족", "이메일"], default=["직분", "전화번호", "가족"])
    
    if st.button("📄 PDF 생성"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 15, "Kingston Korean Church Directory", ln=True, align='C')
        pdf.ln(5)
        
        p_df = df[df['상태'].isin(p_status)]
        for _, r in p_df.iterrows():
            y_start = pdf.get_y()
            # [사진 출력]
            if r['사진'] and r['사진'].startswith('data:image'):
                img_data = base64.b64decode(r['사진'].split(',')[1])
                img_file = io.BytesIO(img_data)
                pdf.image(img_file, x=10, y=y_start, w=25, h=25)
            else:
                try: pdf.image("church_icon.png", x=10, y=y_start, w=25, h=25)
                except: pdf.rect(10, y_start, 25, 25)
            
            pdf.set_left_margin(40)
            pdf.set_font("Arial", 'B', 12)
            # 이름 강제 인코딩 (한글 대신 영어 이름 권장하거나 폰트 설정 필요)
            name_text = f"{r['이름']} ({r['직분'] if '직분' in p_cols else ''})"
            pdf.cell(0, 8, name_text.encode('latin-1', 'ignore').decode('latin-1'), ln=True)
            
            pdf.set_font("Arial", '', 10)
            details = []
            if "전화번호" in p_cols: details.append(f"Tel: {r['전화번호']}")
            if "가족" in p_cols: details.append(f"Family: {r['가족']}")
            if "생년월일" in p_cols: details.append(f"Birth: {r['생년월일']}")
            pdf.cell(0, 6, " | ".join(details).encode('latin-1', 'ignore').decode('latin-1'), ln=True)
            
            if "주소" in p_cols:
                pdf.cell(0, 6, f"Addr: {r['주소']}".encode('latin-1', 'ignore').decode('latin-1'), ln=True)
            
            pdf.set_left_margin(10)
            pdf.ln(12)
            
        st.download_button("📥 PDF 다운로드", data=bytes(pdf.output()), file_name="Church_Directory.pdf")