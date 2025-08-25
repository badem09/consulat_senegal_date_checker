import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import os
import requests

URL = "https://prendrerdv.espacerendezvous.com/rendez_vous/index.html?domain=prendrerdv.espacerendezvous.com&mb=prendrerdv&pro=consulsen"
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY")
MAIL_TO = os.environ.get("MAIL_TO")

# limite pour RDV urgents
limit_date = datetime.strptime("11-11-2025", "%d-%m-%Y")

jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

def format_date(ts):
    dt = datetime.fromtimestamp(int(ts)/1000)
    jour = jours_fr[dt.weekday()]
    return f"{jour} {dt.day:02d}-{dt.month:02d}-{dt.year}"

def send_email(subject, body, to):
    url = f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages"
    response = requests.post(
        url,
        auth=("api", MAILGUN_API_KEY),
        data={"from": f"RDV CNI <mailgun@{MAILGUN_DOMAIN}>",
              "to": [to],
              "subject": subject,
              "text": body}
    )
    if response.status_code == 200:
        print("📧 Email envoyé avec succès !")
    else:
        print("❌ Erreur email:", response.text)

async def fetch_slots():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL)

        await page.click("xpath=//button[contains(., 'Prendre un rendez-vous')]")
        await page.click("xpath=//h4[contains(., 'Service CNI')]/following::button[1]")
        await page.click('xpath=//span[contains(text(), "Recherche à partir d\'une date")]')

        available_dates = set()
        while True:
            days = await page.query_selector_all("//td[contains(@class, 'day') and not(contains(@class, 'disabled'))]")
            for day in days:
                data_date = await day.get_attribute("data-date")
                available_dates.add(data_date)

            next_button = await page.query_selector("//th[contains(@class,'next')]")
            classes = await next_button.get_attribute("class")
            if "disabled" in classes:
                break
            else:
                await next_button.click()
                await page.wait_for_timeout(500)

        await browser.close()
        # tri correct des timestamps
        return sorted(available_dates, key=lambda x: int(x))

async def main():
    slots = await fetch_slots()
    readable_dates = [format_date(ts) for ts in slots]

    # RDV urgents avant 11 nov
    urgent_slots = [d for d in readable_dates if datetime.strptime(d.split()[1], "%d-%m-%Y") < limit_date]

    # check nouveaux créneaux stockés
    stored_file = "slots.txt"
    if os.path.exists(stored_file):
        with open(stored_file, "r") as f:
            old_slots = set(f.read().splitlines())
    else:
        old_slots = set()

    new_slots = set(readable_dates) - old_slots

    # enregistrer les slots pour next run
    with open(stored_file, "w") as f:
        f.write("\n".join(readable_dates))

    # tri alphabétique par date réelle pour email
    def sort_key(d):
        return datetime.strptime(d.split()[1], "%d-%m-%Y")

    if urgent_slots:
        body = f"⚠️ RDV urgents avant le 11 novembre:\n" + "\n".join(sorted(urgent_slots, key=sort_key)) + "\n\n✨ Nouveaux créneaux:\n" + "\n".join(sorted(new_slots, key=sort_key))
    else:
        body = f"✨ Nouveaux créneaux:\n" + "\n".join(sorted(new_slots, key=sort_key))

    print(body)

    if MAILGUN_DOMAIN and MAILGUN_API_KEY and MAIL_TO:
        send_email("Récap RDV CNI", body, MAIL_TO)

if __name__ == "__main__":
    asyncio.run(main())
