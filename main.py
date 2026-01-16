import streamlit as st
import pandas as pd
import speech_recognition as sr
import io
import difflib
import os
import re
from pydub import AudioSegment
from streamlit_mic_recorder import mic_recorder
from datetime import datetime

# --- 1. إعدادات التصميم ---
st.set_page_config(page_title="مقيم نطق الأطفال", layout="centered")

def clean_arabic(text):
    noise = re.compile(r'[\u064B-\u0652]') # إزالة التشكيل
    return re.sub(noise, '', text).strip()

@st.cache_data
def load_phonetics_data():
    if os.path.exists('arabic_phonetics.csv'):
        return pd.read_csv('arabic_phonetics.csv')
    return None

df_phonetics = load_phonetics_data()

# --- 2. وظيفة حفظ البيانات (Excel) ---
def save_to_database(name, age, target, spoken, accuracy, report_text):
    db_file = 'patient_records.xlsx'
    new_entry = {
        'التاريخ': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'اسم الطفل': name,
        'العمر': age,
        'النص المستهدف': target,
        'نطق الطفل': spoken,
        'نسبة النجاح': f"{accuracy}%",
        'التشخيص': " | ".join(report_text)
    }
    
    df_new = pd.DataFrame([new_entry])
    
    if os.path.exists(db_file):
        # قراءة الملف الحالي وإضافة السطر الجديد
        df_existing = pd.read_excel(db_file)
        df_final = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_final = df_new
    
    # حفظ الملف بصيغة إكسل (تأكد من تثبيت pip install openpyxl)
    df_final.to_excel(db_file, index=False)

# --- 3. محرك التشخيص الفونولوجي ---
def run_diagnosis(target, spoken):
    if df_phonetics is None: return [], "", "", 0
    target = clean_arabic(target)
    spoken = clean_arabic(spoken)
    matcher = difflib.SequenceMatcher(None, target, spoken)
    report, t_ipa, s_ipa = [], [], []
    accuracy = round(matcher.ratio() * 100, 1)

    for char in target:
        row = df_phonetics[df_phonetics['letter'] == char] if char != " " else None
        t_ipa.append(row.iloc[0]['ipa'] if row is not None and not row.empty else char)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        t_p, s_p = target[i1:i2], spoken[j1:j2]
        if tag == 'replace':
            for tc, sc in zip(t_p, s_p):
                t_row = df_phonetics[df_phonetics['letter'] == tc]
                s_row = df_phonetics[df_phonetics['letter'] == sc]
                if not t_row.empty and not s_row.empty:
                    tr, sr = t_row.iloc[0], s_row.iloc[0]
                    report.append(f"🔄 **إبدال**: ({sc}) بدلاً من ({tc})")
                    report.append(f"   - مخرج {tr['name']}: {tr['place']} ({tr['manner']})")
                    report.append(f"   - مخرج {sr['name']}: {sr['place']} ({sr['manner']})")
                    s_ipa.append(sr['ipa'])
        elif tag == 'delete':
            for char in t_p: report.append(f"❌ **حذف**: حرف ({char})")
        elif tag == 'insert':
            for char in s_p:
                report.append(f"➕ **إضافة**: حرف ({char})")
                s_row = df_phonetics[df_phonetics['letter'] == char]
                if not s_row.empty: s_ipa.append(s_row.iloc[0]['ipa'])
        elif tag == 'equal':
            for char in s_p:
                s_row = df_phonetics[df_phonetics['letter'] == char]
                s_ipa.append(s_row.iloc[0]['ipa'] if not s_row.empty else char)
                    
    return report, "".join(t_ipa), "".join(s_ipa), accuracy

# --- 4. واجهة المستخدم ---
st.title("🔬 محلل اضطرابات النطق الفونولوجي")

if df_phonetics is not None:
    with st.sidebar:
        st.header("⚙️ الإعدادات والسجلات")
        if st.button("📂 عرض سجل المتابعة الكامل"):
            if os.path.exists('patient_records.xlsx'):
                records_df = pd.read_excel('patient_records.xlsx')
                st.session_state['show_records'] = True
            else:
                st.error("لا توجد سجلات محفوظة بعد.")

    with st.expander("👤 بيانات الطفل", expanded=True):
        c1, c2 = st.columns(2)
        child_name = c1.text_input("اسم الطفل:", placeholder="أدخل الاسم هنا")
        child_age = c2.number_input("العمر:", 2, 15, 5)
        
    target_text = st.text_input("🎯 النص المستهدف (الكلمة الصحيحة):")
    
    st.write("---")
    st.subheader("🎤 تسجيل نطق الطفل")
    record = mic_recorder(start_prompt="بدء التسجيل", stop_prompt="توقف للتحليل", key='recorder')
    
    final_spoken = ""

    if record:
        st.audio(record['bytes'])
        try:
            with st.spinner("جاري معالجة الصوت..."):
                audio_segment = AudioSegment.from_file(io.BytesIO(record['bytes']))
                wav_io = io.BytesIO()
                audio_segment.export(wav_io, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000"])
                wav_io.seek(0)
                r = sr.Recognizer()
                with sr.AudioFile(wav_io) as source:
                    audio_content = r.record(source)
                    ai_text = r.recognize_google(audio_content, language="ar-SA")
            
            st.warning("⚠️ تأكد مما سمعه البرنامج وعدله إذا لزم الأمر:")
            final_spoken = st.text_input("نطق الطفل المكتشف:", ai_text)
            
        except Exception as e:
            st.error("لم يتم التعرف على الصوت. يرجى الكتابة يدوياً.")
            final_spoken = st.text_input("اكتب الكلمة التي نطقها الطفل هنا:")

    # --- عرض النتائج والحفظ ---
    if final_spoken and target_text:
        res, tipa, sipa, acc = run_diagnosis(target_text, final_spoken)
        
        st.divider()
        st.metric("نسبة صحة النطق", f"{acc}%")
        
        col1, col2 = st.columns(2)
        col1.info(f"**IPA المستهدف:** `/{tipa}/`")
        col2.success(f"**IPA المسموع:** `/{sipa}/`")
        
        if res:
            st.subheader("📋 تقرير الأخطاء المكتشفة:")
            for line in res:
                st.write(line)
        else:
            st.balloons()
            st.success("نطق سليم تماماً! أحسنت.")

        if st.button("💾 حفظ هذه الجلسة في السجل"):
            if not child_name:
                st.error("⚠️ يرجى إدخال اسم الطفل أولاً.")
            else:
                save_to_database(child_name, child_age, target_text, final_spoken, acc, res)
                st.success(f"تمت إضافة بيانات {child_name} إلى السجل بنجاح!")

    # عرض جدول السجلات إذا تم تفعيل الخيار
    if st.session_state.get('show_records'):
        st.divider()
        st.subheader("📜 سجلات المتابعة المحفوظة")
        view_df = pd.read_excel('patient_records.xlsx')
        st.dataframe(view_df, use_container_width=True)
        if st.button("إغلاق السجل"):
            st.session_state['show_records'] = False
            st.rerun()

else:
    st.error("خطأ: لم يتم العثور على ملف arabic_phonetics.csv. يرجى رفعه في مجلد المشروع.")


















