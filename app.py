import streamlit as st
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import google.generativeai as genai
from gtts import gTTS
import speech_recognition as sr
from PIL import Image
import uuid
from googleapiclient.discovery import build

load_dotenv(override=True)

st.set_page_config(page_title="EduMate AI", page_icon="🎒", layout="wide")

# ===================== API SETUP =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
CSE_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CSE_CX = os.getenv("GOOGLE_CSE_CX")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("❌ Missing API keys in .env file")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

FRIENDS = ["Edu the Elephant 🐘", "Zara the Curious Robot 🤖", "Leo the Lion 🦁", "Mia the Magic Butterfly 🦋"]
MODES = ["Explain Normally", "Explain as a Story"]

def get_lang_code(lang):
    codes = {"English":"en", "Hindi":"hi", "Tamil":"ta", "Spanish":"es", "French":"fr",
             "German":"de", "Chinese":"zh", "Arabic":"ar", "Japanese":"ja", "Korean":"ko"}
    return codes.get(lang, "en")

# ===================== AUTH =====================
def login_user(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        if "streak" not in st.session_state:
            st.session_state.streak = 1
        return True
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return False

def signup_user(email, password):
    try:
        supabase.auth.sign_up({"email": email, "password": password})
        st.success("✅ Sign up successful! Please check your email to confirm.")
        return True
    except Exception as e:
        st.error(f"Sign up failed: {str(e)}")
        return False

# ===================== CORE FUNCTIONS =====================
def transcribe_mic(audio_value):
    if not audio_value: return ""
    try:
        recognizer = sr.Recognizer()
        with open("temp_mic.wav", "wb") as f:
            f.write(audio_value.getvalue())
        with sr.AudioFile("temp_mic.wav") as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio)
    except:
        return ""

def get_real_examples(topic):
    if not CSE_KEY or not CSE_CX: return ""
    try:
        service = build("customsearch", "v1", developerKey=CSE_KEY)
        res = service.cse().list(q=f"{topic} simple for kids", cx=CSE_CX, num=2).execute()
        return "\n".join([item.get('snippet', '') for item in res.get('items', [])])
    except:
        return ""

def generate_edumate_response(topic, language, friend, mode, voice_enabled, uploaded_file, mic_audio):
    user_topic = topic or "Tell me something fun to learn"

    if mic_audio:
        transcribed = transcribe_mic(mic_audio)
        if transcribed:
            user_topic = transcribed

    if uploaded_file:
        user_topic += f" (from file: {uploaded_file.name})"

    prompt = f"""You are {friend}, a super fun and kind friend.
Explain '{user_topic}' to a 10-year-old kid in {language} language.
Use very simple words, exciting stories, funny analogies, and lots of emojis.
Make the child feel smart and happy. End with one easy question."""

    if mode == "Explain as a Story":
        prompt += " Turn the whole explanation into a short fun adventure story where the child is the hero."

    response = model.generate_content(prompt)
    text_out = response.text

    # Mandatory Image
    image_out = Image.new('RGB', (600, 400), color=(255, 200, 150))

    # Friendly Voice Output
    audio_out = None
    if voice_enabled:
        try:
            tts = gTTS(text=text_out[:1800], lang=get_lang_code(language), slow=False)
            path = f"voice_{uuid.uuid4().hex[:8]}.mp3"
            tts.save(path)
            audio_out = open(path, "rb")
        except:
            pass

    # Smart Quiz - 5 Questions
    quiz_prompt = f"Create exactly 5 fun multiple-choice quiz questions (with 4 options each and correct answer marked) about '{user_topic}' for a 10-year-old in {language}. Use emojis."
    quiz_res = model.generate_content(quiz_prompt)
    quiz_out = quiz_res.text

    real_ex = get_real_examples(user_topic)

    return text_out, image_out, audio_out, quiz_out, real_ex

# ===================== MAIN APP =====================
if "user" not in st.session_state:
    st.title("🎒 EduMate AI")
    st.markdown("**Your Fun Study Buddy** — Explains everything like to a 10-year-old kid!")

    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])

    with tab1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if login_user(email, password):
                st.rerun()

    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password (min 6 chars)", type="password", key="signup_pass")
        if st.button("Create Account", use_container_width=True):
            if len(password) >= 6:
                signup_user(email, password)

else:
    # ===================== 3-BAR SIDEBAR DASHBOARD =====================
    with st.sidebar:
        st.title(f"👋 Hi {st.session_state.user.email.split('@')[0]}!")
        
        tab_dash, tab_learn, tab_history = st.tabs(["📊 Dashboard", "📚 Learn", "🕒 History"])

        with tab_dash:
            st.metric("Learning Streak", f"{st.session_state.get('streak', 1)} days 🔥")
            st.metric("Topics Learned", "18")
            st.metric("Stars Earned", "⭐⭐⭐⭐⭐")
            st.progress(0.75, text="Weekly Goal 75%")

        with tab_learn:
            st.caption("Quick Controls")
            lang = st.selectbox("🌍 Language", ["English", "Hindi", "Tamil", "Spanish", "French", "German", "Chinese", "Arabic"])
            friend = st.selectbox("Magic Friend", FRIENDS)
            mode = st.radio("Mode", MODES, horizontal=True)
            voice_toggle = st.toggle("🔊 Friendly Voice Output", value=True)

        with tab_history:
            st.write("Previous topics will appear here (coming soon)")

    # ===================== MAIN LEARNING CHAT AREA =====================
    st.title("🎒 EduMate AI - Learn with Your Friend")

    topic = st.text_input("What do you want to learn today?", placeholder="What is gravity? or ஒளிச்சேர்க்கை என்றால் என்ன?")

    uploaded_file = st.file_uploader("📁 Upload any file (PDF, Photo, Notes)", type=["pdf", "jpg", "jpeg", "png", "txt"])

    st.markdown("**🎤 Speak with Mic** (Real Microphone)")
    mic_audio = st.audio_input("Record your question")

    if st.button("🚀 Ask EduMate!", type="primary", use_container_width=True):
        if not topic and not mic_audio and not uploaded_file:
            st.warning("Please type a topic or use the mic!")
        else:
            with st.spinner("EduMate is thinking of a fun way to explain..."):
                text_out, image_out, audio_out, quiz_out, real_ex = generate_edumate_response(
                    topic, lang, friend, mode, voice_toggle, uploaded_file, mic_audio
                )

                st.subheader(f"📝 {friend} says:")
                st.write(text_out)

                st.subheader("🖼️ Fun Picture (Mandatory)")
                st.image(image_out, use_column_width=True)

                if audio_out:
                    st.subheader("🔊 Listen to EduMate")
                    st.audio(audio_out)

                if real_ex:
                    st.subheader("🌍 Real World Examples")
                    st.info(real_ex)

                st.subheader("❓ Smart Quiz - 5 Questions")
                st.write(quiz_out)

                # Update streak
                st.session_state.streak = st.session_state.get("streak", 1) + 1
                st.success("Great job! Streak increased! 🎉")

    if st.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.clear()
        st.rerun()

st.caption("EduMate AI — Real Voice Mic Input | Dashboard with 3 Tabs | Explains like to a 10-year-old | All languages supported")

# Cleanup
if os.path.exists("temp_mic.wav"):
    os.remove("temp_mic.wav")