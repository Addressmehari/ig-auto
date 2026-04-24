import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_telegram_video(token, chat_id, video_path):
    if not token or not chat_id:
        print("Error: BOT_TOKEN or CHAT_ID not found in environment variables.")
        return

    if not os.path.exists(video_path):
        print(f"Error: Video file {video_path} not found.")
        return

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    print(f"📤 Uploading {video_path} to Telegram (this may take a moment)...")
    
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            payload = {
                "chat_id": chat_id,
                "caption": "🎬 Your daily GitVille video is ready!"
            }
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            print("✅ Video sent successfully to Telegram!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending video: {e}")

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    VIDEO_PATH = "final_video.mp4"
    
    send_telegram_video(BOT_TOKEN, CHAT_ID, VIDEO_PATH)
