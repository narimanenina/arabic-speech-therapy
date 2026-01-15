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

# دالة تنظيف النص العربي
def clean_arabic(text):
    noise = re.compile(r'[\u064B-\u0652]') # إزالة التشكيل
    return re.sub(noise, '', text).strip()

@st.cache_data
def load_data():
    if os.path.exists('arabic_phonetics.csv'):
        return pd.read_csv('arabic_phonetics.csv')
    return None

df = load_data()

# --- 2. محرك التشخيص الفونولوجي ---
def run_diagnosis(target, spoken):
    if df is None: return [], "", "", 0
    target, spoken = clean_arabic(target), clean_arabic(spoken)
    matcher = difflib.SequenceMatcher(None, target, spoken)
    report, t_ipa, s_ipa = [], [], []
    accuracy = round(matcher.ratio() * 100, 1)

    for char in target:
        row = df[df['letter'] == char] if char != " " else None
        t_ipa.append(row.iloc[0]['ipa'] if row is not None and not row.empty else char)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        t_p, s_p = target[i1:i2], spoken[j1:j2]
        if tag == 'replace':
            for tc, sc in zip(t_p, s_p):
                t_row, s_row = df[df['letter'] == tc], df[df['letter'] == sc]
                if not t_row.empty and not s_row.empty:
                    tr, sr = t_row.iloc[0], s_row.iloc[0]
                    report.append(f"🔄 **إبدال**: ({sc}) بدلاً من ({tc})")
                    report.append(f"   - مخرج {tr['name']}: {tr['place']} ({tr['manner']})")
                    report.append(f"   - مخرج {sr['name']}: {sr['place']} ({sr['manner']})")
                    s_ipa.append(sr['ipa'])
        elif tag == 'delete':
            for char in t_p: report.append(f"❌ **حذف**: حرف ({char})")
        elif tag == 'insert':
            for char in s_p:
                report.append(f"➕ **إضافة**: حرف ({char})")
                s_row = df[df['letter'] == char]
                if not s_row.empty: s_ipa.append(s_row.iloc[0]['ipa'])
        elif tag == 'equal':
            for char in s_p:
                s_row = df[df['letter'] == char]
                s_ipa.append(s_row.iloc[0]['ipa'] if not s_row.empty else char)
                    
    return report, "".join(t_ipa), "".join(s_ipa), accuracy

# --- 3. واجهة المستخدم ---
st.title("🔬 محلل اضطرابات النطق الفونولوجي")

if df is not None:
    target_text = st.text_input("🎯 الكلمة المستهدفة:", "نعم")
    
    st.write("---")
    st.subheader("🎤 تسجيل نطق الطفل")
    record = mic_recorder(start_prompt="سجل الآن", stop_prompt="توقف للتحليل", key='recorder')
    
    # متغير لتخزين النص الذي سيتم تشخيصه
    final_spoken = ""

    if record:
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
                    # الحصول على النص من جوجل
                    ai_text = r.recognize_google(audio_content, language="ar-SA")
                    
            # الحل هنا: السماح للمستخدم بتأكيد أو تعديل النص الذي سمعه البرنامج
            st.warning("⚠️ إذا قام البرنامج بتصحيح الكلمة تلقائياً، يرجى تعديلها أدناه لتطابق ما قاله الطفل فعلياً:")
            final_spoken = st.text_input("ما قاله الطفل فعلياً (تعديل يدوي إذا لزم الأمر):", ai_text)
            
        except Exception:
            st.error("لم يتم التعرف على الصوت. يرجى الكتابة يدوياً.")
            final_spoken = st.text_input("اكتب الكلمة التي نطقها الطفل هنا:")

    if final_spoken:
        res, tipa, sipa, acc = run_diagnosis(target_text, final_spoken)
        
        st.divider()
        st.metric("نسبة صحة النطق", f"{acc}%")
        
        c1, c2 = st.columns(2)
        c1.info(f"**IPA المستهدف:** `/{tipa}/`")
        c2.success(f"**IPA المسموع:** `/{sipa}/`")
        
        if res:
            st.subheader("📋 تقرير الأخطاء المكتشفة:")
            for line in res:
                st.write(line)
        else:
            st.balloons()
            st.success("أحسنت! النطق سليم.")

else:
    st.error("تأكد من وجود ملف arabic_phonetics.csv")








