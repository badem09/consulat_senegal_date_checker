import os
import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import locale
import requests
import json

# --- Configuration Mailgun ---
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN")
MAIL_TO = os.environ.get("MAIL_TO")
MAIL_FROM = f"RDV Consulat <mailgun@{MAILGUN_DOMAIN}>"

# --- Locale français pour jours ---
locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')

# --- URL consulat ---
URL = "https://prendrerdv.espacerendezvous.com/rendez_vous/index.html?domain=prendrerdv.espacerendezvous.com&mb=prendrerdv&pro=consulsen"

# --- Stockage local des créneaux déjà vus ---
SLOTS_FILE = "slots_seen.json"

def load_seen_slots():
    """Charge les créneaux déjà vus depuis le fichier local."""
    if os.path.exists(SLOTS_FILE):
        with open(SLOTS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_slots(slots):
    """Sauvegarde les créneaux vus dans le fichier local."""
    with open(SLOTS_FILE, "w") as f:
        json.dump(list(slots), f)

def format_date(ts):
    """Convertit un timestamp en une chaîne de date formatée."""
    dt = datetime.fromtimestamp(int(ts)/1000)
    return dt.strftime("%A %d-%m-%Y")  # Lundi 25-08-2025

async def fetch_slots():
    """Récupère tous les créneaux disponibles depuis le site web."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL)

        # Étape 1 : Prendre un RDV
        await page.click("xpath=//button[contains(., 'Prendre un rendez-vous')]")

        # Étape 2 : Service CNI
        await page.click("xpath=//h4[contains(., 'Service CNI')]/following::button[1]")

        # Étape 3 : Ouvrir le datepicker
        await page.click('xpath=//span[contains(text(), "Recherche à partir d\'une date")]')

        # Étape 4 : Collecter tous les jours disponibles
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
        return sorted(list(available_dates))

def send_mail(subject, body):
    """Envoie un email via l'API Mailgun."""
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN or not MAIL_TO:
        print("⚠️ Mailgun non configuré")
        return

    response = requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_API_KEY),
        data={
            "from": MAIL_FROM,
            "to": MAIL_TO,
            "subject": subject,
            "text": body
        }
    )
    if response.status_code == 200:
        print("📧 Email envoyé avec succès !")
    else:
        print("❌ Erreur envoi email:", response.text)

async def main():
    """Fonction principale pour récupérer, trier et envoyer les créneaux."""
    slots = await fetch_slots()

    # Récupérer les créneaux déjà vus et les sauvegarder
    seen_slots = load_seen_slots()
    new_slots = set(slots) - seen_slots
    save_seen_slots(set(slots))

    # Convertir les timestamps en dates lisibles et créer des listes triées
    all_dates_readable = [format_date(ts) for ts in sorted(slots)]
    new_slots_readable = [format_date(ts) for ts in sorted(list(new_slots))]
    
    # Filtrer et trier les RDV avant le 11 novembre 2025
    limit_date = datetime(2025, 11, 11)
    urgent_slots = [ts for ts in slots if datetime.fromtimestamp(int(ts)/1000) < limit_date]
    urgent_slots_readable = [format_date(ts) for ts in sorted(urgent_slots)]
    
    today = datetime.now()
    send_mail_flag = False
    reason = ""

    # Déterminer la raison de l'envoi
    if new_slots and any(datetime.fromtimestamp(int(ts)/1000) < limit_date for ts in new_slots):
        send_mail_flag = True
        reason = "Nouveaux RDV avant le 11 novembre"
    elif today.weekday() in [0, 2, 4]:  # 0=Lundi, 2=Mercredi, 4=Vendredi
        send_mail_flag = True
        reason = "Récap hebdo programmé"
    
    if send_mail_flag:
        body = f"📅 Tous les créneaux disponibles:\n" + "\n".join(all_dates_readable) + "\n\n"
        if new_slots:
            body += "✨ Nouveaux créneaux:\n" + "\n".join(new_slots_readable) + "\n\n"
        if urgent_slots:
            body += "⚠️ RDV avant le 11 novembre:\n" + "\n".join(urgent_slots_readable) + "\n\n"
        body += f"Raison envoi: {reason}"
        send_mail("Récap RDV CNI", body)
    else:
        print("Aucun email à envoyer aujourd'hui.")

if __name__ == "__main__":
    asyncio.run(main())
