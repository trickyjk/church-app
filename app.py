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
import uuid
import os

# --- 1. 설정 및 데이터 연결 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v14.1")

@st.cache_resource
def get_font():
    """PDF 생성용 폰트 다운로드 및 캐싱 (속도 개선)"""
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        f_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        try:
            response = requests.get(f_url)
            with open(font_path, "wb") as f:
                f.write(response.content)
        except Exception as e:
            st.error(f"폰트 다운로드 실패: {e}")
            return None
    return font_path

def get_sheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name(SECRET_FILE, SCOPE)
        return gspread.authorize(creds).open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        return None

def load_data():
    sheet = get_sheet()
    if not sheet: return pd.DataFrame()
    
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # 데이터가 비어있을 경우 빈 DataFrame 반환하되 컬럼 구조 유지
    if df.empty:
        return pd.DataFrame(columns=["id", "이름", "직분", "생년월일", "전화번호", "이메일", "주소", "가족", "상태", "사진"])

    # 결측치 처리
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null', ''], ' ')
    
    # [수정 1] 고유 ID(UUID) 관리: ID 컬럼이 없거나 비어있으면 생성
    if 'id' not in df.columns:
        df['id'] = [str(uuid.uuid4()) for _ in range(len(df))]
    else:
        # 혹시라도 id가 빈 문자열인 행이 있다면 채워줌
        df['id'] = df.apply(lambda x: str(uuid.uuid4()) if x['id'].strip() == '' else x['id'], axis=1)
        
    return df

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        # [수정 2] ID 컬럼을 삭제하지 않고 함께 저장 (데이터 무결성 핵심)
        save_df = save_df.fillna(" ")
        
        try:
            sheet.clear()
            # 헤더와 데이터를 함께 업데이트
            sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())
        except Exception as e:
            st.error(f"데이터 저장 중 오류 발생: {e}")

def image_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

# --- 2. 상세 정보 수정 팝업 ---
@st.dialog("성도 상세 정보")
def edit_member_dialog(member_id, full_df):
    # [수정 3] ID 매칭 로직 안전성 강화
    row = full_df[full_df['id'] == member_id]
    if row.empty:
        st.error("해당 성도 정보를 찾을 수 없습니다.")
        return
        
    m_info = row.iloc[0]
    idx = row.index[0]

    tab1, tab2 = st.tabs(["📄 정보 수정", "📸 사진 관리"])
    
    with tab1:
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                u_name = st.text_input("성함", value=str(m_info['이름']))
                role_opts = ["목사", "장로", "전도사", "권사", "집사", "성도", "청년"]
                u_role = st.selectbox("직분", role_opts, 
                                    index=role_opts.index(m_info['직분']) if m_info['직분'] in role_opts else 5)
                
                try: 
                    def_date = datetime.strptime(m_info['생년월일'], '%Y-%m-%d').date()
                except: 
                    def_date = date(1970, 1, 1)
                    
                u_birth = st.date_input("생년월일", value=def_date, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            with c2:
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_family = st.text_area("가족 관계", value=str(m_info['가족']))
            status_opts = ["출석 중", "장기결석", "타지역", "기타"]
            u_status = st.selectbox("상태", status_opts, 
                                  index=status_opts.index(m_info['상태']) if m_info['상태'] in status_opts else 0)
            
            if st.form_submit_button("✅ 수정 내용 저장"):
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
            
            try:
                img = Image.open(img_file).rotate(st.session_state.rot, expand=True)
                cropped = st_cropper(img, aspect_ratio=(1, 1))
                if st.button("📸 이 사진으로 확정 저장"):
                    full_df.at[idx, '사진'] = image_to_base64(cropped)
                    save_to_google(full_df)
                    st.session_state.rot = 0
                    st.success("사진 저장 완료!"); st.rerun()
            except Exception as e:
                st.error(f"이미지 처리 중 오류: {e}")

# --- 3. 메인 화면 ---
st.title("⛪ 킹스턴한인교회 통합 교적부 v14.1")
menu = st.sidebar.radio("메뉴", ["성도 관리", "신규 등록", "PDF 주소록 생성"])

if menu == "성도 관리":
    df = load_data()
    if not df.empty:
        search = st.text_input("🔍 성함으로 검색")
        f_df = df[df['이름'].str.contains(search)] if search else df.copy()

        thumbnail_js = JsCode("""
        function(params) {
            if (params.value && params.value.includes('base64')) {
                return '<img src="' + params.value + '" style="width:40px;height:40px;border-radius:50%;">';
            } return ' ';
        }
        """)

        # AgGrid 설정
        gb = GridOptionsBuilder.from_dataframe(f_df[["id", "사진", "이름", "직분", "전화번호", "주소"]])
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("id", hide=True) # ID는 숨김 처리
        gb.configure_column("사진", headerName="📸", cellRenderer=thumbnail_js, width=80)
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
        
        # [수정 4] AgGrid 선택 값 처리 안전장치 (버그 수정 핵심)
        if selected is not None:
            selected_id = None
            
            # Case A: 리스트 형태 (딕셔너리 리스트)
            if isinstance(selected, list) and len(selected) > 0:
                selected_id = selected[0].get('id')
            
            # Case B: DataFrame 형태
            elif isinstance(selected, pd.DataFrame) and not selected.empty:
                selected_id = selected.iloc[0]['id']
            
            if selected_id:
                edit_member_dialog(str(selected_id), df)

elif menu == "신규 등록":
    st.header("📝 새 성도님 등록")
    with st.form("new_member_form"):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("성함 (필수)")
            n_role = st.selectbox("직분", ["목사", "장로", "전도사", "권사", "집사", "성도", "청년"], index=5)
            n_birth = st.date_input("생년월일", value=date(1980, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            n_status = st.selectbox("상태", ["출석 중", "장기결석", "타지역"], index=0)
        with c2:
            n_phone = st.text_input("연락처")
            n_email = st.text_input("이메일")
            n_addr = st.text_input("주소")
        
        n_family = st.text_area("가족 관계 및 메모")
        
        if st.form_submit_button("🆕 교적부에 추가 등록"):
            if n_name:
                df_curr = load_data()
                new_data = {
                    "id": str(uuid.uuid4()), # [수정 5] 신규 등록 시 고유 ID 부여
                    "이름": n_name, "직분": n_role, "생년월일": n_birth.strftime('%Y-%m-%d'),
                    "전화번호": n_phone, "이메일": n_email, "주소": n_addr, 
                    "가족": n_family, "상태": n_status, "사진": " "
                }
                # DataFrame 병합 방식 최신화
                new_row_df = pd.DataFrame([new_data])
                updated_df = pd.concat([df_curr, new_row_df], ignore_index=True)
                
                save_to_google(updated_df)
                st.success(f"{n_name} 성도님이 등록되었습니다."); st.rerun()
            else:
                st.error("성함은 필수 입력 항목입니다.")

elif menu == "PDF 주소록 생성":
    st.header("🖨️ PDF 주소록 제작")
    df = load_data()
    
    col_a, col_b = st.columns(2)
    with col_a:
        sel_status = st.multiselect("출력 대상", ["출석 중", "장기결석", "타지역"], default=["출석 중"])
    with col_b:
        sel_info = st.multiselect("포함할 정보", ["직분", "생년월일", "전화번호", "이메일", "가족"], default=["직분", "전화번호", "가족"])

    if st.button("📄 주소록 PDF 다운로드 준비"):
        # [수정 6] 폰트 캐싱 함수 사용
        font_path = get_font()
        if not font_path:
            st.stop()

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("Nanum", "", font_path, uni=True)
        pdf.set_font("Nanum", "", 18)
        pdf.cell(0, 15, "⛪ 킹스턴 한인교회 주소록", ln=True, align='C')
        pdf.ln(5)

        p_df = df[df['상태'].isin(sel_status)].sort_values(by=['주소', '이름'])
        grouped = p_df.groupby('주소')

        for addr, group in grouped:
            pdf.set_font("Nanum", "", 11)
            pdf.set_fill_color(245, 245, 245)
            # 주소 값이 없으면 '주소 미입력'으로 표시
            disp_addr = addr if str(addr).strip() else "주소 미입력"
            pdf.cell(0, 8, f" 📍 주소: {disp_addr}", ln=True, fill=True)
            pdf.ln(2)

            for _, r in group.iterrows():
                y_start = pdf.get_y()
                # 1. 사진 배치
                if str(r['사진']).startswith("data:image"):
                    try:
                        img_bin = base64.b64decode(r['사진'].split(',')[1])
                        pdf.image(io.BytesIO(img_bin), x=12, y=y_start, w=18, h=18)
                    except: pass
                
                # 2. 정보 배치
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
                
                if "가족" in sel_info and str(r['가족']).strip():
                    pdf.set_font("Nanum", "", 9)
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(0, 5, f"👨‍👩‍👧‍👦 {r['가족']}", ln=True)
                    pdf.set_text_color(0, 0, 0)

                pdf.set_left_margin(10)
                pdf.ln(4)
            pdf.ln(4)

        st.download_button("📥 클릭하여 PDF 저장", data=bytes(pdf.output()), file_name=f"교적부_{date.today()}.pdf")