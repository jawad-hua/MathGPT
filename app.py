import streamlit as st
from groq import Groq
import os
import numpy as np
import pytesseract
import cv2
import re
import base64
from io import BytesIO
from PIL import Image

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="MathGPT – AI Math Solver", page_icon="🧮", layout="wide")

# ─── API Setup ───────────────────────────────────────────────────────────────
# Streamlit Cloud mein st.secrets se key aayegi, local env se os.getenv
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    st.error("API Key missing! Please set GROQ_API_KEY in your environment or secrets.toml")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# Tesseract path for local Linux. On Streamlit Cloud, it usually works without specifying the path 
# if installed via packages.txt, but keeping the default fallback is fine.
# pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract" 

# ─── Models ──────────────────────────────────────────────────────────────────
TEXT_MODEL   = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # Note: Updated to a supported Groq vision model name

# ─── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are MathGPT, an expert AI math tutor and solver.
Your ONLY job is to solve mathematical problems.
Rules:
- If the question is NOT math-related, respond: "I am designed only to solve math problems."
- Always solve step by step with clear explanations.
- Show each step on a new line.
- For equations: show the final answer clearly at the end.
- For word problems: first identify variables, then solve.
- Support: algebra, calculus, geometry, trigonometry, statistics, arithmetic, and more.
- Use plain text formatting, keep it readable."""

# ─── Math Detection ──────────────────────────────────────────────────────────
def is_math(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    patterns = [
        r'\d', r'[+\-*/=^%]', 
        r'\b(solve|find|calculate|compute|evaluate|simplify|differentiate|integrate|prove|factor)\b',
        r'\b(equation|formula|derivative|integral|limit|matrix|vector|angle|triangle|circle)\b',
        r'\b(x|y|z|sin|cos|tan|log|ln|sqrt|root)\b',
        r'[√∫∑π∞≤≥≠²³]', 
        r'\b(plus|minus|times|divide|squared|cubed|percent)\b',
    ]
    for p in patterns:
        if re.search(p, text_lower):
            return True
    return False

# ─── PIL Image → Base64 ───────────────────────────────────────────────────────
def pil_to_base64(pil_image: Image.Image) -> str:
    buffered = BytesIO()
    if pil_image.mode in ("RGBA", "P"):
        pil_image = pil_image.convert("RGB")
    pil_image.save(buffered, format="JPEG", quality=95)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# ─── Image Preprocessing & OCR ───────────────────────────────────────────────
def preprocess_for_ocr(pil_image: Image.Image) -> np.ndarray:
    img = np.array(pil_image)
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img
    scale = 2
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.fastNlMeansDenoising(gray, h=30)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    return thresh

def extract_text_ocr(pil_image: Image.Image) -> str:
    try:
        processed = preprocess_for_ocr(pil_image)
        configs = ["--psm 6 --oem 3", "--psm 11 --oem 3", "--psm 3 --oem 3"]
        best_text = ""
        for cfg in configs:
            text = pytesseract.image_to_string(processed, config=cfg).strip()
            if len(text) > len(best_text):
                best_text = text
        return best_text
    except Exception:
        return ""

# ─── Solvers ─────────────────────────────────────────────────────────────────
def solve_text(question: str) -> str:
    try:
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}
            ],
            temperature=0.1,
            max_tokens=1500
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"❌ Error: {e}"

def solve_image_vision(pil_image: Image.Image) -> str:
    try:
        b64 = pil_to_base64(pil_image)
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Look at this image carefully. If it contains a math problem, solve it step by step. If it does not contain math, say: 'I am designed only to solve math problems.'"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=1500
        )
        return completion.choices[0].message.content
    except Exception as vision_error:
        extracted = extract_text_ocr(pil_image)
        if extracted and is_math(extracted):
            result = solve_text(f"Solve this math problem:\n{extracted}")
            return f"📷 OCR Extracted:\n{extracted}\n\n📐 Solution:\n{result}"
        elif extracted:
            return f"📷 OCR Extracted text:\n{extracted}\n\n⚠️ This doesn't appear to be a math problem."
        else:
            return f"❌ Vision model error: {vision_error}\n⚠️ OCR also couldn't read the image. Please try a clearer image or type the question manually."

# ─── UI Layout ───────────────────────────────────────────────────────────────
st.title("🧮 MathGPT — Professional AI Math Solver")
st.markdown("**Supports:** Algebra · Calculus · Geometry · Trigonometry · Statistics · Arithmetic")
st.markdown("---")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input")
    user_text = st.text_area("✏️ Type Your Math Question", placeholder="e.g. Solve 2x + 5 = 15 | Integrate x² dx", height=150)
    uploaded_file = st.file_uploader("📷 Or Upload a Math Image (optional)", type=["png", "jpg", "jpeg"])
    
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        submit_btn = st.button("🔍 Solve", type="primary", use_container_width=True)
    with col_btn2:
        if st.button("🗑️ Clear", use_container_width=True):
            st.rerun()

with col2:
    st.subheader("📐 Solution")
    result_container = st.empty()
    
    if submit_btn:
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            with st.spinner("Analyzing image and solving..."):
                result = solve_image_vision(image)
                result_container.markdown(result)
        elif user_text.strip():
            if is_math(user_text):
                with st.spinner("Solving math problem..."):
                    result = solve_text(user_text)
                    result_container.markdown(result)
            else:
                result_container.warning("🤖 I am designed only to solve math problems. Please enter a math question.")
        else:
            result_container.info("⚠️ Please enter a math question or upload an image.")

st.markdown("---")
st.markdown("<center><small>© 2026 MathGPT. All Rights Reserved.</small></center>", unsafe_allow_html=True)