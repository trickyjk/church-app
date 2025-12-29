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

# --- [기능] 이미지 처리 함수 ---
def image_to_base64(img):
    if img is None: return ""
    img = img.resize((150, 150))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=70)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

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
        # 429 에러 발생 시 사용자에게 친절하게 안내
        if "429" in str(e):
            st.error("⚠️ 구글 서버 접속이 일시적으로 많습니다. 1분만 기다렸다가 새로고침(F5) 해주세요.")
        else:
            st.error(f"구글 시트 연결 실패: {e}")
        return None

# --- 데이터 불러오기 ---
def load_data():
    sheet = get_sheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            cols = ["사진", "이름", "상태", "직분", "전화번호", "주소", "비즈니스 주소", "자녀", "생년월일", "심방기록"]
            if not data: return pd.DataFrame(columns=cols)
            df = pd.DataFrame(data).astype(str)
            for c in cols:
                if c not in df.columns: df[c] = ""
            if '이름' in df.columns:
                df = df[~df['이름'].str.replace(' ', '').isin(['이름', 'Name', '번호'])]
            return df[cols]
        except:
            return pd.DataFrame(columns=["사진", "이름", "상태", "직분", "전화번호", "주소", "비즈니스 주소", "자녀", "생년월일", "심방기록"])
    return pd.DataFrame()

def save_to_google(df):
    sheet = get_sheet()
    if sheet:
        save_df = df.copy().fillna("")
        sheet.clear()
        data_to_upload = [save_df.columns.values.tolist()] + save_df.values.tolist()
        sheet.update(data_to_upload)

# --- 사이드바 메뉴 ---
menu = st.sidebar.radio("메뉴 선택", ["1. 성도 검색 및 수정", "2. 새가족 등록", "3. (관리자용) PDF 초기화"])

if menu == "1. 성도 검색 및 수정":
    st.header("🔍 성도 검색 및 관리")
    df = load_data()
    
    if not df.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input("이름/전화번호 검색")
        with col2:
            status_options = ["출석 중", "새가족", "장기결석", "한국 체류", "타지역 체류", "유학 종료", "전출"]
            selected_status = st.multiselect("상태별 모아보기", options=status_options)

        results = df.copy()
        if selected_status: results = results[results['상태'].isin(selected_status)]
        if search: results = results[results['이름'].str.contains(search) | results['전화번호'].str.contains(search)]

        st.subheader(f"📊 검색 결과: {len(results)}명")
        edited_df = st.data_editor(
            results,
            column_config={
                "사진": st.column_config.ImageColumn("사진", width="small"),
                "상태": st.column_config.SelectboxColumn("상태", options=status_options),
                "심방기록": st.column_config.TextColumn("심방기록", width="large", help="상세 기록은 하단 '심방 기록' 탭을 이용하세요.")
            },
            use_container_width=True,
            key="editor_final"
        )

        if st.button("💾 표 수정사항 저장하기", type="primary"):
            df.update(edited_df)
            save_to_google(df)
            st.success("저장되었습니다!")
            st.rerun()

        st.divider()

        # --- 심방 기록 및 사진 변경 섹션 ---
        st.subheader("📝 상세 관리 (심방 기록 / 사진)")
        if not results.empty:
            sel_person = st.selectbox("관리할 성도를 선택하세요:", results.index, format_func=lambda x: f"{results.loc[x, '이름']} ({results.loc[x, '생년월일']})")
            
            t1, t2 = st.tabs(["✍️ 심방 기록 추가", "📷 사진 변경 및 회전"])
            
            with t1:
                st.write(f"**{df.loc[sel_person, '이름']}** 성도님 심방 기록")
                st.text_area("기존 기록", value=df.loc[sel_person, '심방기록'], height=100, disabled=True)
                
                with st.form("visit_log_form", clear_on_submit=True):
                    v_date = st.date_input("심방 날짜", datetime.now())
                    v_text = st.text_area("심방 내용")
                    if st.form_submit_button("기록 저장"):
                        log = f"[{v_date}] {v_text}"
                        old_log = df.at[sel_person, '심방기록']
                        df.at[sel_person, '심방기록'] = f"{old_log} | {log}" if old_log and old_log != "nan" else log
                        save_to_google(df)
                        st.success("기록이 추가되었습니다.")
                        st.rerun()

            with t2:
                col_img1, col_img2 = st.columns([1, 2])
                with col_img1:
                    st.write("현재 사진")
                    if df.at[sel_person, '사진']: st.image(df.at[sel_person, '사진'], width=150)
                with col_img2:
                    up_file = st.file_uploader("사진 업로드", type=['jpg','jpeg','png'], key="photo_up")
                    if up_file:
                        img = Image.open(up_file)
                        if "rot" not in st.session_state: st.session_state.rot = 0
                        if st.button("🔄 90도 회전"):
                            st.session_state.rot = (st.session_state.rot + 90) % 360
                        
                        img = img.rotate(-st.session_state.rot, expand=True)
                        
                        # [에러 해결] use_container_width 삭제
                        cropped = st_cropper(img, aspect_ratio=(1,1), box_color="red")
                        
                        if st.button("이 사진으로 저장"):
                            df.at[sel_person, '사진'] = image_to_base64(cropped)
                            save_to_google(df)
                            st.session_state.rot = 0
                            st.success("사진이 변경되었습니다.")
                            st.rerun()
        else:
            st.info("검색된 성도가 없습니다.")

# --- 2. 새가족 등록 ---
elif menu == "2. 새가족 등록":
    st.header("📝 새가족 등록")
    with st.form("new_family_form"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름 (필수)")
            role = st.selectbox("직분", ["성도", "청년", "집사", "권사", "장로", "목사"])
            status = st.selectbox("상태", ["새가족", "출석 중"])
            phone = st.text_input("전화번호")
        with c2:
            birth = st.text_input("생년월일 (8자리)", placeholder="19900101")
            addr = st.text_input("주소")
            biz_addr = st.text_input("비즈니스 주소")
            child = st.text_input("자녀")
        
        if st.form_submit_button("등록하기"):
            if not name: st.error("이름을 입력해주세요.")
            else:
                if len(birth) == 8: birth = f"{birth[:4]}-{birth[4:6]}-{birth[6:]}"
                df = load_data()
                new_row = pd.DataFrame([["", name, status, role, phone, addr, biz_addr, child, birth, ""]], 
                                      columns=df.columns)
                save_to_google(pd.concat([df, new_row], ignore_index=True))
                st.success(f"{name} 성도님 등록 완료!")

# --- 3. PDF 초기화 (필요시 복구 가능) ---
elif menu == "3. (관리자용) PDF 초기화":
    st.header("⚠️ 데이터 초기화")
    st.warning("이 기능은 신중히 사용하세요.")