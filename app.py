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

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부 v14.2")

@st.cache_resource
def get_font():
    """PDF 생성용 한글 폰트(나눔고딕) 다운로드 및 캐싱"""
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        # 구글 폰트 등 안정적인 소스에서 다운로드
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
    
    if df.empty:
        return pd.DataFrame(columns=["id", "이름", "직분", "생년월일", "전화번호", "이메일", "주소", "가족", "상태", "사진"])

    # 결측치 처리
    df = df.astype(str).replace(['nan', 'None', 'NaT', 'NaN', 'null', ''], ' ')
    
    # 고유 ID(UUID) 관리
    if 'id' not in df.columns:
        df['id'] = [str(uuid.uuid4()) for _ in range(len(df))]
    else:
        df['id'] = df.apply(lambda x: str(uuid.uuid4()) if x['id'].strip() == '' else x['id'], axis=1)
        
    return df

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        save_df = save_df.fillna(" ")
        try:
            sheet.clear()
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
                role_opts = ["목사", "장로", "전도사", "권사", "집사", "성도", "청년", "유학생", "아동부"]
                u_role = st.selectbox("직분", role_opts, 
                                    index=role_opts.index(m_info['직분']) if m_info['직분'] in role_opts else 5)
                try: def_date = datetime.strptime(m_info['생년월일'], '%Y-%m-%d').date()
                except: def_date = date(1980, 1, 1)
                u_birth = st.date_input("생년월일", value=def_date, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            with c2:
                u_phone = st.text_input("연락처", value=str(m_info['전화번호']))
                u_email = st.text_input("이메일", value=str(m_info['이메일']))
                u_addr = st.text_input("주소", value=str(m_info['주소']))
            
            u_family = st.text_area("가족 관계 (자녀 등)", value=str(m_info['가족']))
            status_opts = ["출석 중", "장기결석", "타지역", "방문", "기타"]
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
st.title("⛪ 킹스턴한인교회 통합 교적부 v14.2")
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

        gb = GridOptionsBuilder.from_dataframe(f_df[["id", "사진", "이름", "직분", "전화번호", "주소", "상태"]])
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_column("id", hide=True)
        gb.configure_column("사진", headerName="📸", cellRenderer=thumbnail_js, width=70)
        gb.configure_column("이름", pinned='left', width=100)
        gb.configure_column("상태", width=90)
        
        grid_opts = gb.build()
        grid_opts['rowHeight'] = 50

        responses = AgGrid(f_df, gridOptions=grid_opts, 
                           update_mode=GridUpdateMode.SELECTION_CHANGED,
                           data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                           allow_unsafe_jscode=True,
                           theme='balham',
                           fit_columns_on_grid_load=True)

        selected = responses.get('selected_rows')
        
        if selected is not None:
            selected_id = None
            if isinstance(selected, list) and len(selected) > 0:
                selected_id = selected[0].get('id')
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
            n_role = st.selectbox("직분", ["목사", "장로", "전도사", "권사", "집사", "성도", "청년", "유학생", "아동부"], index=5)
            n_birth = st.date_input("생년월일", value=date(1980, 1, 1), min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            n_status = st.selectbox("상태", ["출석 중", "장기결석", "타지역", "방문"], index=0)
        with c2:
            n_phone = st.text_input("연락처")
            n_email = st.text_input("이메일")
            n_addr = st.text_input("주소 (같은 주소는 주소록에서 가족으로 묶입니다)")
        
        n_family = st.text_area("가족 관계 (자녀 이름 등)")
        
        if st.form_submit_button("🆕 교적부에 추가 등록"):
            if n_name:
                df_curr = load_data()
                new_data = {
                    "id": str(uuid.uuid4()),
                    "이름": n_name, "직분": n_role, "생년월일": n_birth.strftime('%Y-%m-%d'),
                    "전화번호": n_phone, "이메일": n_email, "주소": n_addr, 
                    "가족": n_family, "상태": n_status, "사진": " "
                }
                updated_df = pd.concat([df_curr, pd.DataFrame([new_data])], ignore_index=True)
                save_to_google(updated_df)
                st.success(f"{n_name} 성도님이 등록되었습니다."); st.rerun()
            else:
                st.error("성함은 필수 입력 항목입니다.")

elif menu == "PDF 주소록 생성":
    st.header("🖨️ PDF 주소록 제작 (가족별 출력)")
    df = load_data()
    
    # 1. 설정 섹션 (캡처본 스타일 구현을 위한 옵션)
    st.subheader("1. 출력 옵션 설정")
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        # 상태 필터링
        all_statuses = list(df['상태'].unique()) if '상태' in df.columns else ["출석 중"]
        sel_statuses = st.multiselect("출력할 성도 상태 선택", all_statuses, default=["출석 중"])
    
    with col_opt2:
        # 표시할 정보 선택
        info_options = ["직분", "자녀/가족", "전화번호", "생년월일", "이메일"]
        sel_infos = st.multiselect("주소록에 포함할 항목", info_options, default=["직분", "자녀/가족", "전화번호", "이메일"])

    if st.button("📄 PDF 주소록 생성하기"):
        font_path = get_font()
        if not font_path: st.stop()

        # 데이터 필터링 및 정렬 (주소 기준 정렬 -> 가족 묶기 위함)
        filtered_df = df[df['상태'].isin(sel_statuses)].copy()
        filtered_df = filtered_df.sort_values(by=['주소', '이름'])
        
        # PDF 초기화
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("Nanum", "", font_path, uni=True)
        
        # 제목
        pdf.set_font("Nanum", "", 16)
        pdf.cell(0, 10, f"킹스턴 한인교회 주소록 ({date.today().year})", ln=True, align='L')
        pdf.ln(5)

        # 주소별로 그룹핑 (가족 단위)
        grouped = filtered_df.groupby('주소')

        # 각 그룹(가족/주소) 순회
        for addr, group in grouped:
            if not addr.strip(): continue # 주소 없는 경우 건너뛰거나 별도 처리
            
            # --- 가족 블록 시작 ---
            pdf.set_draw_color(200, 200, 200) # 회색 라인
            pdf.line(10, pdf.get_y(), 200, pdf.get_y()) # 구분선
            pdf.ln(2)
            
            start_y = pdf.get_y()
            
            # 레이아웃: 왼쪽(사진) / 오른쪽(텍스트)
            # 그룹 내 첫 번째 사람의 사진을 대표 사진으로 사용하거나, 
            # 개별 사진을 나열할 수 있음. 요청하신 캡처는 '가족 사진' 1장이지만, 
            # DB 구조상 '개인 사진'이므로, 가장 먼저 나오는 분 사진을 왼쪽에 배치합니다.
            
            # 1. 왼쪽: 사진 영역 (대표 1인 또는 가족 사진이 있다면 그것)
            # 여기서는 그룹의 첫 번째 사람 사진을 사용합니다.
            photo_width = 35
            photo_height = 35
            photo_x = 10
            
            rep_member = group.iloc[0] # 대표자
            has_photo = False
            
            if str(rep_member['사진']).startswith("data:image"):
                try:
                    img_data = base64.b64decode(rep_member['사진'].split(',')[1])
                    pdf.image(io.BytesIO(img_data), x=photo_x, y=start_y, w=photo_width, h=photo_height)
                    has_photo = True
                except:
                    pass
            
            # 사진이 없으면 빈 박스 혹은 공간 유지
            if not has_photo:
                # pdf.rect(photo_x, start_y, photo_width, photo_height) # 빈 박스 필요시 주석 해제
                pass

            # 2. 오른쪽: 텍스트 영역
            text_x = photo_x + photo_width + 5
            pdf.set_xy(text_x, start_y)
            
            # (1) 이름 및 직분 (굵게)
            # 같은 주소의 모든 이름을 나열 (예: 김세령, 오세호)
            names = []
            for _, mem in group.iterrows():
                name_str = mem['이름']
                if "직분" in sel_infos and mem['직분']:
                    # 직분은 이름 옆에 작게 붙이거나 이름만 나열
                    pass 
                names.append(name_str)
            
            # 이름 줄 생성
            pdf.set_font("Nanum", "", 14) # 굵게(Bold)는 폰트 파일 필요하므로 크기로 조절
            full_name_str = ", ".join(names)
            
            # 직분 표시 (대표자 직분 또는 가장 높은 직분 등 로직 필요, 여기선 대표자 직분 표시)
            role_str = ""
            if "직분" in sel_infos:
                # 그룹 내 직분들을 모아서 보여줄 수도 있음
                roles = [m['직분'] for _, m in group.iterrows() if m['직분']]
                role_str = " ".join(list(set(roles))) # 중복 제거
            
            # 이름 출력
            pdf.cell(100, 8, full_name_str, ln=0)
            # 직분 우측 정렬 느낌으로 출력 (좌표 조정)
            pdf.set_font("Nanum", "", 11)
            pdf.cell(0, 8, role_str, ln=1, align='R')
            
            # 현재 Y 좌표 저장 (이름 줄 다음)
            current_text_y = pdf.get_y()
            pdf.set_xy(text_x, current_text_y)
            
            pdf.set_font("Nanum", "", 10)
            
            # (2) 자녀/가족 관계
            if "자녀/가족" in sel_infos:
                # 가족 컬럼 내용을 합침
                families = [m['가족'] for _, m in group.iterrows() if m['가족'].strip()]
                if families:
                    family_str = ", ".join(list(set(families))) # 중복 내용 제거
                    pdf.cell(0, 6, f"{family_str}", ln=1)
                    pdf.set_x(text_x)

            # (3) 전화번호 (여러 명일 경우 각각 표시)
            if "전화번호" in sel_infos:
                phones = []
                for _, mem in group.iterrows():
                    if mem['전화번호'].strip():
                        phones.append(f"{mem['이름'][0]} {mem['전화번호']}") # 성+번호 로 간략화
                if phones:
                    pdf.cell(0, 6, " / ".join(phones), ln=1)
                    pdf.set_x(text_x)

            # (4) 주소 (필수)
            pdf.cell(0, 6, f"{addr}", ln=1)
            pdf.set_x(text_x)

            # (5) 생년월일 (선택 시)
            if "생년월일" in sel_infos:
                 births = []
                 for _, mem in group.iterrows():
                     births.append(f"{mem['이름']}:{mem['생년월일']}")
                 if births:
                     pdf.cell(0, 6, " ".join(births), ln=1)
                     pdf.set_x(text_x)

            # (6) 이메일
            if "이메일" in sel_infos:
                emails = [m['이메일'] for _, m in group.iterrows() if m['이메일'].strip()]
                if emails:
                    pdf.cell(0, 6, ", ".join(emails), ln=1)

            # 다음 그룹을 위해 Y좌표 이동 (사진 높이와 텍스트 높이 중 큰 것 기준)
            end_y = pdf.get_y()
            block_height = max(photo_height, end_y - start_y)
            pdf.set_y(start_y + block_height + 5) # 여백 5
            
        st.success("PDF 생성이 완료되었습니다!")
        st.download_button("📥 주소록 PDF 다운로드", data=bytes(pdf.output()), file_name=f"교적부_{date.today()}.pdf")