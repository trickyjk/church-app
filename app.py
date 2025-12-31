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
st.title("⛪ 킹스턴한인교회 교적부 (v5.8)")

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

ROLE_OPTIONS = ["목사", "전도사", "장로", "권사", "안수집사", "집사", "성도", "청년"]
FAITH_OPTIONS = ["유아세례", "입교", "세례", "해당없음"]
STATUS_OPTIONS = ["출석 중", "장기결석", "한국 체류", "타지역 체류", "전출"]

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 상세정보", "2. 신규 등록", "3. PDF 주소록 만들기"])

# 1. 성도 검색 및 상세정보 (개선된 UI)
if menu == "1. 성도 검색 및 상세정보":
    st.header("🔍 성도 검색")
    df = load_data()
    
    if not df.empty:
        c1, c2 = st.columns([3, 1])
        with c1: search = st.text_input("이름 / 전화번호 / 사역이력으로 검색하세요")
        with c2: s_status = st.multiselect("상태 필터", STATUS_OPTIONS, default=["출석 중"])
        
        results = df.copy()
        if s_status: results = results[results['상태'].isin(s_status)]
        if search:
            results = results[results['이름'].str.contains(search, na=False) | 
                              results['전화번호'].str.contains(search, na=False) | 
                              results['사역이력'].str.contains(search, na=False)]
        
        st.write(f"검색 결과: {len(results)}명")
        
        # 성도 리스트에서 이름 클릭 시 선택되도록 함
        selected_id = None
        if not results.empty:
            # 리스트 테이블 표시 (편집 불가능하게 보여줌)
            st.dataframe(results[["이름", "직분", "전화번호", "상태", "주소"]], use_container_width=True)
            
            # 성도 선택 드롭다운 (이름을 클릭하는 대신 직관적인 선택 도구 제공)
            selected_id = st.selectbox("📝 정보를 보거나 수정할 성도를 선택하세요:", 
                                      results.index, 
                                      format_func=lambda x: f"{results.loc[x, '이름']} {results.loc[x, '직분']} ({results.loc[x, '상태']})")

        # --- 상세 정보 및 수정 페이지 (성도가 선택되었을 때만 표시) ---
        if selected_id:
            st.divider()
            st.subheader(f"👤 {df.loc[selected_id, '이름']} 성도 상세 정보")
            
            with st.form(f"edit_form_{selected_id}"):
                col_img, col_info = st.columns([1, 3])
                
                with col_img:
                    current_pic = df.loc[selected_id, '사진']
                    if current_pic: st.image(current_pic, width=150)
                    else:
                        if os.path.exists("church_icon.png"): st.image("church_icon.png", width=150)
                        else: st.info("사진 없음")
                    
                with col_info:
                    i_c1, i_c2 = st.columns(2)
                    with i_c1:
                        new_name = st.text_input("이름", value=df.loc[selected_id, '이름'])
                        new_role = st.selectbox("직분", ROLE_OPTIONS, index=ROLE_OPTIONS.index(df.loc[selected_id, '직분']) if df.loc[selected_id, '직분'] in ROLE_OPTIONS else 6)
                        new_faith = st.selectbox("신급", FAITH_OPTIONS, index=FAITH_OPTIONS.index(df.loc[selected_id, '신급']) if df.loc[selected_id, '신급'] in FAITH_OPTIONS else 3)
                        new_birth = st.date_input("생년월일", value=df.loc[selected_id, '생년월일'] if df.loc[selected_id, '생년월일'] else date(2000,1,1))
                    with i_c2:
                        new_status = st.selectbox("상태", STATUS_OPTIONS, index=STATUS_OPTIONS.index(df.loc[selected_id, '상태']) if df.loc[selected_id, '상태'] in STATUS_OPTIONS else 0)
                        new_phone = st.text_input("전화번호", value=df.loc[selected_id, '전화번호'])
                        new_email = st.text_input("이메일", value=df.loc[selected_id, '이메일'])
                        new_addr = st.text_input("주소", value=df.loc[selected_id, '주소'])
                
                st.write("**추가 정보**")
                new_history = st.text_area("사역 이력", value=df.loc[selected_id, '사역이력'], height=70)
                new_visit = st.text_area("목양/심방 기록 (기존 기록 뒤에 추가됩니다)", height=100)
                
                if st.form_submit_button("💾 정보 업데이트 및 저장", type="primary"):
                    df.at[selected_id, '이름'] = new_name
                    df.at[selected_id, '직분'] = new_role
                    df.at[selected_id, '신급'] = new_faith
                    df.at[selected_id, '생년월일'] = new_birth
                    df.at[selected_id, '상태'] = new_status
                    df.at[selected_id, '전화번호'] = format_phone(new_phone)
                    df.at[selected_id, '이메일'] = new_email
                    df.at[selected_id, '주소'] = new_addr
                    df.at[selected_id, '사역이력'] = new_history
                    if new_visit:
                        log = f"[{date.today()}] {new_visit}"
                        df.at[selected_id, '심방기록'] = f"{df.loc[selected_id, '심방기록']}\n{log}" if df.loc[selected_id, '심방기록'] else log
                    
                    save_to_google(df)
                    st.success(f"{new_name} 성도님의 정보가 성공적으로 수정되었습니다.")
                    st.rerun()

            # --- 사진 수정 전용 (폼 외부) ---
            with st.expander("📷 사진 등록/변경하기"):
                up_file = st.file_uploader("새 사진 업로드", type=['jpg', 'png', 'jpeg'])
                if up_file:
                    img = Image.open(up_file)
                    cropped = st_cropper(img, aspect_ratio=(1,1))
                    if st.button("새 사진 적용"):
                        df.at[selected_id, '사진'] = image_to_base64(cropped)
                        save_to_google(df)
                        st.success("사진이 변경되었습니다.")
                        st.rerun()

# 2. 신규 등록 및 3. PDF 주소록 (이전 v5.7과 동일한 안정된 코드)
elif menu == "2. 신규 등록":
    st.header("📝 신규 성도 등록")
    with st.form("new_reg"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ROLE_OPTIONS, index=6)
            birth = st.date_input("생년월일", value=date(2000, 1, 1))
        with c2:
            phone = st.text_input("전화번호")
            addr = st.text_input("주소")
            status = st.selectbox("상태", STATUS_OPTIONS)
        if st.form_submit_button("등록하기"):
            if name:
                df_curr = load_data()
                new_data = [["", name, role, "해당없음", status, format_phone(phone), "", str(birth), addr, "", "", "", str(date.today()), str(date.today()), ""]]
                save_to_google(pd.concat([df_curr, pd.DataFrame(new_data, columns=df_curr.columns)], ignore_index=True))
                st.success(f"{name} 성도님 등록 완료!")
            else: st.error("이름을 입력하세요.")

elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성")
    df = load_data()
    target_status = st.multiselect("출력할 성도 상태", options=STATUS_OPTIONS, default=["출석 중"])
    st.subheader("📋 포함 옵션")
    col_a, col_b = st.columns(2)
    with col_a: i_birth, i_phone = st.checkbox("생년월일", True), st.checkbox("전화번호", True)
    with col_b: i_addr, i_history = st.checkbox("주소", True), st.checkbox("사역이력", False)

    if st.button("📄 PDF 생성 및 다운로드"):
        pdf = FPDF()
        try:
            pdf.add_font('Nanum', '', 'NanumGothic-Regular.ttf'); font_name = 'Nanum'
        except: font_name = 'Arial'
        
        pdf.add_page(); pdf.set_font(font_name, '', 16)
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C'); pdf.ln(5)
        
        print_df = df[df['상태'].isin(target_status)].copy()
        print_df['addr_key'] = print_df['주소'].str.strip()
        groups = []
        for addr, group in print_df.groupby('addr_key', sort=False):
            if addr and addr != "nan": groups.append({'group': group, 'name': group.iloc[0]['이름']})
        
        for item in sorted(groups, key=lambda x: x['name']):
            group = item['group']
            y = pdf.get_y()
            if y > 230: pdf.add_page(); y = pdf.get_y()
            
            x = 10
            for _, m in group.iterrows():
                if x > 85: break
                pic = m['사진']
                if pic and "base64," in pic:
                    try: pdf.image(io.BytesIO(base64.b64decode(pic.split(",")[1])), x=x, y=y, w=30, h=30)
                    except: pdf.rect(x, y, 30, 30)
                elif os.path.exists("church_icon.png"): pdf.image("church_icon.png", x=x, y=y, w=30, h=30)
                else: pdf.rect(x, y, 30, 30)
                pdf.set_xy(x, y+31); pdf.set_font(font_name, '', 8); pdf.cell(30, 5, m['이름'], align='C')
                x += 32
            
            pdf.set_xy(110, y); pdf.set_font(font_name, '', 12)
            pdf.multi_cell(0, 7, " / ".join([f"{r['이름']} {r['직분']}" for _, r in group.iterrows()]))
            pdf.set_font(font_name, '', 10); info = []
            if i_birth and group.iloc[0]['생년월일']: info.append(f"생일: {group.iloc[0]['생년월일']}")
            if i_phone and group.iloc[0]['전화번호']: info.append(f"전화: {group.iloc[0]['전화번호']}")
            if i_addr and group.iloc[0]['주소']: info.append(f"주소: {group.iloc[0]['주소']}")
            if i_history and group.iloc[0]['사역이력']: info.append(f"사역: {group.iloc[0]['사역이력']}")
            pdf.set_x(110); pdf.multi_cell(0, 6, "\n".join(info))
            pdf.set_y(y + 45)

        st.download_button("📥 PDF 다운로드", data=bytes(pdf.output()), file_name="AddressBook.pdf")