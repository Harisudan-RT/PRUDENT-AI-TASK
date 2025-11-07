import os
import json
import tempfile
import pdfplumber
import pytesseract
from PIL import Image
import streamlit as st
from google import genai


# MY GEMINI API KEY

os.environ["GEMINI_API_KEY"] = "AIzaSyD09t9R197Mb6NPP-xD21tukd03iEmPtL8"

try:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
except Exception as e:
    client = None

# MOCK DATA FOR TEST MODE WHICH TO REPRESENT DURING OFFLINE
MOCK_OUTPUT = {
    "fields": {
        "account_info": {
            "bank_name": "Axis Bank",
            "account_holder": "Harisudan R T",
            "account_number_masked": "XXXXXXX7",
            "statement_period_start": "2019-02-01",
            "statement_period_end": "2019-03-01",
            "account_type": "Checking"
        },
        "summary": {
            "opening_balance": 40000.0,
            "closing_balance": 44079.83,
            "total_credits": 5474.0,
            "total_debits": 1395.17,
            "average_daily_balance": None,
            "overdraft_count": None,
            "nsf_count": None,
            "currency": "INR"
        },
        "transactions": [
            {"date": "2019-02-01", "description": "Card payment - High St Petrol Station", "amount": -24.5, "balance": 39975.5, "category": "Fuel"},
            {"date": "2019-02-04", "description": "Job BiWeekly Payment", "amount": 2575.0, "balance": 42500.5, "category": "Income"},
            {"date": "2019-02-28", "description": "Monthly Apartment Rent", "amount": -987.33, "balance": 44079.83, "category": "Housing"}
        ]
    },
    "insights": [
        "Your account balance increased by ₹4,079.83 in February 2019.",
        "Main income source: 'Job' with two biweekly payments totaling ₹5,150.",
        "Largest expense: Monthly Apartment Rent (₹987.33).",
        "Spending categories: Housing, Fuel, Food, Insurance, Shopping.",
    ],
    "quality": {"ocr_used": False, "warnings": [], "mock_mode": True}
}

# HELPER FUNCTIONS

def extract_text_from_pdf(file_path):
    """Extract text from PDF (OCR if needed)."""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if not page_text:
                image = page.to_image(resolution=300).original
                text += pytesseract.image_to_string(image)
            else:
                text += page_text
    return text.strip()

def extract_text_from_image(file_path):
    """Extract text from image using OCR."""
    return pytesseract.image_to_string(Image.open(file_path)).strip()

def safe_json_parse(text):
    """Try to parse JSON, fallback to plain text inside list."""
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception:
        return {"insights": [line.strip() for line in clean.splitlines() if line.strip()]}

def get_gemini_json(prompt_text):
    """Send text to Gemini and safely parse as JSON."""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt_text,
        )
        raw_text = response.text.strip()
        return safe_json_parse(raw_text)
    except Exception as e:
        return {"error": f"Extraction parse failed: {str(e)}"}

def normalize_output(raw_json):
    """Ensure all outputs follow consistent schema."""
    if "fields" in raw_json:
        return raw_json
    else:
        return {"fields": raw_json}

def process_bank_statement(file_path: str, test_mode: bool = False):
    """Main parser — OCR + Gemini + insights pipeline."""
    if test_mode:
        return MOCK_OUTPUT

    if not client:
        return {"error": "Gemini client not initialized. Check GEMINI_API_KEY."}

    # Step 1 — Extract text
    if file_path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    else:
        text = extract_text_from_image(file_path)

    # Step 2 — Gemini Extraction
    extraction_prompt = f"""
You are a financial document parser. Extract this data in strict JSON.

fields:
  account_info:
    bank_name
    account_holder
    account_number_masked
    statement_period_start
    statement_period_end
    account_type
  summary:
    opening_balance
    closing_balance
    total_credits
    total_debits
    average_daily_balance
    overdraft_count
    nsf_count
    currency
  transactions:
    - date
      description
      amount
      balance
      category

Input:
{text}
"""
    extraction_json = normalize_output(get_gemini_json(extraction_prompt))

    # Step 3 — Insights
    insight_prompt = f"""
Given this bank statement data, generate concise bullet-style financial insights:
{json.dumps(extraction_json, indent=2)}
"""
    insights_json = get_gemini_json(insight_prompt)

    # Step 4 — Combine
    return {
        "fields": extraction_json.get("fields", {}),
        "insights": insights_json.get("insights", []),
        "quality": {
            "text_length": len(text),
            "raw_extraction_response": json.dumps(extraction_json, indent=2),
            "raw_insights_response": json.dumps(insights_json, indent=2),
        },
    }

# STREAMLIT UI

st.set_page_config(page_title="Bank Statement Parser (Gemini)", layout="wide", page_icon="🏦")

st.title("🏦 Bank Statement Parser using Gemini AI")
st.caption("Upload a bank statement (PDF or image) to extract key details and insights.")

colA, colB = st.columns([3, 1])
uploaded_file = colA.file_uploader("📂 Upload Bank Statement", type=["pdf", "png", "jpg", "jpeg"])
test_mode = colB.toggle("🧪 Test Mode", value=False, help="Use sample data, skip API calls")

if uploaded_file or test_mode:
    with st.spinner("⏳ Processing your bank statement..."):
        if test_mode:
            output = process_bank_statement(file_path="", test_mode=True)
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[-1]) as tmp:
                tmp.write(uploaded_file.read())
                output = process_bank_statement(tmp.name)

    st.success("✅ Extraction Complete!")

    # Extracted Fields
    st.markdown("### 📋 Extracted Fields")
    fields = output.get("fields", {})
    if fields:
        col1, col2 = st.columns(2)
        acc_info = fields.get("account_info", {})
        summary = fields.get("summary", {})
        txns = fields.get("transactions", [])

        with col1:
            st.markdown("#### 🏛 Account Info")
            st.json(acc_info)
        with col2:
            st.markdown("#### 💰 Summary")
            st.json(summary)

        if txns:
            st.markdown("#### 🧾 Transactions")
            st.dataframe(txns, use_container_width=True)
    else:
        st.warning("No structured fields extracted.")

    # Insights
    insights = output.get("insights", [])
    if insights:
        st.markdown("### 💡 Financial Insights")
        for i, point in enumerate(insights, start=1):
            st.markdown(f"{i}. {point}")
    else:
        st.info("No insights generated.")

    # --- Quality Info ---
    with st.expander("🧩 Quality & Debug Info"):
        st.json(output.get("quality", {}))
else:
    st.info("👆 Upload a statement or enable Test Mode to start.")
