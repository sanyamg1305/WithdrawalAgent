import streamlit as st
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import time

# --- Withdrawer Class ---
class LinkedInWithdrawer:
    def __init__(self):
        self.driver = None
        self.withdrawn_count = 0
        self.max_withdrawals = 80
        self.withdrawn_invites = []

    def setup_driver(self):
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        self.driver = uc.Chrome(options=options)

    def login(self):
        st.info("Opening LinkedIn. Please login manually in the browser window...")
        self.driver.get("https://www.linkedin.com")

        try:
            WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.CLASS_NAME, "global-nav__me"))
            )
            st.success("✅ Login successful!")
            return True
        except TimeoutException:
            st.warning("⏰ Login not detected after timeout. You can still try using the tool.")
            return False

    def export_pending_requests(self):
        self.driver.get("https://www.linkedin.com/mynetwork/invitation-manager/sent/")
        # Wait for at least one invitation card to appear
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"][componentkey^="auto-component-"]'))
            )
        except TimeoutException:
            st.error("❌ Could not find any invitation cards. The LinkedIn UI may have changed or you may not be logged in.")
            st.info("Current page URL: " + self.driver.current_url)
            return None
        time.sleep(2)

        # Find all invitation cards with the new selector
        cards = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"][componentkey^="auto-component-"]')

        pending_requests = []
        for card in cards:
            try:
                # Profile link
                profile_link = card.find_element(By.CSS_SELECTOR, 'a[href*="/in/"]').get_attribute("href")
                # Name
                try:
                    name = card.find_element(By.CSS_SELECTOR, 'a._70f3535c._5c6933d6').text
                except Exception:
                    # fallback: first <a> with /in/ in href
                    name = card.find_element(By.CSS_SELECTOR, 'a[href*="/in/"]').text
                # Headline (the second <p> tag)
                ps = card.find_elements(By.TAG_NAME, "p")
                headline = ps[1].text if len(ps) > 1 else ""
                # Time sent (the <p> containing 'Sent')
                time_sent = ""
                for p in ps:
                    if "Sent" in p.text:
                        time_sent = p.text
                        break
                pending_requests.append({
                    'profile_link': profile_link,
                    'name': name,
                    'headline': headline,
                    'time_sent': time_sent
                })
            except Exception as e:
                continue

        df = pd.DataFrame(pending_requests)
        csv_filename = f"pending_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(csv_filename, index=False)
        return csv_filename

    def withdraw_specific_requests(self, urls_to_withdraw, names_to_withdraw=None):
        st.info("Navigating to LinkedIn's Sent Invitations page...")
        self.driver.get("https://www.linkedin.com/mynetwork/invitation-manager/sent/")
        # Wait for at least one invitation card to appear (new selector)
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"][componentkey^="auto-component-"]'))
        )
        time.sleep(3) # Give page some time to load initial invitations

        initial_withdrawal_count = self.withdrawn_count
        processed_urls = set() # To keep track of URLs already attempted
        urls_to_process = set(urls_to_withdraw) # Convert to set for faster lookup and modification
        
        # Also prepare names for matching if provided
        names_to_process = set()
        if names_to_withdraw:
            names_to_process = set([name.strip().lower() for name in names_to_withdraw if name])

        scroll_attempts = 0
        max_scroll_attempts = 50 # Max scrolls to load all invites
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        st.info(f"Starting withdrawal process for {len(urls_to_process)} URLs...")
        if names_to_process:
            st.info(f"Also matching against {len(names_to_process)} names: {list(names_to_process)[:5]}...")

        while urls_to_process and scroll_attempts < max_scroll_attempts:
            # Find all currently visible invitation cards (new selector)
            invitation_cards = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"][componentkey^="auto-component-"]')
            
            found_new_cards_in_scroll = False
            for card in invitation_cards:
                try:
                    profile_link_element = card.find_element(By.CSS_SELECTOR, 'a[href*="/in/"]')
                    profile_link = profile_link_element.get_attribute("href")
                    
                    # Get name for debugging and potential matching
                    try:
                        name = card.find_element(By.CSS_SELECTOR, 'a._70f3535c._5c6933d6').text.strip()
                    except NoSuchElementException:
                        name = "Unknown"
                    
                    # Check if this card should be processed
                    should_process = False
                    match_reason = ""
                    
                    # First try URL matching
                    if profile_link in urls_to_process and profile_link not in processed_urls:
                        should_process = True
                        match_reason = f"URL match: {profile_link}"
                    # Fallback to name matching if URL not found
                    elif names_to_process and name.lower() in names_to_process and profile_link not in processed_urls:
                        should_process = True
                        match_reason = f"Name match: {name}"
                    
                    if should_process:
                        found_new_cards_in_scroll = True
                        st.info(f"🎯 Found target invite: {name} - {match_reason}")
                        
                        # Debug: Show what we're looking for vs what we found
                        st.info(f"   Profile link: {profile_link}")
                        st.info(f"   Name: {name}")
                        if profile_link in urls_to_process:
                            st.info(f"   ✅ URL is in target list")
                        if names_to_process and name.lower() in names_to_process:
                            st.info(f"   ✅ Name is in target list")

                        # Find the withdraw button within this specific invitation card (new selector)
                        try:
                            withdraw_button = WebDriverWait(card, 5).until(
                                EC.element_to_be_clickable((
                                    By.XPATH, ".//button[span[contains(text(), 'Withdraw')]]"
                                ))
                            )
                        except TimeoutException:
                            # Fallback to CSS selector if needed
                            try:
                                withdraw_button = card.find_element(By.CSS_SELECTOR, 'button[data-view-name="sent-invitations-withdraw-single"]')
                            except Exception:
                                st.warning(f"❌ Could not find Withdraw button for {name}. Skipping.")
                                continue

                        withdraw_button.click()
                        st.success(f"✅ Successfully clicked withdraw for {name} ({profile_link})")

                        # Step 2: Handle the confirmation modal (new LinkedIn UI)
                        try:
                            # Wait for the confirmation dialog to appear and click the correct Withdraw button
                            confirm_withdraw_button = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((
                                    By.XPATH,
                                    "//dialog[contains(@aria-label, 'Withdraw invitation')]//button[span//span[contains(text(), 'Withdraw')]]"
                                ))
                            )
                            confirm_withdraw_button.click()
                            st.success(f"✅ Confirmed withdrawal for {name}")
                            time.sleep(2)  # Give time for modal to close and action to process
                        except TimeoutException:
                            st.warning(f"❌ Withdrawal confirmation modal/button not found for {name}. Skipping confirmation.")
                            # Attempt to close any modal if it's stuck, to continue with next invites
                            try:
                                cancel_button = self.driver.find_element(By.XPATH, "//dialog[contains(@aria-label, 'Withdraw invitation')]//button[span//span[contains(text(), 'Cancel')]]")
                                cancel_button.click()
                                st.info("Attempted to close a blocking modal.")
                                time.sleep(1)
                            except:
                                pass
                        except Exception as e:
                            st.error(f"Error confirming withdrawal for {name}: {str(e)}")
                            # Attempt to close any modal if it's stuck
                            try:
                                cancel_button = self.driver.find_element(By.XPATH, "//dialog[contains(@aria-label, 'Withdraw invitation')]//button[span//span[contains(text(), 'Cancel')]]")
                                cancel_button.click()
                                st.info("Attempted to close a blocking modal.")
                                time.sleep(1)
                            except:
                                pass

                        # Ensure the modal is closed before proceeding
                        WebDriverWait(self.driver, 10).until(
                            EC.invisibility_of_element_located((By.XPATH, "//div[@data-test-modal-container and @data-test-is-confirm-dialog]"))
                        )
                        st.info("Modal is no longer visible.")

                        # Add to withdrawn list and mark as processed
                        self.withdrawn_invites.append({
                            'name': name,
                            'headline': headline,
                            'time': datetime.now().isoformat(),
                            'profile_link': profile_link
                        })
                        self.withdrawn_count += 1
                        processed_urls.add(profile_link)
                        
                        # Remove from both URL and name sets
                        if profile_link in urls_to_process:
                            urls_to_process.remove(profile_link)
                        if names_to_process and name.lower() in names_to_process:
                            names_to_process.remove(name.lower())
                            
                        st.info(f"Remaining URLs to withdraw: {len(urls_to_process)}")
                        if names_to_process:
                            st.info(f"Remaining names to withdraw: {len(names_to_process)}")

                        # Scroll the processed card out of view to avoid re-processing or issues with layout
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", card)
                        time.sleep(1) # Small pause

                except (TimeoutException, NoSuchElementException) as e:
                    # This card might not be a target, or its elements are not found
                    pass # Do not log loudly for every non-target card
                except Exception as e:
                    st.error(f"An unexpected error occurred while inspecting card: {str(e)}")
                    # No need to break, continue trying other cards

            # After checking all visible cards, scroll down
            if not urls_to_process and not names_to_process: # If all targets are processed, break early
                st.info("All target URLs and names processed or attempted.")
                break

            st.info(f"Scrolling down to load more invites... (scroll attempt {scroll_attempts + 1}/{max_scroll_attempts})")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3) # Give time for new content to load

            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height and not found_new_cards_in_scroll: # Stop if no new content and no new cards processed in this scroll
                st.info("Reached end of scrollable content and no new target invites found.")
                break
            last_height = new_height
            scroll_attempts += 1

        if self.withdrawn_count == initial_withdrawal_count:
            st.info("No new invitations were withdrawn in this batch.")
        else:
            st.success(f"Completed withdrawal attempts. Total withdrawn in this session: {self.withdrawn_count - initial_withdrawal_count}")

        if urls_to_process:
            st.warning(f"Could not withdraw {len(urls_to_process)} invites by URL. Remaining URLs: {list(urls_to_process)[:5]}...")
        if names_to_process:
            st.warning(f"Could not withdraw {len(names_to_process)} invites by name. Remaining names: {list(names_to_process)[:5]}...")

    def close(self):
        if self.driver:
            self.driver.quit()

# --- Streamlit UI ---
st.set_page_config(page_title="LinkedIn Invite Withdrawer", layout="centered")
st.title("🔗 LinkedIn Invite Withdraw Tool")

# Initialize bot if needed
if 'bot' not in st.session_state:
    st.session_state.bot = LinkedInWithdrawer()
    st.session_state.bot.setup_driver()
    st.session_state.login_attempted = False
    st.session_state.logged_in = False

# Manual login initiation
if not st.session_state.login_attempted:
    if st.button("🔓 Start Manual Login"):
        st.session_state.login_attempted = True
        with st.spinner("Waiting for you to login manually..."):
            st.session_state.logged_in = st.session_state.bot.login()

# Step 1: Export
st.markdown("### Step 1: Export pending invites")
if st.button("🔍 Export Now"):
    with st.spinner("Fetching pending invites..."):
        filename = st.session_state.bot.export_pending_requests()
        with open(filename, "rb") as f:
            csv_data = f.read()
        st.download_button("📥 Download Exported CSV", csv_data, file_name=filename, mime='text/csv')

# Step 2: Upload filtered CSV
st.markdown("### Step 2: Upload filtered CSV to Withdraw")
uploaded_file = st.file_uploader("Upload filtered CSV (with profile_link column)", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    st.write(df)
    
    # Extract both URLs and names for matching
    urls_to_withdraw = df['profile_link'].dropna().tolist()
    names_to_withdraw = df['name'].dropna().tolist() if 'name' in df.columns else None
    
    st.info(f"Found {len(urls_to_withdraw)} URLs to withdraw")
    if names_to_withdraw:
        st.info(f"Found {len(names_to_withdraw)} names to withdraw")

    if st.button("🚫 Start Withdrawals"):
        with st.spinner("Withdrawing invites..."):
            st.session_state.bot.withdraw_specific_requests(urls_to_withdraw, names_to_withdraw)
        st.success(f"✅ Done! Withdrawn {len(st.session_state.bot.withdrawn_invites)} invites.")

        for invite in st.session_state.bot.withdrawn_invites:
            st.markdown(f"""
            - **{invite['name']}**  
              {invite['headline']}  
              Withdrawn: {invite['time']}  
              [🔗 Profile]({invite['profile_link']})
            """)

# Step 3: Close browser session
st.markdown("### Step 3: Close Browser")
if st.button("❌ Close Session"):
    st.session_state.bot.close()
    st.success("Closed browser session.")
