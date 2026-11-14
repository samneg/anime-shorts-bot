"""
Anime YouTube Shorts Telegram Bot Agent (Batch & Queue Powered)
Runs 24/7 in the Cloud on Render - 100% Autonomous
"""

import os
import sys
import re
import json
import shutil
import asyncio
import queue
import threading
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
    print("[!] Please set your TELEGRAM_BOT_TOKEN!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
ensure_dirs()

# Job Queue and State
job_queue = queue.Queue()
user_sources = {}
is_worker_running = False


# ==========================================
# Gemini AI Script Generator & Parser
# ==========================================
def generate_script_with_gemini(user_prompt: str) -> tuple[str, str]:
    """Uses Gemini to write a high-retention Shorts script and pick keywords."""
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
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
        return data.get("script", user_prompt), data.get("search_query", "anime")
    except Exception as e:
        print(f"[Gemini] Error: {e}. Using raw text.")
        return user_prompt, "anime"


def parse_batch_file_with_ai(file_content: str) -> list[str]:
    """
    Parses a batch .txt file containing 50+ scripts or topics into a clean list of individual items.
    Uses Gemini AI if available, with robust regex fallbacks.
    """
    # 1. Try with Gemini if API key is present
    if GEMINI_API_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            prompt = (
                f"Analyze this document and extract every separate anime Short script, idea, or topic as a distinct list item.\n\n"
                f"Document text:\n\"\"\"\n{file_content[:15000]}\n\"\"\"\n\n"
                f"Respond with a raw JSON array of strings, one string per short:\n"
                f"[\"script 1...\", \"script 2...\", ...]"
            )
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            parsed = json.loads(response.text)
            if isinstance(parsed, list) and len(parsed) > 0:
                return [s.strip() for s in parsed if len(s.strip()) > 5]
        except Exception as e:
            print(f"[Gemini Batch Parser] Fallback to regex: {e}")

    # 2. Robust Regex Fallbacks (delimiters like 1., 2., ---, or double newlines)
    # Check for separator dashes or hashes
    if "---" in file_content:
        items = [x.strip() for x in file_content.split("---") if len(x.strip()) > 5]
        if items:
            return items

    # Check for numbered lists (e.g. 1. or 1) or #1 )
    numbered = re.split(r'\n\s*(?:\d+[\.\)]|\#\d+)\s*', file_content)
    if len(numbered) > 1:
        items = [x.strip() for x in numbered if len(x.strip()) > 5]
        if items:
            return items

    # Check for paragraph blocks separated by blank lines
    blocks = [x.strip() for x in re.split(r'\n\s*\n', file_content) if len(x.strip()) > 5]
    if len(blocks) > 1:
        return blocks

    # Fallback to lines
    return [line.strip() for line in file_content.splitlines() if len(line.strip()) > 10]


# ==========================================
# Autonomous Queue Worker (No Permission Needed)
# ==========================================
def process_single_video(chat_id: int, prompt: str, current_num: int, total_num: int):
    """Generates and uploads one video, cleaning up disk space immediately."""
    source = user_sources.get(chat_id, "archive")
    status_msg = bot.send_message(
        chat_id,
        f"🎬 *Starting Video [{current_num}/{total_num}]*...\n_\"{prompt[:60]}...\"_",
        parse_mode="Markdown"
    )
    user_temp_dir = f"temp_{chat_id}_{current_num}"
    os.makedirs(user_temp_dir, exist_ok=True)
    
    try:
        # Step 1: Gemini AI Script & Search Query
        script_text, search_query = generate_script_with_gemini(prompt)
        
        # Step 2: Voiceover & Subtitles
        audio_path, srt_path = asyncio.run(generate_speech_and_subs(script_text))
        
        # Step 3: Sourcing Anime Clips
        if source == "sakuga":
            urls = fetch_sakugabooru_clips(search_query, count=4)
        else:
            urls = fetch_internet_archive_clips(search_query, count=4)
            
        if not urls:
            urls = fetch_internet_archive_clips("anime", count=4)
            
        clips = download_or_slice_clips(urls, target_duration_per_clip=3.0, target_count=4)
        
        # Step 4: Render 9:16 Video
        out_filename = f"batch_{chat_id}_{current_num}.mp4"
        final_video = render_youtube_short(clips, audio_path, srt_path, output_filename=out_filename)
        
        # Step 5: Send Video Directly to User
        caption = (
            f"🍿 *Short [{current_num}/{total_num}] Complete!*\n\n"
            f"📝 *Script:*\n\"{script_text}\"\n\n"
            f"• *Format:* 1080x1920 (9:16 Vertical)\n"
            f"• *Queue Status:* {total_num - current_num} remaining"
        )
        with open(final_video, "rb") as video:
            bot.send_video(chat_id, video, caption=caption, parse_mode="Markdown", supports_streaming=True)
            
        # Clean up disk space immediately
        if os.path.exists(final_video):
            os.remove(final_video)
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        print(f"Error on video {current_num}: {e}")
        bot.send_message(chat_id, f"⚠️ *Skipped Video [{current_num}/{total_num}]* due to error: `{str(e)}`\nMoving to next in queue...", parse_mode="Markdown")
        
    finally:
        if os.path.exists(user_temp_dir):
            shutil.rmtree(user_temp_dir, ignore_errors=True)


def queue_worker():
    """Background worker thread that automatically processes all queued shorts without stopping."""
    global is_worker_running
    is_worker_running = True
    print("[Queue] Worker thread started.")
    
    while True:
        try:
            task = job_queue.get()
            if task is None:
                break
                
            chat_id, prompt, current_num, total_num = task
            process_single_video(chat_id, prompt, current_num, total_num)
            job_queue.task_done()
            
            # Send completion notification if this was the last item in a batch
            if current_num == total_num:
                bot.send_message(chat_id, f"🎉 *Batch Complete!* All {total_num} videos have been successfully generated and sent to you!", parse_mode="Markdown")
                
        except Exception as e:
            print(f"[Queue Worker Exception]: {e}")


# Start queue worker on startup
worker_thread = threading.Thread(target=queue_worker, daemon=True)
worker_thread.start()


# ==========================================
# Telegram Bot Message Handlers
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    ai_status = "🟢 *Gemini AI Active*" if GEMINI_API_KEY else "⚪ *Gemini AI Not Configured*"
    welcome_text = (
        f"🎬 *Autonomous Anime Shorts Batch Creator*\n"
        f"{ai_status}\n\n"
        "*How to use:*\n"
        "1. **Send a Single Topic:** Just type e.g. `Goku vs Saitama` and get 1 video.\n"
        "2. **Send a Batch File (50+ Scripts):** Send a `.txt` file containing all your scripts or ideas. "
        "The bot will analyze it, queue all videos, and automatically generate and send them one by one without asking for permission!\n\n"
        "*Commands:*\n"
        "• `/queue` - Check current queue progress\n"
        "• `/clearqueue` - Cancel remaining videos in queue\n"
        "• `/source archive` or `/source sakuga` - Change clip source"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")


@bot.message_handler(commands=['queue'])
def check_queue(message):
    size = job_queue.qsize()
    bot.reply_to(message, f"📊 *Queue Status:* {size} videos waiting to be generated.", parse_mode="Markdown")


@bot.message_handler(commands=['clearqueue'])
def clear_queue(message):
    count = 0
    while not job_queue.empty():
        try:
            job_queue.get_nowait()
            job_queue.task_done()
            count += 1
        except Exception:
            break
    bot.reply_to(message, f"🛑 Cleared {count} pending videos from the queue.", parse_mode="Markdown")


@bot.message_handler(commands=['source'])
def set_source(message):
    args = message.text.split()
    if len(args) > 1 and args[1].lower() in ["archive", "sakuga"]:
        user_sources[message.chat.id] = args[1].lower()
        bot.reply_to(message, f"✅ Clip source set to *{args[1].lower()}*!", parse_mode="Markdown")
    else:
        current = user_sources.get(message.chat.id, "archive")
        bot.reply_to(message, f"Current clip source: *{current}*\nUsage: `/source archive` or `/source sakuga`", parse_mode="Markdown")


# ==========================================
# Batch File Handler (.txt, .md, .csv)
# ==========================================
@bot.message_handler(content_types=['document'])
def handle_batch_file(message):
    doc = message.document
    fname = doc.file_name.lower()
    
    if not fname.endswith(('.txt', '.md', '.csv')):
        bot.reply_to(message, "⚠️ Please upload a `.txt` or `.md` file with your scripts!", parse_mode="Markdown")
        return

    wait_msg = bot.reply_to(message, "📥 *Analyzing your document with Gemini AI...*", parse_mode="Markdown")
    
    try:
        # Download document
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        content = downloaded.decode('utf-8', errors='ignore')
        
        # Parse into scripts
        scripts = parse_batch_file_with_ai(content)
        total = len(scripts)
        
        if total == 0:
            bot.edit_message_text("❌ Could not detect any valid scripts in this file. Please check formatting.", chat_id=message.chat.id, message_id=wait_msg.message_id)
            return

        bot.edit_message_text(
            f"🚀 *Batch Accepted!*\n\n"
            f"• *Detected Scripts:* {total}\n"
            f"• *Status:* Queued for autonomous generation.\n\n"
            f"I will now create and send all {total} videos one by one into this chat without asking for permission. You can put your phone away!",
            chat_id=message.chat.id,
            message_id=wait_msg.message_id,
            parse_mode="Markdown"
        )
        
        # Add all items to the queue
        for idx, s in enumerate(scripts, start=1):
            job_queue.put((message.chat.id, s, idx, total))

    except Exception as e:
        bot.edit_message_text(f"❌ Error reading file: `{str(e)}`", chat_id=message.chat.id, message_id=wait_msg.message_id, parse_mode="Markdown")


# ==========================================
# Single Prompt Handler (Text)
# ==========================================
@bot.message_handler(func=lambda msg: True)
def handle_single_prompt(message):
    text = message.text.strip()
    # Add single prompt as 1-item batch to queue
    job_queue.put((message.chat.id, text, 1, 1))
    queue_size = job_queue.qsize()
    if queue_size > 1:
        bot.reply_to(message, f"📋 Added to queue! ({queue_size} videos currently in queue)", parse_mode="Markdown")


if __name__ == "__main__":
    print("="*60)
    print("🤖 Batch Anime Shorts Telegram Bot is running!")
    print(f"   Gemini AI: {'Connected' if GEMINI_API_KEY else 'Off (Add GEMINI_API_KEY to activate)'}")
    print("="*60)
    bot.infinity_polling()
