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

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v14.0")

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
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null', ''], ' ')
    df['id'] = range(1, len(df) + 1)
    return df

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        if 'id' in save_df.columns: save_df = save_df.drop(columns=['id'])
        save_df = save_df.fillna(" ")
        sheet.clear()
        sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())

def image_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

# --- 2. 상세 정보 수정 팝업 ---
@st.dialog("성도 상세 정보")
def edit_member_dialog(member_id, full_df):
    m_info = full_df[full_df['id'] == member_id].iloc[0]
    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 관리"])
    
    with tab1:
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                u_role = st.selectbox("직분", ["목사", "장로", "전도사", "권사", "집사", "성도", "청년"], 
                                    index=["목사", "장로", "전도사", "권사", "집사", "성도", "청년"].index(m_info['직분']) if m_info['직분'] in ["목사", "장로", "전도사", "권사", "집사", "성도", "청년"] else 5)
                try: def_date = datetime.strptime(m_info['생년월일'], '%Y-%m-%d').date()
                except: def_date = date(1970, 1, 1)
                u_birth = st.date_input("생년월일", value=def_date, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            with c2:
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_family = st.text_area("가족 관계", value=str(m_info['가족']))
            u_status = st.selectbox("상태", ["출석 중", "장기결석", "타지역", "기타"], 
                                  index=["출석 중", "장기결석", "타지역", "기타"].index(m_info['상태']) if m_info['상태'] in ["출석 중", "장기결석", "타지역", "기타"] else 0)
            
            if st.form_submit_button("✅ 수정 내용 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '이름'] = u_name
                full_df.at[idx, '직분'] = u_role
                full_df.at[idx, '생년월일'] = u_birth.strftime('%Y-%m-%d')
                full_df.at[idx, '전화번호'] = u_phone
                full_df.at[idx, '이메일'] = u_email
                full_df.at[idx, '주소'] = u_addr
                full_df.at[idx, '가족'] = u_family
                full_df.at[idx, '상태'] = u_status
                save_to_google(full_df)
                st.success("정보가 업데이트되었습니다."); st.rerun()

    with tab2:
        img_file = st.file_uploader("새 사진 업로드", type=['jpg', 'jpeg', 'png'])
        if img_file:
            if 'rot' not in st.session_state: st.session_state.rot = 0
            rc1, rc2 = st.columns(2)
            if rc1.button("🔄 왼쪽 90도"): st.session_state.rot += 90
            if rc2.button("🔄 오른쪽 90도"): st.session_state.rot -= 90
            img = Image.open(img_file).rotate(st.session_state.rot, expand=True)
            cropped = st_cropper(img, aspect_ratio=(1, 1))
            if st.button("📸 이 사진으로 확정 저장"):
                idx = full_df[full_df['id'] == member_id].index[0]
                full_df.at[idx, '사진'] = image_to_base64(cropped)
                save_to_google(full_df)
                st.session_state.rot = 0
                st.success("사진 저장 완료!"); st.rerun()

# --- 3. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부")
menu = st.sidebar.radio("메뉴", ["성도 관리", "신규 등록", "PDF 주소록 생성"])

if menu == "성도 관리":
    df = load_data()
    if not df.empty:
        search = st.text_input("🔍 성함으로 검색")
        f_df = df[df['이름'].str.contains(search)] if search else df.copy()

        # [1, 2번 해결] 사진 표시 및 체크박스 활성화 코드
        thumbnail_js = JsCode("""
        function(params) {
            if (params.value && params.value.includes('base64')) {
                return '<img src="' + params.value + '" style="width:40px;height:40px;border-radius:50%;">';
            } return ' ';
        }
        """)

        gb = GridOptionsBuilder.from_dataframe(f_df[["id", "사진", "이름", "직분", "전화번호", "주소"]])
        gb.configure_selection('single', use_checkbox=True) # [1번 해결] 체크박스 활성화
        gb.configure_column("id", hide=True)
        gb.configure_column("사진", headerName="📸", cellRenderer=thumbnail_js, width=80) # [2번 해결] 사진 표시
        gb.configure_column("이름", pinned='left', width=100)
        
        grid_opts = gb.build()
        grid_opts['rowHeight'] = 50

        responses = AgGrid(f_df, gridOptions=grid_opts, 
                           update_mode=GridUpdateMode.SELECTION_CHANGED,
                           data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                           allow_unsafe_jscode=True,
                           theme='balham',
                           fit_columns_on_grid_load=True)

        selected = responses.get('selected_rows')
        if selected is not None and not selected.empty:
            member_id = int(selected.iloc[0]['id'])
            edit_member_dialog(member_id, df)

elif menu == "신규 등록":
    # [3번 해결] 신규 등록 입력 사항 확장
    st.header("📝 새 성도님 등록")
    with st.form("new_member_form"):
        st.info("성도 상세 정보 팝업창과 동일한 항목을 입력하실 수 있습니다.")
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("성함 (필수)")
            n_role = st.selectbox("직분", ["목사", "장로", "전도사", "권사", "집사", "성도", "청년"], index=5)
            n_birth = st.date_input("생년월일", value=date(1980, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            n_status = st.selectbox("상태", ["출석 중", "장기결석", "타지역"], index=0)
        with c2:
            n_phone = st.text_input("연락처")
            n_email = st.text_input("이메일")
            n_addr = st.text_input("주소 (동일 주소는 가족으로 묶입니다)")
        
        n_family = st.text_area("가족 관계 및 메모")
        
        if st.form_submit_button("🆕 교적부에 추가 등록"):
            if n_name:
                df_curr = load_data()
                new_data = {
                    "이름": n_name, "직분": n_role, "생년월일": n_birth.strftime('%Y-%m-%d'),
                    "전화번호": n_phone, "이메일": n_email, "주소": n_addr, 
                    "가족": n_family, "상태": n_status, "사진": " "
                }
                save_to_google(pd.concat([df_curr, pd.DataFrame([new_data])], ignore_index=True))
                st.success(f"{n_name} 성도님이 등록되었습니다."); st.rerun()
            else:
                st.error("성함은 필수 입력 항목입니다.")

elif menu == "PDF 주소록 생성":
    # [4번 해결] 캡처 화면 레이아웃 반영 PDF 생성
    st.header("🖨️ PDF 주소록 제작 (가족별 그룹화)")
    df = load_data()
    
    col_a, col_b = st.columns(2)
    with col_a:
        sel_status = st.multiselect("출력 대상", ["출석 중", "장기결석", "타지역"], default=["출석 중"])
    with col_b:
        sel_info = st.multiselect("포함할 정보", ["직분", "생년월일", "전화번호", "이메일", "가족"], default=["직분", "전화번호", "가족"])

    if st.button("📄 주소록 PDF 다운로드 준비"):
        # 폰트 로드
        f_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        font_res = requests.get(f_url)
        with open("NanumGothic.ttf", "wb") as f: f.write(font_res.content)

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("Nanum", "", "NanumGothic.ttf", uni=True)
        pdf.set_font("Nanum", "", 18)
        pdf.cell(0, 15, "⛪ 킹스턴 한인교회 주소록", ln=True, align='C')
        pdf.ln(5)

        # 주소지 기준 정렬 및 그룹화
        p_df = df[df['상태'].isin(sel_status)].sort_values(by=['주소', '이름'])
        grouped = p_df.groupby('주소')

        for addr, group in grouped:
            # 가족 주소 헤더 (캡처 화면처럼 구분선 역할)
            pdf.set_font("Nanum", "", 11)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(0, 8, f" 📍 주소: {addr if addr.strip() else '주소 미입력'}", ln=True, fill=True)
            pdf.ln(2)

            for _, r in group.iterrows():
                y_start = pdf.get_y()
                # 1. 사진 배치
                if len(r['사진']) > 100:
                    try:
                        img_bin = base64.b64decode(r['사진'].split(',')[1])
                        pdf.image(io.BytesIO(img_bin), x=12, y=y_start, w=18, h=18)
                    except: pass
                
                # 2. 정보 배치 (캡처 화면 레이아웃)
                pdf.set_left_margin(35)
                pdf.set_font("Nanum", "", 12)
                name_str = r['이름']
                if "직분" in sel_info: name_str += f" {r['직분']}"
                pdf.cell(0, 7, name_str, ln=True)
                
                pdf.set_font("Nanum", "", 10)
                detail_bits = []
                if "전화번호" in sel_info: detail_bits.append(f"📞 {r['전화번호']}")
                if "생년월일" in sel_info: detail_bits.append(f"🎂 {r['생년월일']}")
                if "이메일" in sel_info: detail_bits.append(f"📧 {r['이메일']}")
                pdf.cell(0, 6, "  ".join(detail_bits), ln=True)
                
                if "가족" in sel_info and r['가족'].strip():
                    pdf.set_font("Nanum", "", 9)
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(0, 5, f"👨‍👩‍👧‍👦 {r['가족']}", ln=True)
                    pdf.set_text_color(0, 0, 0)

                pdf.set_left_margin(10)
                pdf.ln(4)
            pdf.ln(4)

        st.download_button("📥 클릭하여 PDF 저장", data=bytes(pdf.output()), file_name=f"교적부_{date.today()}.pdf")