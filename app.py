import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram_bot import bot

def run_bot():
    print("🤖 Telegram Bot polling started in background...")
    bot.infinity_polling()

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK: Anime Shorts Telegram Bot is running 24/7!")
    
    def log_message(self, format, *args):
        pass  # Suppress excessive health check logs

if __name__ == "__main__":
    # 1. Start Telegram bot in a daemon background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # 2. Start HTTP server on Render's assigned PORT
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Health check server listening on port {port}...")
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()
