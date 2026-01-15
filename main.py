import streamlit as st
import pandas as pd
import speech_recognition as sr
import io
import difflib
import os
import librosa
import soundfile as sf
from streamlit_mic_recorder import mic_recorder
from datetime import datetime

# --- 1. إعدادات الصفحة والجماليات ---
st.set_page_config(page_title="مقيم نطق الأطفال", layout="centered")

st.markdown("""
    <style>
    .report-card {
        background-color: white; padding: 20px; border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-right: 5px solid #2196F3;
        margin-bottom: 20px; color: #333;
    }
    h1 { color: #1E3A8A; text-align: center; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #2196F3; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    if os.path.exists('arabic_phonetics.csv'):
        return pd.read_csv('arabic_phonetics.csv')
    return None

df = load_data()

# --- 2. وظيفة حفظ البيانات ---
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

# --- 3. محرك التشخيص الفونولوجي المعدل ---
def run_diagnosis(target, spoken):
    if df is None: return [], "", "", 0
    matcher = difflib.SequenceMatcher(None, target, spoken)
    report, t_ipa, s_ipa = [], [], []
    accuracy = round(matcher.ratio() * 100, 1)

    for char in target:
        if char == " ": t_ipa.append(" ")
        else:
            row = df[df['letter'] == char]
            t_ipa.append(row.iloc[0]['ipa'] if not row.empty else char)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        t_p, s_p = target[i1:i2], spoken[j1:j2]
        if tag == 'replace':
            for tc, sc in zip(t_p, s_p):
                t_row, s_row = df[df['letter'] == tc], df[df['letter'] == sc]
                if not t_row.empty and not s_row.empty:
                    report.append(f"🔄 إبدال: ({sc}) بدلاً من ({tc}) | المخرج: {t_row.iloc[0]['place']} ← {s_row.iloc[0]['place']}")
                    s_ipa.append(s_row.iloc[0]['ipa'])
        elif tag == 'delete':
            for char in t_p:
                if char != " ": report.append(f"❌ حذف: حرف ({char})")
        elif tag == 'insert':
            for char in s_p:
                if char != " ":
                    report.append(f"➕ إضافة: حرف ({char})")
                    s_row = df[df['letter'] == char]
                    if not s_row.empty: s_ipa.append(s_row.iloc[0]['ipa'])
        elif tag == 'equal':
            for char in s_p:
                if char == " ": s_ipa.append(" ")
                else:
                    s_row = df[df['letter'] == char]
                    s_ipa.append(s_row.iloc[0]['ipa'] if not s_row.empty else char)
                    
    return report, "".join(t_ipa), "".join(s_ipa), accuracy

# --- 4. واجهة المستخدم ---
st.title("تقييم الكلام لدى الأطفال ذوي اضطرابات النطق")

if df is not None:
    with st.expander("👤 بيانات الطفل", expanded=True):
        c1, c2 = st.columns(2)
        child_name = c1.text_input("اسم الطفل:", placeholder="اسم الطفل")
        child_age = c2.number_input("العمر:", 2, 15, 5)

    target_text = st.text_input("🎯 النص المستهدف:", placeholder="اكتب الكلمة هنا")
    
    # مسجل الصوت
    record = mic_recorder(start_prompt="ابدأ تسجيل الصوت 🎤", stop_prompt="توقف للتحليل ⏹️", key='recorder')
    
    spoken_text = ""
    if record:
        st.write("🎧 استمع للتسجيل قبل التحليل:")
        st.audio(record['bytes'])
        
        try:
            with st.spinner("جاري معالجة الصوت والتعرف على الكلمات..."):
                # معالجة الصوت
                raw_audio = io.BytesIO(record['bytes'])
                y, sr_rate = librosa.load(raw_audio, sr=None) 
                
                buf = io.BytesIO()
                sf.write(buf, y, sr_rate, format='WAV', subtype='PCM_16')
                buf.seek(0)
                
                r = sr.Recognizer()
                with sr.AudioFile(buf) as source:
                    # تعديل لضبط مستوى الضجيج في الخلفية
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio_content = r.record(source)
                    spoken_text = r.recognize_google(audio_content, language="ar-SA")
            
            st.success(f"الكلمة المكتشفة: **{spoken_text}**")
            
        except sr.UnknownValueError:
            st.error("⚠️ لم يتم التعرف على الصوت. حاول النطق بوضوح أكثر في مكان هادئ.")
        except Exception as e:
            st.error(f"⚠️ خطأ فني: {e}")

    if spoken_text and target_text:
        res, tipa, sipa, acc = run_diagnosis(target_text, spoken_text)
        
        st.markdown(f"<div class='report-card'><h3>📊 تقرير: {child_name if child_name else 'عام'}</h3><p>دقة النطق الإجمالية: {acc}%</p></div>", unsafe_allow_html=True)
        st.write(f"**IPA المستهدف:** `/{tipa}/` | **IPA المنطوق:** `/{sipa}/`")
        
        if st.button("💾 حفظ التقرير في سجل المتابعة"):
            if not child_name:
                st.warning("يرجى إدخال اسم الطفل لحفظ السجل.")
            else:
                save_to_database(child_name, child_age, target_text, spoken_text, acc, res)
                st.success(f"تم حفظ تقرير {child_name} بنجاح!")

        st.divider()
        if res:
            st.subheader("📋 تفاصيل التشخيص الفونولوجي:")
            for line in res: st.info(line)
        else:
            st.success("✅ نطق سليم تماماً!")

    # عرض السجل في الجانب
    if st.sidebar.button("📂 عرض سجل المتابعة"):
        if os.path.exists('patient_records.csv'):
            st.sidebar.dataframe(pd.read_csv('patient_records.csv'))
        else:
            st.sidebar.info("لا يوجد سجلات بعد.")
else:
    st.error("ملف 'arabic_phonetics.csv' مفقود.")
