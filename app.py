import streamlit as st
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import google.generativeai as genai
from gtts import gTTS
import speech_recognition as sr
from PIL import Image, ImageDraw
import uuid
import PyPDF2
import requests
from io import BytesIO
from pexels_api import API
from datetime import datetime

load_dotenv(override=True)

# ===================== API SETUP =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_KEY = os.getenv("PEXELS_API_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY]):
    st.error("❌ Missing required API keys in .env file")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# ===================== LANGUAGES =====================
LANGUAGES = {
    "English": "en", "Hindi": "hi", "Tamil": "ta", "Telugu": "te", "Kannada": "kn",
    "Malayalam": "ml", "Bengali": "bn", "Marathi": "mr", "Gujarati": "gu", "Punjabi": "pa",
    "Odia": "or", "Assamese": "as", "Urdu": "ur",
    "Spanish": "es", "French": "fr", "German": "de", "Chinese": "zh", "Arabic": "ar",
    "Japanese": "ja", "Korean": "ko", "Russian": "ru", "Portuguese": "pt", "Italian": "it",
    "Dutch": "nl", "Turkish": "tr", "Vietnamese": "vi", "Thai": "th", "Indonesian": "id",
    "Polish": "pl", "Swedish": "sv", "Greek": "el", "Hebrew": "he", "Persian": "fa"
}

FRIENDS = ["Edu the Elephant 🐘", "Zara the Curious Robot 🤖", "Leo the Lion 🦁", "Mia the Magic Butterfly 🦋"]
MODES = ["Explain Normally", "Explain as a Story"]

def get_lang_code(lang):
    return LANGUAGES.get(lang, "en")

# ===================== PROGRESS & HISTORY =====================
def load_user_progress():
    if "user" not in st.session_state: return
    try:
        res = supabase.table("user_progress").select("*").eq("user_id", st.session_state.user.id).execute()
        if res.data:
            data = res.data[0]
            st.session_state.streak = data.get("streak", 1)
            st.session_state.stars = data.get("stars", 0)
            st.session_state.topics_learned = data.get("topics_learned", 0)
        else:
            supabase.table("user_progress").insert({
                "user_id": st.session_state.user.id,
                "streak": 1,
                "stars": 0,
                "topics_learned": 0,
                "last_active": datetime.utcnow().isoformat()
            }).execute()
            st.session_state.streak = 1
            st.session_state.stars = 0
            st.session_state.topics_learned = 0
    except:
        st.session_state.streak = 1
        st.session_state.stars = 0
        st.session_state.topics_learned = 0

def save_user_progress():
    if "user" not in st.session_state: return
    try:
        supabase.table("user_progress").upsert({
            "user_id": st.session_state.user.id,
            "streak": st.session_state.get("streak", 1),
            "stars": st.session_state.get("stars", 0),
            "topics_learned": st.session_state.get("topics_learned", 0),
            "last_active": datetime.utcnow().isoformat()
        }).execute()
    except:
        pass

def save_to_history(topic):
    if "user" not in st.session_state: return
    try:
        supabase.table("history").insert({
            "user_id": st.session_state.user.id,
            "topic": str(topic)[:200],
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except:
        pass

# ===================== FILE READING =====================
def read_uploaded_file(uploaded_file):
    if not uploaded_file: return ""
    try:
        if uploaded_file.type == "application/pdf":
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
            return text[:2000]
        elif uploaded_file.type.startswith("text/") or uploaded_file.name.endswith(".txt"):
            return uploaded_file.getvalue().decode("utf-8")[:2000]
        else:
            return f"Uploaded file: {uploaded_file.name}"
    except Exception as e:
        return f"Error reading file: {str(e)[:100]}"

# ===================== IMPROVED PEXELS IMAGE =====================
def get_real_kid_image(topic):
    if not PEXELS_KEY:
        return create_simple_fallback(topic), f"Image about {topic}"

    try:
        pexels = API(PEXELS_KEY)
        
        # Much better queries for educational/science topics
        base_queries = [
            f"{topic} diagram for kids",
            f"{topic} illustration simple",
            f"{topic} educational diagram",
            f"{topic} cycle explanation",
            f"{topic} process step by step",
            f"{topic} water cycle" if "water" in topic.lower() or "cycle" in topic.lower() else f"{topic} learning"
        ]

        bad_keywords = ["paramecium", "cilia", "vacuole", "nucleus", "amoeba", "bacteria", "cell", "microscope"]

        for q in base_queries:
            results = pexels.search(query=q, page=1, results_per_page=12)
            if results and results.get('photos'):
                for photo in results['photos']:
                    alt_text = photo.get('alt', '').lower()
                    # Skip clearly unrelated biology images
                    if any(bad in alt_text for bad in bad_keywords):
                        continue
                    
                    try:
                        img_url = photo['src']['large']
                        response = requests.get(img_url, timeout=12)
                        if response.status_code == 200:
                            img = Image.open(BytesIO(response.content))
                            caption = photo.get('alt', f"Educational image about {topic}")
                            return img, caption
                    except:
                        continue
    except Exception as e:
        st.warning(f"Image search issue: {str(e)[:100]}")

    # Final fallback
    return create_simple_fallback(topic), f"Simple illustration: {topic}"

def create_simple_fallback(topic):
    img = Image.new('RGB', (720, 420), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((80, 140), str(topic).upper(), fill=(0, 0, 100), size=48)
    draw.text((100, 220), "Educational Illustration for Kids", fill=(80, 80, 80), size=28)
    draw.text((120, 270), "🌍 Learn with EduMate", fill=(0, 100, 0), size=24)
    return img

# ===================== SAFE GENERATE =====================
def safe_generate_content(prompt):
    try:
        response = model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.text
        return "Sorry buddy! I couldn't create this right now. Try a different topic 😊"
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "quota" in error_str:
            return "⏳ Oops! Daily limit reached. Please wait a few minutes and try again 😊"
        return f"Oops! {str(e)[:150]}"

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

def clean_for_voice(text):
    import re
    return re.sub(r'[^\w\s.,!?]', '', text).strip()

# ===================== CORE RESPONSE =====================
def generate_edumate_response(topic, language, friend, mode, voice_enabled, uploaded_file, mic_audio):
    user_topic = topic or "Tell me something fun"

    if mic_audio:
        transcribed = transcribe_mic(mic_audio)
        if transcribed:
            user_topic = transcribed

    file_content = read_uploaded_file(uploaded_file)
    show_image = not (bool(file_content) or bool(mic_audio))

    if file_content:
        prompt = f"""You are {friend}, a super fun and kind friend.
Explain the content of this uploaded file to a 10-year-old kid in simple {language} language.
File content: {file_content}
Use very simple words, exciting stories, funny analogies, and lots of emojis.
Make the child feel smart and happy. End with one easy question."""
    else:
        prompt = f"""You are {friend}, a super fun and kind friend.
Explain '{user_topic}' to a 10-year-old kid in simple {language} language.
Use very simple words, exciting stories, funny analogies, and lots of emojis.
Make the child feel smart and happy. End with one easy question."""

        if mode == "Explain as a Story":
            prompt += " Turn the whole explanation into a short fun adventure story where the child is the hero."

    text_out = safe_generate_content(prompt)

    image_out = None
    image_caption = ""
    if show_image:
        image_out, image_caption = get_real_kid_image(user_topic)

    audio_out = None
    if voice_enabled and "Sorry" not in text_out and "Oops" not in text_out:
        clean_text = clean_for_voice(text_out)
        try:
            tts = gTTS(text=clean_text[:1800], lang=get_lang_code(language), slow=False)
            path = f"voice_{uuid.uuid4().hex[:8]}.mp3"
            tts.save(path)
            audio_out = open(path, "rb")
        except:
            pass

    quiz_topic = file_content[:500] if file_content else user_topic
    quiz_prompt = f"""Create exactly 5 fun multiple-choice quiz questions about '{quiz_topic}' for a 10-year-old in {language}.
Randomly choose which option is correct.
Do NOT mention the correct answer.
Format each exactly like this:
Q1: Question text here?
1) option one
2) option two
3) option three
4) option four

Do the same for Q2 to Q5."""

    quiz_out = safe_generate_content(quiz_prompt)

    return text_out, image_out, audio_out, quiz_out, image_caption, file_content

# ===================== AUTH =====================
def login_user(email, password):
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        load_user_progress()
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

def reset_password(email):
    try:
        supabase.auth.reset_password_for_email(email)
        st.success("✅ Password reset link sent to your email. Please check your inbox.")
        return True
    except Exception as e:
        st.error(f"Failed to send reset link: {str(e)}")
        return False

# ===================== MAIN APP =====================
if "user" not in st.session_state:
    st.title("🎒 EduMate AI")
    st.markdown("**Your Fun Study Buddy** — Explains everything like to a 10-year-old kid!")

    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])

    with tab1:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("Login", type="primary", use_container_width=True):
                if login_user(email, password):
                    st.rerun()
        with col2:
            if st.button("Forgot Password?"):
                if email:
                    reset_password(email)
                else:
                    st.warning("Please enter your email first")

    with tab2:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password (min 6 chars)", type="password", key="signup_pass")
        if st.button("Create Account", use_container_width=True):
            if len(password) >= 6:
                signup_user(email, password)

else:
    if "streak" not in st.session_state:
        load_user_progress()

    with st.sidebar:
        st.title(f"👋 Hi {st.session_state.user.email.split('@')[0]}!")
        tab_dash, tab_learn, tab_history = st.tabs(["📊 Dashboard", "📚 Learn", "🕒 History"])

        with tab_dash:
            st.metric("Learning Streak", f"{st.session_state.get('streak', 1)} days 🔥")
            st.metric("Topics Learned", st.session_state.get("topics_learned", 0))
            st.metric("Stars Earned", f"⭐ {st.session_state.get('stars', 0)}")
            st.progress(0.90, text="Weekly Goal 90%")

        with tab_learn:
            st.caption("Quick Controls")
            lang = st.selectbox("🌍 Select Language", list(LANGUAGES.keys()))
            friend = st.selectbox("Magic Friend", FRIENDS)
            mode = st.radio("Mode", MODES, horizontal=True)
            voice_toggle = st.toggle("🔊 Friendly Voice Output", value=True)

        with tab_history:
            st.write("**Recent Topics:**")
            try:
                history = supabase.table("history").select("topic, created_at").eq("user_id", st.session_state.user.id).order("created_at", desc=True).limit(5).execute()
                for item in history.data:
                    st.write(f"• {item['topic']}")
            except:
                st.write("No history yet.")

    st.title("🎒 EduMate AI - Learn with Your Friend")

    topic = st.text_input("What do you want to learn today?", placeholder="What is gravity? or Water cycle?")

    uploaded_file = st.file_uploader("📁 Upload PDF, Photo or Notes", type=["pdf", "jpg", "jpeg", "png", "txt"])

    st.markdown("**🎤 Speak with Mic**")
    mic_audio = st.audio_input("Record your question")

    col1, col2 = st.columns([4, 1])
    with col1:
        ask_btn = st.button("🚀 Ask EduMate!", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key.startswith("last_") or key in ["quiz_out", "quiz_started", "current_q", "user_answers"]:
                    del st.session_state[key]
            st.rerun()

    if ask_btn:
        if not topic and not mic_audio and not uploaded_file:
            st.warning("Please ask something or upload a file!")
        else:
            with st.spinner("EduMate is preparing fun explanation..."):
                text_out, image_out, audio_out, quiz_out, image_caption, file_content = generate_edumate_response(
                    topic, lang, friend, mode, voice_toggle, uploaded_file, mic_audio
                )

                st.session_state.last_text = text_out
                st.session_state.last_image = image_out
                st.session_state.last_audio = audio_out
                st.session_state.quiz_out = quiz_out
                st.session_state.image_caption = image_caption
                st.session_state.current_q = 0
                st.session_state.quiz_started = False
                st.session_state.user_answers = {}

                # Save history
                if file_content and file_content.strip():
                    current_topic = file_content[:150]
                elif topic and topic.strip():
                    current_topic = topic.strip()
                else:
                    current_topic = "Voice Question"

                save_to_history(current_topic)

                # Update progress
                st.session_state.streak = st.session_state.get("streak", 1) + 1
                st.session_state.stars = st.session_state.get("stars", 0) + 10
                st.session_state.topics_learned = st.session_state.get("topics_learned", 0) + 1
                save_user_progress()

    # ===================== DISPLAY CONTENT =====================
    if "last_text" in st.session_state:
        st.subheader(f"📝 {friend} says:")
        st.write(st.session_state.last_text)

        if st.session_state.last_image is not None:
            st.subheader("🖼️ Educational Image")
            st.image(st.session_state.last_image, width=720, caption=st.session_state.image_caption)

        if st.session_state.last_audio:
            st.subheader("🔊 Listen to EduMate")
            st.audio(st.session_state.last_audio)

        st.subheader("❓ Smart Quiz")
        if st.button("Start Quiz 🎯", type="primary"):
            st.session_state.quiz_started = True
            st.session_state.current_q = 0
            st.session_state.user_answers = {}
            st.rerun()

    # ===================== INTERACTIVE QUIZ =====================
    if st.session_state.get("quiz_started", False) and "quiz_out" in st.session_state:
        questions = [q.strip() for q in st.session_state.quiz_out.split("\n\n") if q.strip().startswith("Q")]
        
        if st.session_state.current_q < len(questions):
            q_text = questions[st.session_state.current_q]
            st.write(f"**Question {st.session_state.current_q + 1} of {len(questions)}**")
            st.write(q_text)

            options = [line.strip() for line in q_text.split('\n') if line.strip() and line[0].isdigit() and ')' in line]

            selected = st.radio("Choose the correct answer:", options, key=f"q_{st.session_state.current_q}")

            if st.button("Submit Answer & Next ➡️"):
                st.session_state.user_answers[st.session_state.current_q] = selected
                st.session_state.current_q += 1
                st.rerun()
        else:
            st.success("🎉 Quiz Completed! You are a superstar!")
            st.write("### Your Results:")
            correct_count = 0
            for i, q in enumerate(questions):
                user_ans = st.session_state.user_answers.get(i, "Not answered")
                if user_ans and user_ans.startswith(("1)", "2)", "3)", "4)")):
                    correct_count += 1
                    st.success(f"Q{i+1}: ✅")
                else:
                    st.error(f"Q{i+1}: ❌")

            st.metric("Your Final Score", f"{correct_count} / {len(questions)} ⭐")

            if st.button("Try New Topic"):
                for key in ["last_text", "last_image", "last_audio", "quiz_out", "quiz_started", "current_q", "user_answers"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

    if st.button("Logout"):
        save_user_progress()
        supabase.auth.sign_out()
        st.session_state.clear()
        st.rerun()

st.caption("EduMate AI — Updated Image Search | Better Relevance | Persistent Progress")

# Cleanup
if os.path.exists("temp_mic.wav"):
    os.remove("temp_mic.wav")