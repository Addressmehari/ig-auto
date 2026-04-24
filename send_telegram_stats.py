import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_telegram_message(token, chat_id, message):
    if not token or not chat_id:
        print("Error: BOT_TOKEN or CHAT_ID not found in environment variables.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Stats sent successfully to Telegram!")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")

def main():
    stats_path = "web/data/daily_stats.json"
    
    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Run step1_update_data.py first.")
        return

    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            stats = json.load(f)
            
        message = (
            "<b>📊 GitVille Daily Update</b>\n\n"
            f"👥 <b>Population:</b> {stats['old_active']} → {stats['new_active']}\n"
            f"✨ <b>Newcomers:</b> +{stats['newcomers']}\n"
            f"👋 <b>Left:</b> -{stats['newly_abandoned']}\n"
        )
        
        if stats['newcomer_names_str']:
            message += f"\n🆕 <b>Welcome:</b>\n{stats['newcomer_names_str'].replace(',', ', ')}"

        BOT_TOKEN = os.getenv("BOT_TOKEN")
        CHAT_ID = os.getenv("CHAT_ID")
        
        send_telegram_message(BOT_TOKEN, CHAT_ID, message)
        
    except Exception as e:
        print(f"Error processing stats: {e}")

if __name__ == "__main__":
    main()
