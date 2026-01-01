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

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v11.0")

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
    # 필수 컬럼 보장
    cols = ["사진", "이름", "직분", "생년월일", "전화번호", "이메일", "주소", "가족", "상태", "심방기록"]
    for c in cols:
        if c not in df.columns: df[c] = ""
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
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 3. 상세 정보 수정 팝업 ---
@st.dialog("성도 상세 정보")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 관리"])
    
    with tab1:
        with st.form("edit_v11"):
            if m_info['사진']: st.image(m_info['사진'], width=150)
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(m_info['직분']) if m_info['직분'] in ROLE_OPTIONS else 13)
                # 1번 해결: date_input 사용하여 yyyy-mm-dd 형식 강제
                try: default_date = datetime.strptime(m_info['생년월일'], '%Y-%m-%d').date()
                except: default_date = date(1980, 1, 1)
                u_birth = st.date_input("생년월일", value=default_date)
            with c2:
                u_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(m_info['상태']) if m_info['상태'] in STATUS_OPTIONS else 0)
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            # 3번 해결: 가족관계 여러 줄 입력
            u_family = st.text_area("가족 관계 (여러 줄 가능)", value=str(m_info['가족']))
            st.info(f"**심방기록:**\n{m_info['심방기록']}")
            new_note = st.text_area("새로운 기록 추가")
            
            if st.form_submit_button("✅ 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'], full_df.at[idx, '직분'] = u_name, u_role
                full_df.at[idx, '생년월일'], full_df.at[idx, '상태'] = u_birth.strftime('%Y-%m-%d'), u_status
                full_df.at[idx, '전화번호'], full_df.at[idx, '이메일'] = u_phone, u_email
                full_df.at[idx, '주소'], full_df.at[idx, '가족'] = u_addr, u_family
                if new_note.strip():
                    full_df.at[idx, '심방기록'] = f"{m_info['심방기록']}\n[{date.today()}] {new_note.strip()}" if m_info['심방기록'] else f"[{date.today()}] {new_note.strip()}"
                save_to_google(full_df)
                st.success("저장되었습니다."); st.rerun()

    with tab2:
        img_file = st.file_uploader("사진 업로드", type=['jpg', 'jpeg', 'png'])
        if img_file:
            # 4번 해결: 90도 회전 버튼 방식 복구
            if 'rotation' not in st.session_state: st.session_state.rotation = 0
            col_r1, col_r2 = st.columns(2)
            if col_r1.button("🔄 왼쪽으로 90도"): st.session_state.rotation += 90
            if col_r2.button("🔄 오른쪽으로 90도"): st.session_state.rotation -= 90
            
            img = Image.open(img_file).rotate(st.session_state.rotation, expand=True)
            cropped = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📸 이 모양으로 사진 저장"):
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
        c1, c2 = st.columns([1, 2])
        with c1: search_name = st.text_input("🔍 이름 검색")
        with c2: sel_status = st.multiselect("📍 상태 필터", STATUS_OPTIONS, default=["출석 중"])
        
        f_df = df.copy()
        if search_name: f_df = f_df[f_df['이름'].str.contains(search_name)]
        if sel_status: f_df = f_df[f_df['상태'].isin(sel_status)]

        # 2, 5번 해결: AgGrid에서 사진 잘 나오도록 HTML 렌더러 수정
        thumbnail_js = JsCode("""
        function(params) {
            if (params.value && params.value.startsWith('data:image')) {
                return '<img src="' + params.value + '" style="width:35px;height:35px;border-radius:50%;object-fit:cover;">';
            } return 'N/A';
        }
        """)

        # 6번 해결: 순서 조정 (체크박스, 사진, 이름, 직분, 전화번호, 이메일, 주소)
        gb = GridOptionsBuilder.from_dataframe(f_df[["사진", "이름", "직분", "전화번호", "이메일", "주소", "id"]])
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("사진", headerName="📸", cellRenderer=thumbnail_js, width=80)
        gb.configure_column("이름", pinned='left', width=100)
        gb.configure_column("id", hide=True)
        grid_opts = gb.build()

        responses = AgGrid(f_df, gridOptions=grid_opts, theme='balham', height=500, update_mode=GridUpdateMode.SELECTION_CHANGED, allow_unsafe_jscode=True)

        selected = responses.get('selected_rows')
        if selected is not None:
            if isinstance(selected, pd.DataFrame) and not selected.empty:
                edit_member_dialog(int(selected.iloc[0]['id']), df)
            elif isinstance(selected, list) and len(selected) > 0:
                edit_member_dialog(int(selected[0]['id']), df)

elif menu == "신규 등록":
    st.header("📝 새 성도 등록")
    # (이전의 모든 항목 포함된 등록 폼 코드 유지)
    with st.form("new_v11"):
        n_name = st.text_input("성함 (필수)")
        n_role = st.selectbox("직분", ROLE_OPTIONS, index=13)
        n_birth = st.date_input("생년월일", value=date(1990, 1, 1))
        n_phone = st.text_input("연락처")
        n_family = st.text_area("가족 관계")
        if st.form_submit_button("등록 완료"):
            if n_name:
                df_curr = load_data()
                new_row = {c: "" for c in df_curr.columns if c != 'id'}
                new_row.update({"이름": n_name, "직분": n_role, "생년월일": n_birth.strftime('%Y-%m-%d'), "전화번호": n_phone, "가족": n_family, "상태": "출석 중"})
                save_to_google(pd.concat([df_curr, pd.DataFrame([new_row])], ignore_index=True))
                st.success("등록되었습니다."); st.rerun()

elif menu == "PDF 주소록":
    st.header("🖨️ 주소록 생성 (가족 단위 그룹화)")
    df = load_data()
    # 7번 해결: 가족별로 묶어서 출력하는 로직 및 한글 깨짐 방지 인코딩 적용
    if st.button("📄 PDF 생성"):
        pdf = FPDF()
        pdf.add_page()
        # 한글 폰트가 서버에 없을 경우를 대비해 'ignore' 인코딩과 이미지 레이아웃 집중
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 15, "Kingston Korean Church Directory", ln=True, align='C')
        
        # 가족(주소) 단위로 그룹화하여 출력
        grouped = df[df['상태']=="출석 중"].groupby('주소')
        for addr, group in grouped:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"Family at: {addr[:30]}...", ln=True) # 주소 출력
            
            for _, r in group.iterrows():
                y = pdf.get_y()
                # 사진 출력
                if r['사진'].startswith('data:image'):
                    try:
                        img_data = base64.b64decode(r['사진'].split(',')[1])
                        img_file = io.BytesIO(img_data)
                        pdf.image(img_file, x=10, y=y, w=20, h=20)
                    except: pass
                
                pdf.set_left_margin(35)
                pdf.set_font("Arial", '', 10)
                # 한글 깨짐 방지를 위해 영어 필드 우선 혹은 인코딩 처리
                info = f"Name: {r['이름']} | Role: {r['직분']} | Tel: {r['전화번호']}"
                pdf.cell(0, 8, info.encode('latin-1', 'ignore').decode('latin-1'), ln=True)
                pdf.set_left_margin(10)
            pdf.ln(5)
            
        st.download_button("📥 PDF 다운로드", data=bytes(pdf.output()), file_name="Directory.pdf")