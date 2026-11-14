"""
Anime YouTube Shorts Telegram Bot Agent (AI Powered by Google Gemini)
Runs 24/7 in the Cloud on Render - 100% Free
"""

import os
import sys
import json
import shutil
import asyncio
import telebot
from anime_agent import (
    generate_speech_and_subs,
    fetch_internet_archive_clips,
    fetch_sakugabooru_clips,
    download_or_slice_clips,
    render_youtube_short,
    ensure_dirs
)

# 1. Credentials Configuration
DEFAULT_TOKEN = "9090036197:AAGaLKi9cSggbOkhopPBveFm7n7H0eiCAH0"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_TOKEN).strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    print("="*60)
    print(" [!] Please set your TELEGRAM_BOT_TOKEN!")
    print("="*60)
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
ensure_dirs()

# User preferences in memory
user_sources = {}


def generate_script_with_gemini(user_prompt: str) -> tuple[str, str]:
    """
    Uses Google Gemini (gemini-3.8-flash) to write a viral Shorts script
    and extract the best anime clip search keywords.
    """
    if not GEMINI_API_KEY:
        return user_prompt, "anime"
        
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"You are a viral YouTube Shorts writer and anime expert.\n"
            f"The user wants an anime Short based on this topic: \"{user_prompt}\"\n\n"
            f"Return a raw JSON object with:\n"
            f"1. \"script\": A high-retention narration script for a 20-30 second vertical YouTube Short (35-50 words maximum). "
            f"Start with an immediate curiosity hook in the first sentence. Energetic, punchy, easy to understand.\n"
            f"2. \"search_query\": The best 1-3 search keywords for finding public anime video footage (e.g. \"Dragon Ball Goku\", \"Naruto\", \"Bleach\").\n\n"
            f"Respond ONLY with raw JSON:\n"
            f"{{\"script\": \"...\", \"search_query\": \"...\"}}"
        )
        
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        script = data.get("script", user_prompt)
        query = data.get("search_query", "anime")
        print(f"[Gemini] Generated script: {script}")
        print(f"[Gemini] Extracted query: {query}")
        return script, query
    except Exception as e:
        print(f"[Gemini] Error: {e}. Using raw text.")
        return user_prompt, "anime"


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    ai_status = "🟢 *Gemini AI Active*" if GEMINI_API_KEY else "⚪ *Gemini AI Not Configured* (Direct script mode)"
    welcome_text = (
        f"🎬 *AI-Powered Anime YouTube Shorts Creator*\n"
        f"{ai_status}\n\n"
        "Just send me any topic or anime idea, and Gemini will automatically write a viral script, "
        "fetch anime footage, add voiceover, burn subtitles, and generate a *9:16 vertical Short*!\n\n"
        "*Try sending any topic:*\n"
        "• `Why Sukuna respects Yuji`\n"
        "• `Top 3 darkest anime backstories`\n"
        "• `Goku vs Saitama who actually wins?`\n\n"
        "*Settings:*\n"
        "• `/source archive` - Use Internet Archive\n"
        "• `/source sakuga` - Use Sakugabooru action cuts"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")


@bot.message_handler(commands=['source'])
def set_source(message):
    args = message.text.split()
    if len(args) > 1 and args[1].lower() in ["archive", "sakuga"]:
        user_sources[message.chat.id] = args[1].lower()
        bot.reply_to(message, f"✅ Clip source set to *{args[1].lower()}*!", parse_mode="Markdown")
    else:
        current = user_sources.get(message.chat.id, "archive")
        bot.reply_to(message, f"Current clip source: *{current}*\nUsage: `/source archive` or `/source sakuga`", parse_mode="Markdown")


@bot.message_handler(func=lambda msg: True)
def handle_prompt(message):
    user_prompt = message.text.strip()
    chat_id = message.chat.id
    source = user_sources.get(chat_id, "archive")
    
    # 0. Live status
    status = bot.reply_to(message, "🧠 *[1/5]* Gemini AI is drafting your viral Shorts script...", parse_mode="Markdown")
    user_temp_dir = f"temp_{chat_id}"
    os.makedirs(user_temp_dir, exist_ok=True)
    
    try:
        # Step 1: Gemini AI Script & Search Query
        script_text, search_query = generate_script_with_gemini(user_prompt)
        
        # Step 2: Voiceover & Subtitles
        bot.edit_message_text(
            f"🎙️ *[2/5]* Generating voiceover & synced subtitles...\n_\"{script_text[:80]}...\"_",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="Markdown"
        )
        audio_path, srt_path = asyncio.run(generate_speech_and_subs(script_text))
        
        # Step 3: Sourcing Anime Clips
        bot.edit_message_text(
            f"🔍 *[3/5]* Sourcing clips for *'{search_query}'* from *{source}*...",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="Markdown"
        )
        
        if source == "sakuga":
            urls = fetch_sakugabooru_clips(search_query, count=4)
        else:
            urls = fetch_internet_archive_clips(search_query, count=4)
            
        if not urls:
            bot.edit_message_text("❌ Could not retrieve clips from archive. Please try another topic.", chat_id=chat_id, message_id=status.message_id)
            return
            
        clips = download_or_slice_clips(urls, target_duration_per_clip=3.0, target_count=4)
        
        # Step 4: Video Composition (1080x1920)
        bot.edit_message_text(
            "🎬 *[4/5]* Composing 9:16 vertical layout & burning in subtitles...",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="Markdown"
        )
        
        out_filename = f"short_{chat_id}_{message.message_id}.mp4"
        final_video = render_youtube_short(clips, audio_path, srt_path, output_filename=out_filename)
        
        # Step 5: Send Video to User
        bot.edit_message_text("🚀 *[5/5]* Uploading video to Telegram...", chat_id=chat_id, message_id=status.message_id, parse_mode="Markdown")
        
        with open(final_video, "rb") as video:
            caption = (
                f"🍿 *AI-Generated Anime Short*\n\n"
                f"📝 *Script:*\n\"{script_text}\"\n\n"
                f"• *Resolution:* 1080x1920 (9:16 Vertical)\n"
                f"• *Ready for:* YouTube Shorts, TikTok, Reels"
            )
            bot.send_video(chat_id, video, caption=caption, parse_mode="Markdown", supports_streaming=True)
            
        bot.delete_message(chat_id, status.message_id)

    except Exception as e:
        print(f"Error handling message: {e}")
        bot.edit_message_text(f"❌ Error: `{str(e)}`", chat_id=chat_id, message_id=status.message_id, parse_mode="Markdown")
        
    finally:
        if os.path.exists(user_temp_dir):
            shutil.rmtree(user_temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("="*60)
    print("🤖 AI-Powered Anime Shorts Telegram Bot is running!")
    print(f"   Gemini AI: {'Connected' if GEMINI_API_KEY else 'Off (Add GEMINI_API_KEY to activate)'}")
    print("="*60)
    bot.infinity_polling()
