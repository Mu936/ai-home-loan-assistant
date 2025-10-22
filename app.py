import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os
import re
from typing import Optional

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    st.set_page_config(page_title="AI Home Loan Assistant", page_icon="🏠")
    st.title("🏠 AI Home Loan Assistant")
    st.warning("OPENAI_API_KEY not found. Please add your API key to the .env file and restart the app.")
    # Continue in offline mode if no API key
    client = None
else:
    client = OpenAI(api_key=api_key)

st.set_page_config(page_title="AI Home Loan Assistant", page_icon="🏠")
st.title("🏠 AI Home Loan Assistant")
st.write("Ask me anything about home loans, interest rates, or the home buying process in South Africa.")

# Sidebar controls
st.sidebar.header("Settings")
offline_mode = st.sidebar.toggle("Offline mode (no API)", value=(client is None))
default_rate = st.sidebar.number_input("Assumed interest rate (%)", min_value=5.0, max_value=25.0, value=11.75, step=0.25)
default_years = st.sidebar.number_input("Bond term (years)", min_value=5, max_value=30, value=20, step=1)
repayment_ratio = st.sidebar.slider("Max repayment as % of gross income", min_value=10, max_value=40, value=30, step=1)


def parse_income_from_text(text: str) -> Optional[float]:
    """Extract a likely monthly income from free text. Returns amount in ZAR if found."""
    if not text:
        return None
    # Look for patterns like R20,000 or 20000 or R 20k
    t = text.lower().replace(",", "")
    # Handle 'k' suffix
    k_match = re.search(r"(r\s*)?(\d+(?:\.\d+)?)\s*k\b", t)
    if k_match:
        try:
            return float(k_match.group(2)) * 1000
        except Exception:
            pass
    # Plain number possibly prefixed by R
    m = re.search(r"(r\s*)?(\d{4,7})(?:\b|\s)", t)
    if m:
        try:
            return float(m.group(2))
        except Exception:
            return None
    return None


def estimate_loan_amount(monthly_income: float, annual_rate_pct: float, years: int, repayment_pct: int) -> Optional[float]:
    """Estimate max loan using annuity formula from an assumed affordable monthly repayment.
    Inputs:
      monthly_income: gross monthly income (ZAR)
      annual_rate_pct: nominal annual interest rate (e.g., 11.75 for 11.75%)
      years: loan term
      repayment_pct: percentage of gross income allocated to repayment (e.g., 30)
    Returns principal estimate (ZAR).
    """
    try:
        affordable_payment = monthly_income * (repayment_pct / 100.0)
        r = (annual_rate_pct / 100.0) / 12.0
        n = years * 12
        if r <= 0:
            return affordable_payment * n
        # PV = Pmt * (1 - (1+r)^-n) / r
        pv = affordable_payment * (1 - (1 + r) ** (-n)) / r
        return max(pv, 0)
    except Exception:
        return None


# User input
user_input = st.text_input("Type your question here:")

if user_input:
    with st.spinner("Thinking..."):
        used_offline = False
        # If offline mode, try local estimation first
        if offline_mode or client is None:
            income = parse_income_from_text(user_input)
            if income:
                est = estimate_loan_amount(income, default_rate, int(default_years), int(repayment_ratio))
                if est:
                    st.success("Estimated Affordability (Offline)")
                    st.write(
                        f"Approximate maximum bond amount: R{est:,.0f}\n\n"
                        f"Assumptions:\n"
                        f"- Gross monthly income: R{income:,.0f}\n"
                        f"- Interest rate: {default_rate:.2f}% p.a.\n"
                        f"- Term: {int(default_years)} years\n"
                        f"- Repayment cap: {int(repayment_ratio)}% of income\n\n"
                        "Tip: Final approval depends on credit score, expenses, and lender criteria."
                    )
                    used_offline = True
            if not used_offline:
                st.info(
                    "Offline mode: I can estimate affordability if you include your monthly income in the question, "
                    "e.g., 'I earn R20,000 per month — how much can I borrow?'"
                )

        # If not in offline mode, or offline didn't handle it, attempt OpenAI
        if not offline_mode and client is not None and not used_offline:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are an expert South African mortgage advisor. Prefer concise, clear answers with SA context."},
                        {"role": "user", "content": user_input}
                    ]
                )
                st.success("Answer:")
                st.write(response.choices[0].message.content)
            except Exception as e:
                # Graceful fallback on API errors
                err_text = str(e)
                quota_err = ("insufficient_quota" in err_text) or ("Error code: 429" in err_text)
                if quota_err:
                    income = parse_income_from_text(user_input)
                    if income:
                        est = estimate_loan_amount(income, default_rate, int(default_years), int(repayment_ratio))
                        if est:
                            st.warning("OpenAI unavailable. Showing offline estimate instead.")
                            st.success("Estimated Affordability (Offline)")
                            st.write(
                                f"Approximate maximum bond amount: R{est:,.0f}\n\n"
                                f"Assumptions:\n"
                                f"- Gross monthly income: R{income:,.0f}\n"
                                f"- Interest rate: {default_rate:.2f}% p.a.\n"
                                f"- Term: {int(default_years)} years\n"
                                f"- Repayment cap: {int(repayment_ratio)}% of income\n\n"
                                "Tip: Final approval depends on credit score, expenses, and lender criteria."
                            )
                        else:
                            st.error(
                                "OpenAI quota exceeded and I couldn't compute an estimate. Try including your monthly income in the question."
                            )
                    else:
                        st.error(
                            "OpenAI quota exceeded. Add billing in your OpenAI account or enable Offline mode in the sidebar "
                            "and include your monthly income for a quick estimate."
                        )
                else:
                    st.error(f"There was an error calling OpenAI: {e}")

# Quick FAQs (works offline)
with st.expander("Common South African home-loan questions (offline)"):
    st.markdown(
        "- Transfer costs: Include transfer duty (if applicable), conveyancer fees, and VAT on services. First-time buyers under certain thresholds may pay reduced duty.\n"
        "- Bond registration costs: Paid to the bank’s appointed conveyancer for registering the bond at the Deeds Office.\n"
        "- Fixed vs variable rate: Fixed gives payment certainty; variable may be cheaper over time but can rise with repo rate. Many lenders offer fixed for 12–24 months.\n"
        "- Typical affordability rule of thumb: Lenders often prefer total debt repayments below ~30% of gross income, but they also consider expenses and credit history.\n"
    )
