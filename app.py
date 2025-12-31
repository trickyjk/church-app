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

# --- 구글 시트 및 화면 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (v5.9)")

# --- [기능] 유틸리티 함수 ---
def image_to_base64(img):
    if img is None: return ""
    if img.mode != "RGB": img = img.convert("RGB")
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=85, subsampling=0)
    return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"

def safe_parse_date(val):
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return None
    clean_val = "".join(filter(str.isdigit, str(val)))
    try:
        if len(clean_val) == 8: return datetime.strptime(clean_val, "%Y%m%d").date()
        return pd.to_datetime(val).date()
    except: return None

def format_phone(val):
    if not val or pd.isna(val) or str(val).lower() in ["none", "nan", ""]: return ""
    nums = "".join(filter(str.isdigit, str(val)))
    if len(nums) == 10: return f"{nums[:3]}-{nums[3:6]}-{nums[6:]}"
    elif len(nums) == 11: return f"{nums[:3]}-{nums[3:7]}-{nums[7:]}"
    return val

# --- 구글 시트 연결 및 데이터 처리 ---
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
    cols = ["사진", "이름", "직분", "신급", "상태", "전화번호", "이메일", "생년월일", "주소", "비즈니스 주소", "자녀", "심방기록", "등록신청일", "등록일", "사역이력"]
    if not data: return pd.DataFrame(columns=cols)
    df = pd.DataFrame(data).astype(str)
    for c in cols:
        if c not in df.columns: df[c] = ""
    df['생년월일'] = df['생년월일'].apply(safe_parse_date)
    df['등록신청일'] = df['등록신청일'].apply(safe_parse_date)
    df['등록일'] = df['등록일'].apply(safe_parse_date)
    df['전화번호'] = df['전화번호'].apply(format_phone)
    df.index = range(1, len(df) + 1)
    return df[cols]

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        for d in ['생년월일', '등록신청일', '등록일']:
            save_df[d] = save_df[d].apply(lambda x: str(x) if x else "")
        save_df = save_df.fillna("")
        sheet.clear()
        sheet.update([save_df.columns.values.tolist()] + save_df.values.tolist())

# 상수 설정
ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
FAITH_OPTIONS = ["유아세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 관리", "2. 신규 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 관리 (썸네일 리스트 및 선택 수정)
if menu == "1. 성도 검색 및 관리":
    st.header("🔍 성도 검색 및 리스트")
    df = load_data()
    
    if not df.empty:
        col_s1, col_s2 = st.columns([3, 1])
        with col_s1: search = st.text_input("이름, 전화번호, 또는 사역이력으로 검색하세요")
        with col_s2: s_status = st.multiselect("상태 필터", STATUS_OPTIONS, default=["출석 중"])
        
        results = df.copy()
        if s_status: results = results[results['상태'].isin(s_status)]
        if search:
            results = results[results['이름'].str.contains(search, na=False) | 
                              results['전화번호'].str.contains(search, na=False) | 
                              results['사역이력'].str.contains(search, na=False)]
        
        # 썸네일이 포함된 데이터 에디터 (이전과 동일하게 사진 표시)
        st.write(f"검색 결과: {len(results)}명")
        st.data_editor(
            results[["사진", "이름", "직분", "전화번호", "상태", "주소", "사역이력"]],
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
            },
            use_container_width=True,
            disabled=True, # 리스트는 보기 전용
            key="list_view"
        )
        
        # 성도 선택 (디폴트 선택 없음)
        st.divider()
        selected_name = st.selectbox(
            "📝 상세 정보를 확인하거나 수정할 성도를 선택하세요:", 
            options=[None] + list(results.index),
            format_func=lambda x: f"{results.loc[x, '이름']} {results.loc[x, '직분']}" if x is not None else "성도를 선택해 주세요"
        )

        # 상세 페이지 섹션 (선택 시에만 나타남)
        if selected_name:
            st.info(f"💡 현재 '{results.loc[selected_name, '이름']}' 성도님의 상세 정보를 수정 중입니다.")
            
            # 레이아웃 구성
            with st.container():
                tab1, tab2 = st.tabs(["📄 기본 인적 사항 및 목양", "📷 사진 변경"])
                
                with tab1:
                    with st.form(f"edit_form_{selected_name}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            u_name = st.text_input("이름", value=df.loc[selected_name, '이름'])
                            u_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(df.loc[selected_name, '직분']) if df.loc[selected_name, '직분'] in ROLE_OPTIONS else 6)
                            u_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(df.loc[selected_name, '신급']) if df.loc[selected_name, '신급'] in FAITH_OPTIONS else 3)
                            u_birth = st.date_input("생년월일", value=df.loc[selected_name, '생년월일'] if df.loc[selected_name, '생년월일'] else date(2000,1,1))
                        with c2:
                            u_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(df.loc[selected_name, '상태']) if df.loc[selected_name, '상태'] in STATUS_OPTIONS else 0)
                            u_phone = st.text_input("전화번호", value=df.loc[selected_name, '전화번호'])
                            u_email = st.text_input("이메일", value=df.loc[selected_name, '이메일'])
                            u_addr = st.text_input("주소", value=df.loc[selected_name, '주소'])
                        
                        st.write("---")
                        u_history = st.text_area("사역 이력", value=df.loc[selected_name, '사역이력'], help="예: 2026년 찬양팀장")
                        
                        st.write("**목양/심방 기록**")
                        st.text_area("기존 기록", value=df.loc[selected_name, '심방기록'], height=100, disabled=True)
                        new_note = st.text_area("신규 기록 추가")
                        
                        if st.form_submit_button("💾 성도 정보 업데이트", type="primary"):
                            df.at[selected_name, '이름'] = u_name
                            df.at[selected_name, '직분'] = u_role
                            df.at[selected_name, '신급'] = u_faith
                            df.at[selected_name, '생년월일'] = u_birth
                            df.at[selected_name, '상태'] = u_status
                            df.at[selected_name, '전화번호'] = format_phone(u_phone)
                            df.at[selected_name, '이메일'] = u_email
                            df.at[selected_name, '주소'] = u_addr
                            df.at[selected_name, '사역이력'] = u_history
                            if new_note:
                                log = f"[{date.today()}] {new_note}"
                                df.at[selected_name, '심방기록'] = f"{df.loc[selected_name, '심방기록']}\n{log}" if df.loc[selected_name, '심방기록'] else log
                            
                            save_to_google(df)
                            st.success("정보가 업데이트되었습니다.")
                            st.rerun()
                
                with tab2:
                    st.write("**현재 등록된 사진**")
                    curr_pic = df.loc[selected_name, '사진']
                    if curr_pic: st.image(curr_pic, width=200)
                    else: st.warning("등록된 사진이 없습니다.")
                    
                    up_file = st.file_uploader("새 사진 업로드", type=['jpg', 'jpeg', 'png'], key="photo_up")
                    if up_file:
                        img = Image.open(up_file)
                        cropped = st_cropper(img, aspect_ratio=(1,1))
                        if st.button("📷 사진 확정 및 저장"):
                            df.at[selected_name, '사진'] = image_to_base64(cropped)
                            save_to_google(df)
                            st.success("사진이 저장되었습니다.")
                            st.rerun()

# 2. 신규 등록 및 3. PDF 주소록 (안정된 기능 유지)
elif menu == "2. 신규 등록":
    st.header("📝 신규 성도 등록")
    with st.form("new_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            n_name = st.text_input("이름 (필수)")
            n_role = st.selectbox("직분", ROLE_OPTIONS, index=6)
            n_birth = st.date_input("생년월일", value=date(2000, 1, 1), min_value=date(1850, 1, 1))
        with c2:
            n_phone = st.text_input("전화번호")
            n_addr = st.text_input("주소")
            n_status = st.selectbox("상태", STATUS_OPTIONS)
        
        n_note = st.text_area("목양 노트")
        
        if st.form_submit_button("⛪ 성도 등록하기", type="primary"):
            if n_name:
                df_curr = load_data()
                new_row = [["", n_name, n_role, "해당없음", n_status, format_phone(n_phone), "", str(n_birth), n_addr, "", "", n_note, str(date.today()), str(date.today()), ""]]
                save_to_google(pd.concat([df_curr, pd.DataFrame(new_row, columns=df_curr.columns)], ignore_index=True))
                st.success(f"{n_name} 성도님 등록 완료!")
            else: st.error("이름을 입력해 주세요.")

elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    t_status = st.multiselect("출력 대상 상태", STATUS_OPTIONS, default=["출석 중"])
    
    if st.button("📄 PDF 생성"):
        pdf = FPDF()
        try:
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf'); f_name = 'Nanum'
        except: f_name = 'Arial'
        
        pdf.add_page(); pdf.set_font(f_name, '', 16)
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C'); pdf.ln(5)
        
        p_df = df[df['상태'].isin(t_status)].copy()
        p_df['addr_key'] = p_df['주소'].str.strip()
        groups = []
        for addr, group in p_df.groupby('addr_key', sort=False):
            if addr and addr != "nan": groups.append({'group': group, 'name': group.iloc[0]['이름']})
        
        # 성씨 순 정렬
        for item in sorted(groups, key=lambda x: x['name']):
            g = item['group']
            y_pos = pdf.get_y()
            if y_pos > 230: pdf.add_page(); y_pos = pdf.get_y()
            
            x_pos = 10
            for _, m in g.iterrows():
                if x_pos > 85: break
                pic = m['사진']
                if pic and "base64," in pic:
                    try: pdf.image(io.BytesIO(base64.b64decode(pic.split(",")[1])), x=x_pos, y=y_pos, w=30, h=30)
                    except: pdf.rect(x_pos, y_pos, 30, 30)
                elif os.path.exists("church_icon.png"): pdf.image("church_icon.png", x=x_pos, y=y_pos, w=30, h=30)
                else: pdf.rect(x_pos, y_pos, 30, 30)
                pdf.set_xy(x_pos, y_pos+31); pdf.set_font(f_name, '', 8); pdf.cell(30, 5, m['이름'], align='C')
                x_pos += 32
            
            pdf.set_xy(110, y_pos); pdf.set_font(f_name, '', 12)
            pdf.multi_cell(0, 7, " / ".join([f"{r['이름']} {r['직분']}" for _, r in g.iterrows()]))
            pdf.set_font(f_name, '', 10); rep = g.iloc[0]
            info = [f"생일: {rep['생년월일']}", f"전화: {rep['전화번호']}", f"주소: {rep['주소']}"]
            pdf.set_x(110); pdf.multi_cell(0, 6, "\n".join(info))
            pdf.set_y(y_pos + 45)

        st.download_button("📥 다운로드", data=bytes(pdf.output()), file_name="AddressBook.pdf")