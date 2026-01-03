import streamlit as st
import pandas as pd
import gspread
import requests
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date

# ==========================================
# [설정 1] ImgBB API Key
IMGBB_API_KEY = "1bbd981a9a24f74780c2ab950a9ceeba"

# [설정 2] 주소록 제목 로고 (비워두면 글씨로 나옴)
CHURCH_LOGO_URL = "" 

# [설정 3] 인쇄용 제목 글씨 색상
TITLE_COLOR = "#000000" 
# ==========================================

# 1. 화면 설정
st.set_page_config(page_title="킹스턴한인교회 교적부", page_icon="⛪", layout="wide")

# 2. 스타일 설정
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Nanum+Myeongjo:wght@700&display=swap');

    div.stButton > button {{
        width: 100%;
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #d0d2d6;
        font-weight: bold;
    }}
    div.stButton > button:hover {{
        background-color: #e6f3ff !important;
        color: #0068c9 !important;
        border-color: #0068c9;
    }}
    @media print {{
        [data-testid="stSidebar"], header, footer, .stButton, .stTextInput, .stSelectbox {{ display: none !important; }}
        .main .block-container {{ padding: 0 !important; max-width: 100% !important; }}
        body {{ background-color: white !important; color: black !important; -webkit-print-color-adjust: exact; }}
        /* 인쇄할 때는 제목 박스의 그림자나 테두리 제거 */
        .title-box {{ border: none !important; box-shadow: none !important; }}
    }}
    
    /* 제목 박스 스타일 (화면용) */
    .title-box {{
        background-color: white;
        padding: 30px;
        border-radius: 10px;
        margin-bottom: 20px;
        text-align: center;
        border: 1px solid #ddd;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }}

    .print-header-text {{
        font-family: 'Nanum Myeongjo', serif;
        font-size: 42px;
        font-weight: bold;
        color: {TITLE_COLOR} !important;
        letter-spacing: 2px;
        margin-bottom: 15px;
    }}
    .print-header-line {{
        border-bottom: 3px double {TITLE_COLOR};
        width: 80%;
        margin: 0 auto; /* 중앙 정렬 */
        opacity: 0.5;
    }}
    .print-logo-img {{
        display: block; margin-left: auto; margin-right: auto;
        max-height: 120px;
    }}

    .print-card {{
        border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px;
        background-color: white; display: flex; page-break-inside: avoid; align-items: flex-start;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05); height: 100%;
    }}
    .print-photo {{
        width: 100px; height: 120px; object-fit: cover; border: 1px solid #eee; margin-right: 20px;
        background-color: #f9f9f9; display: flex; align-items: center; justify_content: center; color: #ccc;
    }}
    .print-info {{ flex: 1; }}
    .print-name {{
        color: #000000 !important; font-size: 20px; font-weight: bold; margin-bottom: 8px;
        border-bottom: 2px solid #333; padding-bottom: 5px; display: inline-block; width: 100%;
    }}
    .print-row {{ margin-bottom: 5px; font-size: 15px; color: #333333 !important; line-height: 1.4; }}
    .print-label {{ font-weight: bold; margin-right: 6px; color: #555555 !important; }}
</style>
""", unsafe_allow_html=True)

# 3. 데이터 연결
@st.cache_resource
def get_creds():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    return creds

def load_data():
    try:
        creds = get_creds()
        client = gspread.authorize(creds)
        sheet = client.open("KingstonKoreanChurch_Directory").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        return df, sheet
    except Exception as e:
        return None, None

# 4. ImgBB 업로드
def upload_to_imgbb(file_obj):
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": IMGBB_API_KEY, "expiration": 0}
        files = {"image": file_obj.getvalue()}
        response = requests.post(url, data=payload, files=files)
        if response.status_code == 200:
            return response.json()['data']['url']
        return None
    except Exception as e:
        return None

# 5. 전화번호 포맷팅
def format_phone_number(phone_str):
    if not phone_str: return ""
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return phone_str

# 6. 카드 HTML 생성
def generate_card_html(person, selected_cols):
    photo_val = str(person.get('사진', ''))
    img_tag = f'<img src="{photo_val}" class="print-photo">' if photo_val.startswith('http') else '<div class="print-photo">No Photo</div>'
    
    info_html = ""
    for col in selected_cols:
        val = person.get(col, '')
        if val:
            info_html += f'<div class="print-row"><span class="print-label">{col}:</span> {val}</div>'
    return f"""
    <div class="print-card">
        {img_tag}
        <div class="print-info">
            <div class="print-name">{person.get('이름', '')} <span style="font-size:14px; font-weight:normal;">{person.get('직분', '')}</span></div>
            {info_html}
        </div>
    </div>
    """

# 7. 팝업창
@st.dialog("성도 상세 정보 관리", width="large")
def member_dialog(member_data, row_index, sheet, mode="edit"):
    role_options = ['성도', '서리집사', '안수집사', '협동안수집사', '은퇴안수집사', '시무권사', '협동권사', '은퇴권사', '장로', '협동장로', '은퇴장로', '협동목사', '목사']
    faith_options = ['', '유아세례', '입교', '세례']
    status_options = ['출석 중', '장기결석', '전출', '한국 거주', '타 지역 거주']

    current_photo_url = str(member_data.get('사진', ''))
    if current_photo_url and current_photo_url.startswith('http'):
        st.image(current_photo_url, width=150, caption="현재 사진")

    def get_val(col): return member_data.get(col, "") if mode == "edit" else ""

    with st.form("member_form"):
        st.write("📸 **사진 업로드**")
        uploaded_file = st.file_uploader("사진 파일 선택", type=['png', 'jpg', 'jpeg', 'webp'])
        updated_data = {}

        c1, c2, c3, c4 = st.columns(4)
        with c1: updated_data['이름'] = st.text_input("이름", value=str(get_val('이름')))
        with c2:
            val = str(get_val('직분')); idx = role_options.index(val) if val in role_options else 0
            updated_data['직분'] = st.selectbox("직분", role_options, index=idx)
        with c3:
            val = str(get_val('신급')); idx = faith_options.index(val) if val in faith_options else 0
            updated_data['신급'] = st.selectbox("신급", faith_options, index=idx)
        with c4:
            val = str(get_val('상태')); idx = status_options.index(val) if val in status_options else 0
            updated_data['상태'] = st.selectbox("상태", status_options, index=idx)

        c1, c2, c3 = st.columns(3)
        with c1:
            d_str = str(get_val('생년월일')); d_val = None
            if d_str: 
                try: d_val = datetime.strptime(d_str, "%Y-%m-%d").date()
                except: pass
            picked = st.date_input("생년월일", value=d_val, min_value=date(1900,1,1), max_value=date(2100,12,31))
            updated_data['생년월일'] = picked.strftime("%Y-%m-%d") if picked else ""
        with c2: updated_data['전화번호'] = st.text_input("전화번호", value=str(get_val('전화번호')))
        with c3: updated_data['이메일'] = st.text_input("이메일", value=str(get_val('이메일')))

        updated_data['주소'] = st.text_input("주소", value=str(get_val('주소')))
        updated_data['비즈니스 주소'] = st.text_input("비즈니스 주소", value=str(get_val('비즈니스 주소')))
        updated_data['가족'] = st.text_area("가족", value=str(get_val('가족')), height=150)

        c1, c2 = st.columns(2)
        with c1:
            d_str = str(get_val('등록신청일')); d_val = None
            if d_str: 
                try: d_val = datetime.strptime(d_str, "%Y-%m-%d").date()
                except: pass
            picked = st.date_input("등록신청일", value=d_val, min_value=date(1900,1,1), max_value=date(2100,12,31))
            updated_data['등록신청일'] = picked.strftime("%Y-%m-%d") if picked else ""
        with c2:
            d_str = str(get_val('등록일')); d_val = None
            if d_str: 
                try: d_val = datetime.strptime(d_str, "%Y-%m-%d").date()
                except: pass
            picked = st.date_input("등록일", value=d_val, min_value=date(1900,1,1), max_value=date(2100,12,31))
            updated_data['등록일'] = picked.strftime("%Y-%m-%d") if picked else ""

        updated_data['사역이력'] = st.text_area("사역이력", value=str(get_val('사역이력')), height=150)

        st.markdown("---")
        st.write("📝 **목양노트**")
        updated_data['목양노트'] = st.text_area("목양노트", value=str(get_val('목양노트')), height=250, label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("💾 저장하기", type="primary", use_container_width=True)
        
        if submitted:
            try:
                final_photo_link = current_photo_url
                if uploaded_file:
                    with st.spinner("사진 업로드 중..."):
                        new_link = upload_to_imgbb(uploaded_file)
                        if new_link: final_photo_link = new_link
                
                if '전화번호' in updated_data:
                    updated_data['전화번호'] = format_phone_number(updated_data['전화번호'])

                row_values = []
                sheet_headers = sheet.row_values(1)
                for col in sheet_headers:
                    if col == '사진': row_values.append(final_photo_link)
                    else: 
                        if col in updated_data: row_values.append(updated_data[col])
                        else: row_values.append(member_data.get(col, "") if mode == "edit" else "")

                if mode == "edit":
                    sheet_row_num = row_index + 2
                    cell_range = f"A{sheet_row_num}:{chr(64+len(sheet_headers))}{sheet_row_num}"
                    sheet.update(range_name=cell_range, values=[row_values])
                    st.success("수정 완료!")
                    st.rerun()
                elif mode == "add":
                    sheet.append_row(row_values)
                    st.success("등록 완료!")
                    st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")

# --- 메인 로직 ---

df, sheet = load_data()

if df is not None:
    with st.sidebar:
        st.header("🖨️ 인쇄 설정")
        print_mode = st.toggle("주소록 인쇄 모드 켜기", value=False)
        if print_mode:
            st.info("인쇄할 항목 선택")
            all_cols = [c for c in df.columns if c not in ['사진', '이름']]
            selected_cols = st.multiselect("항목 선택", all_cols, default=['전화번호', '이메일', '주소'])
            st.warning("Ctrl+P를 눌러 인쇄하세요.")

    if print_mode:
        # [수정] 제목을 하얀 박스(.title-box) 안에 넣어서 다크모드에서도 보이게 처리
        if CHURCH_LOGO_URL:
            st.markdown(f"""
            <div class="title-box">
                <img src="{CHURCH_LOGO_URL}" class="print-logo-img">
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="title-box">
                <div class="print-header-text">2026 킹스턴한인교회 주소록</div>
                <div class="print-header-line"></div>
            </div>
            """, unsafe_allow_html=True)
        
        print_df = df.copy()
        addr_head_map = {}
        for idx, row in print_df.iterrows():
            addr = str(row.get('주소', '')).strip()
            if addr and addr not in addr_head_map:
                addr_head_map[addr] = row.get('이름', '')
        
        def get_sort_key(row):
            addr = str(row.get('주소', '')).strip()
            return addr_head_map.get(addr, row.get('이름', ''))

        print_df['sort_key'] = print_df.apply(get_sort_key, axis=1)
        print_df = print_df.sort_values(by=['sort_key'], kind='mergesort')
        
        print_pairs = []
        i = 0
        while i < len(print_df):
            p1 = print_df.iloc[i]
            p2 = None
            if i + 1 < len(print_df):
                next_p = print_df.iloc[i+1]
                addr1, addr2 = str(p1.get('주소', '')).strip(), str(next_p.get('주소', '')).strip()
                if addr1 and addr1 == addr2:
                    p2 = next_p
                    i += 2
                else: i += 1
            else: i += 1
            print_pairs.append((p1, p2))

        for p1, p2 in print_pairs:
            cols = st.columns(2)
            with cols[0]: st.markdown(generate_card_html(p1, selected_cols), unsafe_allow_html=True)
            with cols[1]:
                if p2 is not None: st.markdown(generate_card_html(p2, selected_cols), unsafe_allow_html=True)
                else: st.write("")
    else:
        st.title("⛪ 킹스턴한인교회 교적부 관리")
        c1, c2 = st.columns([3, 1])
        with c1: search_txt = st.text_input("🔍 빠른 검색", placeholder="이름/전화번호 입력")
        with c2: 
            st.write(""); st.write("")
            if st.button("➕ 새가족 등록", type="primary", use_container_width=True):
                member_dialog({}, -1, sheet, mode="add")
        st.markdown("---")
        
        filtered_df = df.copy()
        if search_txt:
            mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_txt, case=False, na=False)).any(axis=1)
            filtered_df = filtered_df[mask]

        h_cols = st.columns([1.5, 1, 2, 3, 1])
        h_cols[0].markdown("**이름 (사진)**")
        h_cols[1].markdown("**직분**")
        h_cols[2].markdown("**전화번호**")
        h_cols[3].markdown("**주소**")
        h_cols[4].markdown("**관리**")
        st.markdown("<hr style='margin: 0 0 10px 0;'>", unsafe_allow_html=True)

        if len(filtered_df) == 0: st.info("검색 결과가 없습니다.")
        else:
            for index, row in filtered_df.iterrows():
                cols = st.columns([1.5, 1, 2, 3, 1])
                with cols[0]:
                    name_txt = f"**{row.get('이름', '')}**"
                    if str(row.get('사진', '')).startswith('http'): name_txt += " 📷"
                    st.write(name_txt)
                cols[1].write(f"{row.get('직분', '')}")
                cols[2].write(f"{row.get('전화번호', '')}")
                cols[3].write(f"{row.get('주소', '')}")
                with cols[4]:
                    if st.button("✏️ 수정", key=f"edit_{index}"):
                        member_dialog(row.to_dict(), index, sheet, mode="edit")
                st.markdown("<hr style='margin: 5px 0; border-top: 1px dashed #444;'>", unsafe_allow_html=True)
else:
    st.error("데이터 연결 실패.")