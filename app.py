# Final 1.2 - Placeholder error remove
import streamlit as st
import pdfplumber
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
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
    # 4. 데이터 URL 형식으로 반환 (이미지 컬럼 인식용)
    return f"data:image/jpeg;base64,{img_str}"

def base64_to_image(img_str):
    """문자열을 다시 이미지로 변환"""
    if not img_str or img_str == "nan":
        return None
    try:
        # data:image/jpeg;base64, 헤더 제거
        if "," in img_str:
            img_str = img_str.split(",")[1]
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
            
            if '사진' not in df.columns:
                df['사진'] = ""

            cols = ["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"]
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            
            if '이름' in df.columns:
                clean_name = df['이름'].str.replace(' ', '')
                df = df[~clean_name.isin(['이름', 'Name', '번호'])]

            if '생년월일' in df.columns:
                df['생년월일'] = df['생년월일'].replace('nan', '')

            return df[cols]
        except Exception:
            return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])
    return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])

# --- 데이터 저장하기 ---
def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy()
        save_df = save_df.fillna("") 
        
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# --- 날짜 자동 변환 함수 (8자리 -> YYYY-MM-DD) ---
def fix_date_format(df_to_fix):
    """숫자 8자리(19710116)를 날짜 형식(1971-01-16)으로 변환"""
    if '생년월일' in df_to_fix.columns:
        df_to_fix['생년월일'] = df_to_fix['생년월일'].astype(str).str.replace(r'[^0-9]', '', regex=True)
        def convert_8digits(val):
            if len(val) == 8:
                return f"{val[:4]}-{val[4:6]}-{val[6:]}"
            return val
        df_to_fix['생년월일'] = df_to_fix['생년월일'].apply(convert_8digits)
    return df_to_fix

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

        delete_mode = st.checkbox("🗑️ 삭제 모드")

        results = df.copy()
        if selected_status:
            results = results[results['상태'].isin(selected_status)]
        if search:
            mask = results['이름'].str.contains(search, na=False) | results['전화번호'].str.contains(search, na=False)
            results = results[mask]

        filtered_count = len(results)
        
        if (len(selected_status) > 0) or (search != ""):
             st.success(f"📊 전체 {total_count}명 중 **{filtered_count}명** 검색됨")
        else:
             st.info(f"📊 전체 성도: {total_count}명")

        if delete_mode:
            results.insert(0, "삭제선택", False)
            edited_df = st.data_editor(
                results,
                column_config={
                    "삭제선택": st.column_config.CheckboxColumn("삭제", width="small"),
                    "사진": st.column_config.ImageColumn("사진", width="small"),
                    "이름": st.column_config.TextColumn("이름", width="small"),
                    "상태": st.column_config.SelectboxColumn("상태", options=status_options, width="small"),
                    "직분": st.column_config.SelectboxColumn("직분", options=["목사", "전도사", "장로", "권사", "집사", "성도", "청년"], width="small"),
                    "생년월일": st.column_config.TextColumn("생년월일", width="medium")
                },
                num_rows="dynamic",
                use_container_width=True,
                key="editor_delete"
            )
            
            if st.button("🗑️ 체크한 성도 영구 삭제", type="primary"):
                delete_indices = edited_df[edited_df["삭제선택"] == True].index.tolist()
                if delete_indices:
                    df = df.drop(index=delete_indices)
                    with st.spinner('삭제 후 저장 중...'):
                        save_to_google(df)
                    st.success("✅ 삭제 완료!")
                    st.rerun()
                else:
                    st.warning("삭제할 대상을 선택해주세요.")

        else:
            edited_df = st.data_editor(
                results,
                column_config={
                    "사진": st.column_config.ImageColumn("사진", width="small", help="사진 수정은 아래 '사진 변경' 구역에서 가능합니다."),
                    "이름": st.column_config.TextColumn("이름", width="small"),
                    "상태": st.column_config.SelectboxColumn("상태", options=status_options, required=True, width="small"),
                    "직분": st.column_config.SelectboxColumn("직분", options=["목사", "전도사", "장로", "권사", "집사", "성도", "청년"], width="small"),
                    "전화번호": st.column_config.TextColumn("전화번호", width="medium"),
                    "주소": st.column_config.TextColumn("주소", width="large"),
                    "자녀": st.column_config.TextColumn("자녀", width="medium"),
                    "생년월일": st.column_config.TextColumn("생년월일", width="medium", help="숫자 8자리만 입력하면 저장 시 자동 변환됩니다."),
                    "심방기록": st.column_config.TextColumn("심방기록", width="large")
                },
                num_rows="dynamic",
                use_container_width=True,
                key="editor_modify"
            )

            if st.button("💾 변경사항 저장하기 (텍스트/정보)", type="primary"):
                with st.spinner('날짜 변환 및 저장 중...'):
                    fixed_edited_df = fix_date_format(edited_df.copy())
                    df.update(fixed_edited_df)
                    save_to_google(df)
                st.success("✅ 저장 완료! (날짜가 자동으로 1971-01-16 형식으로 변환되었습니다)")
                st.rerun()

            st.divider()
            st.subheader("📷 사진 변경")
            
            if not results.empty:
                selected_idx = st.selectbox("사진을 변경할 성도를 선택하세요:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '생년월일']})")
                
                col_p1, col_p2 = st.columns([1, 1])
                with col_p1:
                    st.write("현재 사진:")
                    curr_img_str = df.loc[selected_idx, '사진']
                    if curr_img_str:
                        st.image(curr_img_str, width=150)
                    else:
                        st.write("(사진 없음)")
                
                with col_p2:
                    st.write("새 사진 업로드:")
                    uploaded_photo = st.file_uploader("이미지 파일 선택", type=['jpg', 'png', 'jpeg'], key="update_photo")
                    if uploaded_photo:
                        img = Image.open(uploaded_photo)
                        cropped_img = st_cropper(img, aspect_ratio=(1,1), box_color='#FF0000', key="crop_update")
                        if st.button("이 사진으로 저장"):
                            new_img_str = image_to_base64(cropped_img)
                            df.at[selected_idx, '사진'] = new_img_str
                            with st.spinner('사진 저장 중...'):
                                save_to_google(df)
                            st.success("✅ 사진 변경 완료!")
                            st.rerun()
            else:
                st.info("검색된 성도가 없습니다.")

    else:
        st.info("데이터가 없습니다.")

# 2. 새가족 등록
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    left_col, right_col = st.columns([1, 1])
    with left_col:
        st.info("Step 1. 기본 정보 입력")
        name = st.text_input("이름 (필수)")
        role = st.selectbox("직분", ["성도", "청년", "집사", "권사", "장로", "전도사", "목사"])
        status = st.selectbox("상태", ["출석 중", "새가족", "한국 체류", "타지역 체류", "장기결석", "유학 종료", "전출"])
        phone = st.text_input("전화번호")
        birth = st.text_input("생년월일 (숫자 8자리)", placeholder="예: 19800101")
    
    with right_col:
        st.info("Step 2. 사진 등록 (선택)")
        img_file = st.file_uploader("사진 파일 업로드", type=['png', 'jpg', 'jpeg'])
        final_img_str = ""
        if img_file:
            image = Image.open(img_file)
            st.write("↘️ 사진의 얼굴 부분을 박스로 맞춰주세요:")
            cropped_image = st_cropper(image, aspect_ratio=(1,1), box_color='blue')
            final_img_str = image_to_base64(cropped_image)

    address = st.text_input("주소")
    children = st.text_input("자녀")
    visit = st.text_input("비고/심방")

    if st.button("등록 완료", type="primary"):
        if name == "":
            st.error("이름을 입력해주세요.")
        else:
            if len(birth) == 8 and birth.isdigit():
                birth = f"{birth[:4]}-{birth[4:6]}-{birth[6:]}"

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
                                    "사진": "", "이름": name, "상태": "출석 중", "직분": role, 
                                    "전화번호": cell, "주소": final_address, 
                                    "자녀": final_children, "생년월일": "", "심방기록": ""
                                })
                            except: continue
                new_df = pd.DataFrame(all_data)
                cols = ["사진", "이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"]
                new_df = new_df[cols]
                save_to_google(new_df)
            st.success(f"✅ 완료! 총 {len(new_df)}명 업로드됨")