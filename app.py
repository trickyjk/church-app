# (메뉴 3번 PDF 주소록 만들기 부분만 수정하여 반영)

elif menu == "3. PDF 주소록 만들기":
    st.header("🖨️ PDF 주소록 생성 (한글 지원)")
    df = load_data()
    st.info("한 페이지에 약 5~6명의 성도가 사진과 함께 배치됩니다.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        target_status = st.multiselect("대상 필터", options=list(df['상태'].unique()), default=["출석 중"])
    with col_b:
        include_cols = st.multiselect("포함 정보", options=["전화번호", "주소", "비즈니스 주소", "자녀", "생년월일"], default=["전화번호", "주소", "자녀"])
    
    if st.button("📄 PDF 생성 시작"):
        pdf_df = df[df['상태'].isin(target_status)]
        
        # FPDF2 설정
        pdf = FPDF()
        
        # [중요] 폰트 추가: 파일 이름이 NanumGothic.ttf 여야 합니다.
        try:
            pdf.add_font('Nanum', '', 'NanumGothic.ttf')
            pdf.set_font('Nanum', '', 16)
            font_ready = True
        except:
            st.warning("⚠️ 폰트 파일을 찾을 수 없어 영문으로 출력합니다. NanumGothic.ttf 파일을 업로드해주세요.")
            pdf.set_font("Arial", 'B', 16)
            font_ready = False
            
        pdf.add_page()
        pdf.cell(0, 10, "Kingston Korean Church Address Book", ln=True, align='C')
        pdf.ln(10)
        
        for idx, row in pdf_df.iterrows():
            curr_y = pdf.get_y()
            if curr_y > 240:
                pdf.add_page()
                curr_y = pdf.get_y()
            
            # 사진 배치
            if row['사진'] and "base64," in row['사진']:
                try:
                    img_data = base64.b64decode(row['사진'].split(",")[1])
                    img = Image.open(io.BytesIO(img_data))
                    pdf.image(img, x=10, y=curr_y, w=35, h=35)
                except: pdf.rect(10, curr_y, 35, 35)
            else: pdf.rect(10, curr_y, 35, 35)
            
            # 정보 배치 (한글 폰트 적용)
            pdf.set_xy(50, curr_y)
            if font_ready:
                pdf.set_font('Nanum', '', 12)
                pdf.cell(0, 8, f"{row['이름']} ({row['직분']})", ln=True)
                pdf.set_font('Nanum', '', 10)
            else:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, f"{row['이름']} ({row['직분']})", ln=True)
                pdf.set_font("Arial", '', 10)
                
            pdf.set_x(50)
            details = "\n".join([f"- {c}: {row[c]}" for c in include_cols if row[c] and row[c] != "nan"])
            pdf.multi_cell(0, 6, details)
            pdf.ln(15)

        pdf_bytes = pdf.output(dest='S')
        st.download_button("📥 한글 PDF 다운로드", data=pdf_bytes, file_name="church_address_book.pdf", mime="application/pdf")