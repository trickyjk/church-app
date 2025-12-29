import streamlit as st
import pdfplumber
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date
from streamlit_cropper import st_cropper
from PIL import Image
import io
import base64

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (Online)")

# --- [기능] 이미지 처리 함수들 (압축 및 변환) ---
def image_to_base64(img):
    """이미지를 구글 시트에 저장 가능한 문자열로 변환 (용량 최적화)"""
    if img is None:
        return ""
    # 1. 크기 줄이기 (썸네일용, 최대 150x150)
    img = img.resize((150, 150))
    # 2. JPG로 변환 및 메모리에 저장
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    # 3. 문자열(Base64)로 변환
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return img_str

def base64_to_image(img_str):
    """문자열을 다시 이미지로 변환"""
    if not img_str or img_str == "nan":
        return None
    try:
        img_data = base64.b64decode(img_str)
        return Image.open(io.BytesIO(img_data))
    except:
        return None

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
        st.error(f"구글 시트 연결 실패: {e}")
        return None

# --- 데이터 불러오기 ---
def load_data():
    sheet = get_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            if not data: 
                return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])
            
            df = pd.DataFrame(data)
            df = df.astype(str)
            
            # '사진' 컬럼이 없으면 새로 만듦
            if '사진' not in df.columns:
                df['사진'] = ""

            # 컬럼 순서 정리 (사진을 맨 앞으로)
            cols = ["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"]
            # 데이터에 없는 컬럼은 빈 값으로 추가
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            
            # 불필요한 헤더 행 제거
            if '이름' in df.columns:
                clean_name = df['이름'].str.replace(' ', '')
                df = df[~clean_name.isin(['이름', 'Name', '번호'])]

            if '생년월일' in df.columns:
                df['생년월일'] = pd.to_datetime(df['생년월일'], errors='coerce').dt.date

            return df[cols] # 순서 맞춰서 리턴
        except Exception:
            return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])
    return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])

# --- 데이터 저장하기 ---
def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        if '생년월일' in save_df.columns:
            save_df['생년월일'] = pd.to_datetime(save_df['생년월일']).dt.strftime('%Y-%m-%d')
            save_df = save_df.replace({'NaT': '', 'nan': ''})
        
        save_df = save_df.fillna("") 
        
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. (관리자용) PDF로 데이터 초기화"])

# 1. 성도 검색 및 수정
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    
    with st.spinner('데이터 불러오는 중...'):
        df = load_data()
        total_count = len(df)
    
    if not df.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input("이름/전화번호 검색", placeholder="예: 김철수")
        with col2:
            status_options = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 모아보기", options=status_options)

        results = df.copy()
        if selected_status:
            results = results[results['상태'].isin(selected_status)]
        if search:
            mask = results['이름'].str.contains(search, na=False) | results['전화번호'].str.contains(search, na=False)
            results = results[mask]

        filtered_count = len(results)
        
        if (len(selected_status) > 0) or (search != ""):
             st.success(f"📊 검색 결과: **{filtered_count}명**")
        
        st.divider()

        # --- [변경] 카드 형태로 보여주기 (사진 때문에 표보다 이게 낫습니다) ---
        for index, row in results.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([1, 2, 4])
                
                # 1. 사진 영역
                with c1:
                    img = base64_to_image(row['사진'])
                    if img:
                        st.image(img, width=100)
                    else:
                        st.write("🖼️ (사진 없음)")
                
                # 2. 기본 정보 영역
                with c2:
                    st.subheader(f"{row['이름']} ({row['직분']})")
                    st.caption(f"상태: {row['상태']}")
                    
                # 3. 상세 정보 및 수정 영역
                with c3:
                    with st.expander("📝 상세 정보 및 수정"):
                        with st.form(key=f"edit_{index}"):
                            new_phone = st.text_input("전화번호", value=row['전화번호'])
                            new_address = st.text_input("주소", value=row['주소'])
                            new_visit = st.text_area("심방기록/비고", value=row['심방기록'])
                            
                            # 사진 수정 기능
                            st.write("📷 사진 변경 (선택사항)")
                            uploaded_file = st.file_uploader("새 사진 업로드", type=['jpg', 'png', 'jpeg'], key=f"file_{index}")
                            cropped_img_str = row['사진'] # 기본값은 기존 사진
                            
                            if uploaded_file:
                                image = Image.open(uploaded_file)
                                st.write("박스를 움직여서 얼굴을 맞춰주세요:")
                                # 자르기 도구 호출 (1:1 비율 고정)
                                cropped_img = st_cropper(image, aspect_ratio=(1,1), box_color='#FF0000', key=f"crop_{index}")
                                cropped_img_str = image_to_base64(cropped_img) # 자른 사진을 문자열로 변환

                            if st.form_submit_button("저장"):
                                df.at[index, '전화번호'] = new_phone
                                df.at[index, '주소'] = new_address
                                df.at[index, '심방기록'] = new_visit
                                df.at[index, '사진'] = cropped_img_str # 사진 업데이트
                                
                                with st.spinner('저장 중...'):
                                    save_to_google(df)
                                st.success("✅ 수정 완료!")
                                st.rerun()
                st.divider()

    else:
        st.info("데이터가 없습니다.")

# 2. 새가족 등록
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    
    # 레이아웃 나누기
    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.info("Step 1. 기본 정보 입력")
        name = st.text_input("이름 (필수)")
        role = st.selectbox("직분", ["성도", "청년", "집사", "권사", "장로", "전도사", "목사"])
        status = st.selectbox("상태", ["출석 중", "새가족", "한국 체류", "타지역 체류", "장기결석", "유학 종료", "전출"])
        phone = st.text_input("전화번호")
        birth = st.text_input("생년월일 (예: 1980-01-01)")
    
    with right_col:
        st.info("Step 2. 사진 등록 (선택)")
        img_file = st.file_uploader("사진 파일 업로드", type=['png', 'jpg', 'jpeg'])
        final_img_str = ""
        
        if img_file:
            image = Image.open(img_file)
            st.write("↘️ 정사각형으로 자를 영역을 선택하세요:")
            # 자르기 도구 (실시간)
            cropped_image = st_cropper(image, aspect_ratio=(1,1), box_color='blue')
            # 미리보기 보여주기
            st.write("미리보기:")
            st.image(cropped_image, width=150)
            final_img_str = image_to_base64(cropped_image)

    # 하단 공통 입력
    address = st.text_input("주소")
    children = st.text_input("자녀")
    visit = st.text_input("비고/심방")

    if st.button("등록 완료", type="primary"):
        if name == "":
            st.error("이름을 입력해주세요.")
        else:
            with st.spinner('등록 중...'):
                current_df = load_data()
                new_data = pd.DataFrame([{
                    "사진": final_img_str,
                    "이름": name, "상태": status, "직분": role, "전화번호": phone,
                    "주소": address, "자녀": children, "생년월일": birth, "심방기록": visit
                }])
                updated_df = pd.concat([current_df, new_data], ignore_index=True)
                save_to_google(updated_df)
            st.success(f"🎉 '{name}' 성도님 등록 완료!")

# 3. PDF 초기화
elif menu == "3. (관리자용) PDF로 데이터 초기화":
    st.header("⚠️ 데이터베이스 초기화")
    st.warning("주의: 기존 사진과 데이터가 모두 삭제됩니다.")
    uploaded_file = st.file_uploader("새 주소록 PDF 업로드", type="pdf")
    
    if uploaded_file and st.button("초기화 및 변환 시작"):
        with st.spinner('변환 중...'):
            with pdfplumber.open(uploaded_file) as pdf:
                all_data = []
                last_valid_address = "" 
                last_valid_children = "" 

                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or row[1] is None: continue
                            try:
                                name = row[1].replace('\n', ' ') if row[1] else ""
                                if name.replace(' ', '') in ["이름", "Name", "번호"]: continue
                                if row[0] == '번호': continue
                                role = row[2].replace('\n', ' ') if row[2] else ""
                                raw_address = row[3].replace('\n', ' ') if row[3] else ""
                                raw_children = row[6].replace('\n', ', ') if len(row) > 6 and row[6] else ""
                                cell = row[5].replace('\n', ', ') if len(row) > 5 and row[5] else ""
                                
                                if raw_address.strip() != "":
                                    final_address = raw_address
                                    last_valid_address = raw_address
                                else:
                                    final_address = last_valid_address
                                
                                if raw_children.strip() != "":
                                    final_children = raw_children
                                    last_valid_children = raw_children
                                else:
                                    final_children = last_valid_children

                                all_data.append({
                                    "사진": "", # 초기화할 땐 사진 없음
                                    "이름": name, "상태": "출석 중", "직분": role, 
                                    "전화번호": cell, "주소": final_address, 
                                    "자녀": final_children,
                                    "생년월일": "", "심방기록": ""
                                })
                            except: continue
                new_df = pd.DataFrame(all_data)
                cols = ["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"]
                new_df = new_df[cols]
                save_to_google(new_df)
            st.success(f"✅ 완료! 총 {len(new_df)}명 업로드됨")