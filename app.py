import os
import datetime
import streamlit as st
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Custom CSS for colors and styling ---
st.markdown(
    """
    <style>
    .main > div {
        max-width: 720px;
        margin: auto;
    }
    .stButton > button {
        background-color: #2B6CB0;  /* Indigo blue */
        color: white;
        font-weight: bold;
        border-radius: 6px;
        padding: 10px 20px;
        transition: background-color 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #2C5282;
        color: #CBD5E0;  /* Light gray */
    }
    .stNumberInput > div > div > input {
        border: 2px solid #2B6CB0;
        border-radius: 6px;
        padding: 8px;
        font-weight: 600;
    }
    .stInfo, .stWarning, .stSuccess {
        border-left: 6px solid #2B6CB0 !important;
    }
    h1 {
        color: #2C5282;
        text-align: center;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Google Sheets Setup ---
def log_to_sheets(age_threshold, withdrawn_count, details):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('golden-bonbon-462205-c9-1824a732fad7.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key('1Hhk35eAmzw8cB4N2kXpHOyQ6bLvMPlfmYCKg9y9e0k').sheet1

    timestamp = datetime.datetime.utcnow().isoformat()
    status = f"Withdrawn: {withdrawn_count}"

    # Append summary row first
    sheet.append_row([timestamp, age_threshold, status, ''])

    # Append each withdrawn invite detail on its own row
    for detail in details:
        sheet.append_row([timestamp, age_threshold, '', detail])

# --- Helper to parse age text like "2 weeks ago" ---
def parse_age_to_days(text):
    if not text:
        return 0
    text = text.lower()
    import re
    match = re.search(r'(\d+)', text)
    if not match:
        return 0
    num = int(match.group(1))
    if 'day' in text:
        return num
    if 'week' in text:
        return num * 7
    if 'month' in text:
        return num * 30
    if 'year' in text:
        return num * 365
    return 0

# --- Main withdrawal function ---
def withdraw_invitations(age_threshold=30):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        storage_path = 'state.json'

        context = None
        if os.path.exists(storage_path):
            context = browser.new_context(storage_state=storage_path)
        else:
            context = browser.new_context()

        page = context.new_page()
        page.goto('https://www.linkedin.com/login')

        # If no saved login, ask user to login manually
        if not os.path.exists(storage_path):
            st.info("Please login manually in the opened browser window, then come back here and press Continue.")
            st.write("After logging in, close the browser window or press Continue.")
            if st.button("Continue after Login"):
                context.storage_state(path=storage_path)
                st.success("Login session saved. You can now run withdrawals.")
            else:
                return "Manual login required first."

        # Go to sent invitations page
        page.goto('https://www.linkedin.com/mynetwork/invitation-manager/sent/')
        page.wait_for_selector('li.invitation-card', timeout=30000)

        withdrawn = []
        cards = page.query_selector_all('li.invitation-card')

        for card in cards:
            try:
                # Get invitee name
                name = card.query_selector('span.invitation-card__title').inner_text().strip()
                age_text = card.query_selector('.invitation-card__subtitle').inner_text().lower()
                days = parse_age_to_days(age_text)
            except Exception as e:
                continue

            if days >= age_threshold:
                btn = card.query_selector('button.artdeco-button--tertiary')
                if btn:
                    btn.click()
                    try:
                        page.wait_for_selector('button[data-control-name="withdraw_confirm"]', timeout=5000)
                        page.click('button[data-control-name="withdraw_confirm"]')
                        withdrawn.append(f"{name} (sent {age_text})")
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        withdrawn.append(f"Failed to withdraw {name} (sent {age_text}): {e}")

        context.storage_state(path=storage_path)  # Save updated session
        browser.close()

        # Log results to Google Sheets
        log_to_sheets(age_threshold, len(withdrawn), withdrawn)

        return withdrawn

# --- Streamlit UI ---
st.markdown("<h1>🔗 LinkedIn Invitation Withdrawer</h1>", unsafe_allow_html=True)

age_threshold = st.number_input(
    "Withdraw invitations older than (days):", min_value=1, value=30
)

if st.button("Start Withdrawal"):
    st.write("Starting withdrawal process...")
    results = withdraw_invitations(age_threshold)
    if isinstance(results, str):
        st.warning(results)
    else:
        st.success(f"Withdrawn {len(results)} invitations.")
        for r in results:
            st.write(r)
