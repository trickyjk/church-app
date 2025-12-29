import streamlit as st
import pdfplumber
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date

# --- 구글 시트 연결 설정 ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SECRET_FILE = 'secrets.json' 
SHEET_NAME = '교적부_데이터'

# 화면 설정
st.set_page_config(layout="wide", page_title="킹스턴한인교회 교적부")
st.title("⛪ 킹스턴한인교회 교적부 (Online)")

# --- 구글 시트 연결 함수 ---
def get_sheet():
    try:
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
                return pd.DataFrame(columns=["이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])
            
            df = pd.DataFrame(data)
            df = df.astype(str)
            
            # [삭제 필터] 이름 헤더 제거
            if '이름' in df.columns:
                clean_name = df['이름'].str.replace(' ', '')
                df = df[~clean_name.isin(['이름', 'Name', '번호'])]

            # 날짜 변환
            if '생년월일' in df.columns:
                df['생년월일'] = pd.to_datetime(df['생년월일'], errors='coerce').dt.date

            return df
        except Exception:
            return pd.DataFrame(columns=["이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])
    return pd.DataFrame(columns=["이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"])

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

# ==========================================
# 1. 성도 검색 및 수정
# ==========================================
if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    
    with st.spinner('데이터 불러오는 중...'):
        df = load_data()
        total_count = len(df) # 전체 인원수 기억하기
    
    if not df.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input("이름/전화번호 검색", placeholder="예: 김철수")
        with col2:
            status_options = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 모아보기", options=status_options)

        delete_mode = st.checkbox("🗑️ 삭제 모드")

        # 필터링 로직
        results = df.copy()
        if selected_status:
            results = results[results['상태'].isin(selected_status)]
        if search:
            mask = results['이름'].str.contains(search, na=False) | results['전화번호'].str.contains(search, na=False)
            results = results[mask]

        # 인원수 표시 로직
        filtered_count = len(results)
        is_filtered = (len(selected_status) > 0) or (search != "")
        
        if is_filtered:
             st.success(f"📊 **전체 {total_count}명** 중 조건에 맞는 성도는 **{filtered_count}명**입니다.")
        else:
             st.info(f"📊 **전체 성도: {total_count}명**")

        # --- 데이터 에디터 ---
        if delete_mode:
            results.insert(0, "삭제선택", False)
            
            edited_df = st.data_editor(
                results,
                column_config={
                    "삭제선택": st.column_config.CheckboxColumn("삭제", width="small"),
                    "이름": st.column_config.TextColumn("이름", width="small"),
                    "상태": st.column_config.SelectboxColumn("상태", options=status_options, width="small"),
                    "직분": st.column_config.SelectboxColumn("직분", options=["목사", "전도사", "장로", "권사", "집사", "성도", "청년"], width="small"),
                    "전화번호": st.column_config.TextColumn("전화번호", width="medium"),
                    "주소": st.column_config.TextColumn("주소", width="large"),
                    "자녀": st.column_config.TextColumn("자녀", width="medium"),
                    "생년월일": st.column_config.DateColumn("생년월일", format="YYYY-MM-DD", width="medium")
                },
                num_rows="dynamic",
                use_container_width=True
            )
            
            if st.button("🗑️ 체크한 성도 삭제 (구글 시트 반영)", type="primary"):
                to_delete = edited_df[edited_df["삭제선택"] == True]
                if not to_delete.empty:
                    delete_indices = []
                    for idx, row in to_delete.iterrows():
                        match = df[
                            (df['이름'] == row['이름']) & 
                            (df['전화번호'] == row['전화번호'])
                        ]
                        delete_indices.extend(match.index.tolist())
                    
                    final_df = df.drop(index=delete_indices)
                    with st.spinner('구글 시트에 반영 중...'):
                        save_to_google(final_df)
                    st.success("✅ 삭제 완료!")
                    st.rerun()
                else:
                    st.warning("삭제할 성도를 선택해주세요.")
                
        else:
            edited_df = st.data_editor(
                results,
                column_config={
                    "이름": st.column_config.TextColumn("이름", width="small"),
                    "상태": st.column_config.SelectboxColumn("상태", options=status_options, required=True, width="small"),
                    "직분": st.column_config.SelectboxColumn("직분", options=["목사", "전도사", "장로", "권사", "집사", "성도", "청년"], width="small"),
                    "전화번호": st.column_config.TextColumn("전화번호", width="medium"),
                    "주소": st.column_config.TextColumn("주소", width="large"),
                    "자녀": st.column_config.TextColumn("자녀", width="medium"),
                    "생년월일": st.column_config.DateColumn("생년월일", format="YYYY-MM-DD", width="medium")
                },
                num_rows="dynamic",
                use_container_width=True
            )

            if st.button("💾 변경사항 저장하기", type="primary"):
                if search or selected_status:
                    st.warning("⚠️ 필터/검색어를 지우고 전체 목록에서 수정 후 저장해주세요. (데이터 보호)")
                else:
                    with st.spinner('저장 중...'):
                        save_df = edited_df.copy()
                        save_df = save_df[~save_df['이름'].str.replace(' ', '').isin(['이름', 'Name', '번호'])]
                        save_to_google(save_df)
                    st.success("✅ 저장 완료!")
                    st.rerun()
    else:
        st.info("데이터가 없습니다. (PDF를 등록해주세요)")

# ==========================================
# 2. 새가족 등록
# ==========================================
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    with st.form("new_member_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ["성도", "청년", "집사", "권사", "장로", "전도사", "목사"])
            phone = st.text_input("전화번호")
            birth = st.text_input("생년월일 (숫자 8자리)", placeholder="예: 19710116")
        with col2:
            status = st.selectbox("상태", ["출석 중", "새가족", "한국 체류", "타지역 체류", "장기결석", "유학 종료", "전출"])
            address = st.text_input("주소")
            children = st.text_input("자녀")
            visit = st.text_input("비고/심방")
        
        if st.form_submit_button("등록 완료"):
            if name == "":
                st.error("이름을 입력해주세요.")
            else:
                if birth and len(birth) == 8 and birth.isdigit():
                    birth = f"{birth[:4]}-{birth[4:6]}-{birth[6:]}"
                
                with st.spinner('등록 중...'):
                    current_df = load_data()
                    new_data = pd.DataFrame([{
                        "이름": name, "상태": status, "직분": role, "전화번호": phone,
                        "주소": address, "자녀": children, "생년월일": birth, "심방기록": visit
                    }])
                    updated_df = pd.concat([current_df, new_data], ignore_index=True)
                    save_to_google(updated_df)
                    
                st.success(f"🎉 '{name}' 성도님 등록 완료!")

# ==========================================
# 3. PDF 초기화
# ==========================================
elif menu == "3. (관리자용) PDF로 데이터 초기화":
    st.header("⚠️ 데이터베이스 초기화")
    st.info("구글 시트의 모든 데이터가 삭제되고 PDF로 교체됩니다.")
    uploaded_file = st.file_uploader("새 주소록 PDF 업로드", type="pdf")
    
    if uploaded_file and st.button("초기화 및 변환 시작"):
        with st.spinner('변환 및 업로드 중...'):
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
                                    final_children = raw_children
                                    last_valid_address = raw_address
                                    last_valid_children = raw_children
                                else:
                                    final_address = last_valid_address
                                    if raw_children.strip() == "":
                                        final_children = last_valid_children
                                    else:
                                        final_children = raw_children
                                
                                all_data.append({
                                    "이름": name, "상태": "출석 중", "직분": role, 
                                    "전화번호": cell, "주소": final_address, 
                                    "자녀": final_children,
                                    "생년월일": "", "심방기록": ""
                                })
                            except: continue
                
                new_df = pd.DataFrame(all_data)
                cols = ["이름", "상태", "직분", "전화번호", "주소", "자녀", "생년월일", "심방기록"]
                new_df = new_df[cols]
                save_to_google(new_df)
                
            st.success(f"✅ 완료! 총 {len(new_df)}명 업로드됨")