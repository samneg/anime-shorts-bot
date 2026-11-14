"""
Anime YouTube Shorts Telegram Bot Agent
Runs 24/7 in the Cloud - 100% Free - Zero PC Required
"""

import os
import sys
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

# 1. Bot Token Configuration
DEFAULT_TOKEN = "9090036197:AAGaLKi9cSggbOkhopPBveFm7n7H0eiCAH0"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_TOKEN).strip()

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    print("="*60)
    print(" [!] Please set your TELEGRAM_BOT_TOKEN to start the bot!")
    print("     1. Open Telegram on your phone and search for @BotFather")
    print("     2. Send /newbot, name it, and copy the HTTP API Token")
    print("     3. In terminal run: ")
    print("        $env:TELEGRAM_BOT_TOKEN=\"your_token_here\"")
    print("        python telegram_bot.py")
    print("="*60)
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
ensure_dirs()

# User preferences in memory (default to internet archive)
user_sources = {}


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "🎬 *Anime YouTube Shorts Creator Bot*\n\n"
        "Send me any script or anime fact, and I will automatically generate "
        "a ready-to-upload *9:16 vertical YouTube Short* with voiceover and animated subtitles!\n\n"
        "*Quick Commands:*\n"
        "• `/source archive` - Use vintage & classic anime from Internet Archive\n"
        "• `/source sakuga` - Use high-action animation cuts from Sakugabooru\n\n"
        "*Try sending this now:*\n"
        "_Did you know why Gojo Satoru covers his eyes? The Six Eyes give him atomic-level cursed energy vision, so his brain overheats if he leaves them open!_"
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
def handle_script(message):
    script_text = message.text.strip()
    
    if len(script_text) < 10:
        bot.reply_to(message, "⚠️ Script is too short! Please provide at least 15-20 words for a proper Short.")
        return

    chat_id = message.chat.id
    source = user_sources.get(chat_id, "archive")
    
    # Send live status message
    status = bot.reply_to(message, "⏳ *[1/4]* Generating neural voiceover & synced subtitles...", parse_mode="Markdown")
    
    user_temp_dir = f"temp_{chat_id}"
    os.makedirs(user_temp_dir, exist_ok=True)
    
    try:
        # 1. Voice & Subtitles
        audio_path, srt_path = asyncio.run(generate_speech_and_subs(script_text))
        
        # 2. Source Anime Clips
        bot.edit_message_text(
            f"🔍 *[2/4]* Sourcing anime cuts from *{source}*...",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="Markdown"
        )
        
        if source == "sakuga":
            urls = fetch_sakugabooru_clips("fighting", count=4)
        else:
            urls = fetch_internet_archive_clips("anime", count=4)
            
        if not urls:
            bot.edit_message_text("❌ Could not retrieve anime clips from public archive. Please try again in a moment.", chat_id=chat_id, message_id=status.message_id)
            return
            
        clips = download_or_slice_clips(urls, target_duration_per_clip=3.0, target_count=4)
        
        # 3. Render 9:16 Video
        bot.edit_message_text(
            "🎬 *[3/4]* Composing 1080x1920 layout & burning in subtitles...",
            chat_id=chat_id,
            message_id=status.message_id,
            parse_mode="Markdown"
        )
        
        out_filename = f"short_{chat_id}_{message.message_id}.mp4"
        final_video = render_youtube_short(clips, audio_path, srt_path, output_filename=out_filename)
        
        # 4. Upload to Telegram
        bot.edit_message_text("🚀 *[4/4]* Uploading finished Short to Telegram...", chat_id=chat_id, message_id=status.message_id, parse_mode="Markdown")
        
        with open(final_video, "rb") as video:
            caption = (
                "🍿 *Your Anime Short is Ready!*\n\n"
                "• *Format:* 1080x1920 (9:16 Vertical)\n"
                "• *Subtitles:* Synced & Burned-in\n"
                "• Ready for YouTube Shorts, TikTok, and Reels."
            )
            bot.send_video(chat_id, video, caption=caption, parse_mode="Markdown", supports_streaming=True)
            
        # Clean up status message
        bot.delete_message(chat_id, status.message_id)

    except Exception as e:
        print(f"Error handling message: {e}")
        bot.edit_message_text(f"❌ Error generating video: `{str(e)}`", chat_id=chat_id, message_id=status.message_id, parse_mode="Markdown")
        
    finally:
        # Cleanup temporary files
        if os.path.exists(user_temp_dir):
            shutil.rmtree(user_temp_dir, ignore_errors=True)


if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN == "DUMMY_TOKEN":
        print("="*60)
        print(" [!] Please set your TELEGRAM_BOT_TOKEN first!")
        print("     1. Open Telegram and search for @BotFather")
        print("     2. Send /newbot and copy the HTTP API Token")
        print("     3. Run: $env:TELEGRAM_BOT_TOKEN=\"your_token\"; python telegram_bot.py")
        print("="*60)
        sys.exit(1)
        
    print("="*60)
    print("🤖 Anime Shorts Telegram Bot is running!")
    print("   Open Telegram on your phone and send a message to your bot.")
    print("="*60)
    bot.infinity_polling()
