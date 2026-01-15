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

# --- 1. إعدادات الصفحة والتصميم ---
st.set_page_config(page_title="مقيم نطق الأطفال", layout="centered")

st.markdown("""
    <style>
    .report-card {
        background-color: white; padding: 20px; border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-right: 5px solid #2196F3;
        margin-bottom: 20px; color: #333;
    }
    h1 { color: #1E3A8A; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# دالة تنظيف النص العربي من التشكيل
def clean_arabic(text):
    if not text: return ""
    noise = re.compile(r'[\u064B-\u0652]') 
    return re.sub(noise, '', text).strip()

@st.cache_data
def load_data():
    if os.path.exists('arabic_phonetics.csv'):
        return pd.read_csv('arabic_phonetics.csv')
    return None

df = load_data()

# --- 2. وظائف التشخيص والحفظ ---

def save_to_database(name, age, target, spoken, accuracy, report_text):
    db_file = 'patient_records.csv'
    new_entry = {
        'التاريخ': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'اسم الطفل': name,
        'العمر': age,
        'النص المستهدف': target,
        'نطق الطفل': spoken,
        'نسبة النجاح': f"{accuracy}%",
        'التشخيص': " | ".join(report_text)
    }
    df_new = pd.DataFrame([new_entry])
    if not os.path.isfile(db_file):
        df_new.to_csv(db_file, index=False, encoding='utf-8-sig')
    else:
        df_new.to_csv(db_file, mode='a', index=False, header=False, encoding='utf-8-sig')

def run_diagnosis(target, spoken):
    if df is None: return [], "", "", 0
    target, spoken = clean_arabic(target), clean_arabic(spoken)
    matcher = difflib.SequenceMatcher(None, target, spoken)
    report, t_ipa, s_ipa = [], [], []
    accuracy = round(matcher.ratio() * 100, 1)

    # بناء IPA المستهدف
    for char in target:
        if char == " ": t_ipa.append(" ")
        else:
            row = df[df['letter'] == char]
            t_ipa.append(row.iloc[0]['ipa'] if not row.empty else char)

    # تحليل الاختلافات
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        t_p, s_p = target[i1:i2], spoken[j1:j2]
        if tag == 'replace':
            for tc, sc in zip(t_p, s_p):
                t_row, s_row = df[df['letter'] == tc], df[df['letter'] == sc]
                if not t_row.empty and not s_row.empty:
                    tr, sr = t_row.iloc[0], s_row.iloc[0]
                    report.append(f"🔄 **إبدال**: ({sc}) بدلاً من ({tc})")
                    report.append(f"   - مخرج {tr['name']}: {tr['place']} ({tr['manner']})")
                    report.append(f"   - مخرج {sr['name']}: {sr['place']} ({sr['manner']})")
                    s_ipa.append(sr['ipa'])
        elif tag == 'delete':
            for char in t_p:
                if char != " ": report.append(f"❌ **حذف**: حرف ({char})")
        elif tag == 'insert':
            for char in s_p:
                if char != " ":
                    report.append(f"➕ **إضافة**: حرف زائد ({char})")
                    s_row = df[df['letter'] == char]
                    if not s_row.empty: s_ipa.append(s_row.iloc[0]['ipa'])
        elif tag == 'equal':
            for char in s_p:
                if char == " ": s_ipa.append(" ")
                else:
                    s_row = df[df['letter'] == char]
                    s_ipa.append(s_row.iloc[0]['ipa'] if not s_row.empty else char)
                    
    return report, "".join(t_ipa), "".join(s_ipa), accuracy

# --- 3. واجهة المستخدم ---
st.title("🔬 محلل اضطرابات النطق الفونولوجي")

if df is not None:
    with st.expander("👤 بيانات الطفل", expanded=True):
        c1, c2 = st.columns(2)
        child_name = c1.text_input("اسم الطفل:", placeholder="أدخل اسم الطفل")
        child_age = c2.number_input("العمر:", 2, 15, 5)

    target_text = st.text_input("🎯 النص المستهدف:", placeholder="اكتب الكلمة هنا")
    
    st.write("---")
    st.subheader("🎤 تسجيل نطق الطفل")
    record = mic_recorder(start_prompt="سجل الآن", stop_prompt="توقف للتحليل", key='recorder')
    
    final_spoken = ""

    if record:
        st.write("🎧 استمع للتسجيل:")
        st.audio(record['bytes'])
        try:
            with st.spinner("جاري التعرف على الكلام..."):
                audio_segment = AudioSegment.from_file(io.BytesIO(record['bytes']))
                wav_io = io.BytesIO()
                audio_segment.export(wav_io, format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "16000"])
                wav_io.seek(0)
                r = sr.Recognizer()
                with sr.AudioFile(wav_io) as source:
                    audio_content = r.record(source)
                    ai_text = r.recognize_google(audio_content, language="ar-SA")
            
            st.warning("⚠️ إذا قام البرنامج بتصحيح الكلمة تلقائياً، يرجى تعديلها أدناه:")
            final_spoken = st.text_input("ما قاله الطفل فعلياً:", ai_text)
            
        except Exception as e:
            st.error("لم يتم التعرف على الصوت. يرجى الكتابة يدوياً.")
            final_spoken = st.text_input("اكتب الكلمة التي نطقها الطفل هنا:")

    # عرض النتائج ومعالجتها
    if final_spoken and target_text:
        res, tipa, sipa, acc = run_diagnosis(target_text, final_spoken)
        
        st.divider()
        st.markdown(f"<div class='report-card'><h3>📊 تقرير: {child_name if child_name else 'عام'}</h3><p>دقة النطق: {acc}%</p></div>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        c1.info(f"**IPA المستهدف:** `/{tipa}/`")
        c2.success(f"**IPA المسموع:** `/{sipa}/`")
        
        # عرض تفاصيل الأخطاء
        if res:
            st.subheader("📋 تقرير الأخطاء المكتشفة:")
            for line in res:
                st.write(line)
        else:
            st.balloons()
            st.success("أحسنت! النطق سليم.")

        # --- زر الحفظ ---
        if st.button("💾 حفظ التقرير في سجل المتابعة"):
            if not child_name:
                st.warning("يرجى إدخال اسم الطفل قبل الحفظ.")
            else:
                save_to_database(child_name, child_age, target_text, final_spoken, acc, res)
                st.success(f"تم حفظ تقرير {child_name} بنجاح في ملف patient_records.csv")

    # --- خيار عرض السجل المحفوظ في الجانب ---
    st.sidebar.title("إدارة السجلات")
    if st.sidebar.button("📂 عرض سجل المتابعة"):
        if os.path.exists('patient_records.csv'):
            st.sidebar.dataframe(pd.read_csv('patient_records.csv'))
        else:
            st.sidebar.info("لا يوجد سجلات محفوظة بعد.")

else:
    st.error("تأكد من وجود ملف arabic_phonetics.csv في مجلد المشروع.")






