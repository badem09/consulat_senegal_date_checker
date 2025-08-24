import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import json
import os
import smtplib
from email.message import EmailMessage

URL = "https://prendrerdv.espacerendezvous.com/rendez_vous/index.html?domain=prendrerdv.espacerendezvous.com&mb=prendrerdv&pro=consulsen"
STATE_FILE = "slots_state.json"

# --------- Helpers ---------
def ts_to_date(ts):
    return datetime.fromtimestamp(int(ts)/1000).strftime("%Y-%m-%d")

def load_previous_slots():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_slots(slots):
    with open(STATE_FILE, "w") as f:
        json.dump(list(slots), f)

def send_email(subject, body, to_email):
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = os.environ['MAIL_FROM']
    msg['To'] = to_email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(os.environ['MAIL_FROM'], os.environ['MAIL_PASSWORD'])
        smtp.send_message(msg)

# --------- Fetch Slots ---------
async def fetch_slots():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)  # headless=True sur GitHub
        page = await browser.new_page()
        await page.goto(URL)

        # Step 1: Click "Prendre un RDV"
        await page.click("xpath=//button[contains(., 'Prendre un rendez-vous')]")

        # Step 2: Click "Service CNI"
        await page.click("xpath=//h4[contains(., 'Service CNI')]/following::button[1]")

        # Step 3: Open the datepicker
        await page.click('xpath=//span[contains(text(), "Recherche à partir d\'une date")]')

        # Step 4: Collect all available dates
        available_dates = set()
        while True:
            # Get all active days
            days = await page.query_selector_all("//td[contains(@class, 'day') and not(contains(@class, 'disabled'))]")
            for day in days:
                data_date = await day.get_attribute("data-date")
                if data_date:
                    available_dates.add(data_date)

            # Check if the "next" button is disabled
            next_button = await page.query_selector("//th[contains(@class,'next')]")
            classes = await next_button.get_attribute("class")
            if "disabled" in classes:
                break
            else:
                await next_button.click()
                await page.wait_for_timeout(500)  # petit délai pour que le calendrier se recharge

        await browser.close()
        return sorted(available_dates)

# --------- Main ---------
async def main():
    slots = await fetch_slots()
    readable_dates = {ts_to_date(ts) for ts in slots}
    prev_slots = load_previous_slots()
    new_slots = readable_dates - prev_slots

    # Save the current state
    save_slots(readable_dates)

    # Print to console
    print("📅 Tous les créneaux:", sorted(readable_dates))
    print("✨ Nouveaux créneaux:", sorted(new_slots))

    # Send email if configured
    if os.environ.get("MAIL_FROM") and os.environ.get("MAIL_PASSWORD") and os.environ.get("MAIL_TO"):
        body = f"📅 Tous les créneaux: {sorted(readable_dates)}\n\n✨ Nouveaux: {sorted(new_slots)}"
        send_email("Récap RDV CNI", body, os.environ['MAIL_TO'])

if __name__ == "__main__":
    asyncio.run(main())
