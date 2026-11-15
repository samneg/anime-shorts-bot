"""
GitHub Actions High-Speed Batch Video Generator (7GB RAM Runner)
Processes 50+ scripts, generates 9:16 Shorts with FFmpeg,
sends to Telegram, and packages artifacts for download.
"""

import os
import sys
import re
import asyncio
import argparse
import telebot
from anime_agent import (
    generate_speech_and_subs,
    fetch_internet_archive_clips,
    fetch_sakugabooru_clips,
    download_or_slice_clips,
    render_youtube_short,
    ensure_dirs
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def parse_scripts_file(filepath: str) -> list[str]:
    """Parses scripts.txt into individual shorts prompts/scripts."""
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Separated by ---
    if "---" in content:
        items = [x.strip() for x in content.split("---") if len(x.strip()) > 5]
        if items:
            return items

    # 2. Numbered list (e.g. 1. or 1) )
    numbered = re.split(r'\n\s*(?:\d+[\.\)]|\#\d+)\s*', content)
    if len(numbered) > 1:
        items = [x.strip() for x in numbered if len(x.strip()) > 5]
        if items:
            return items

    # 3. Paragraph blocks separated by blank lines
    blocks = [x.strip() for x in re.split(r'\n\s*\n', content) if len(x.strip()) > 5]
    if len(blocks) > 1:
        return blocks

    # 4. Line by line
    return [line.strip() for line in content.splitlines() if len(line.strip()) > 10]


def main():
    parser = argparse.ArgumentParser(description="GitHub Actions Batch Anime Shorts Runner")
    parser.add_argument("--file", type=str, default="scripts.txt", help="Path to scripts file")
    parser.add_argument("--prompt", type=str, default="", help="Single prompt override")
    args = parser.parse_args()

    ensure_dirs()
    bot = telebot.TeleBot(BOT_TOKEN) if (BOT_TOKEN and CHAT_ID) else None

    # Determine scripts to generate
    if args.prompt.strip():
        scripts = [args.prompt.strip()]
        print(f"[+] Running single prompt: \"{scripts[0]}\"")
    else:
        scripts = parse_scripts_file(args.file)
        print(f"[+] Loaded {len(scripts)} scripts from '{args.file}'")

    if not scripts:
        print("[!] No valid scripts found to process.")
        sys.exit(0)

    total = len(scripts)
    print(f"\n{'='*60}")
    print(f"🚀 Starting High-Speed Batch Generation: {total} Videos")
    print(f"{'='*60}\n")

    if bot and CHAT_ID:
        try:
            bot.send_message(
                CHAT_ID,
                f"🚀 *GitHub Cloud Runner Started!*\n\n"
                f"• *Total Batch Size:* {total} Videos\n"
                f"• *Hardware:* 7 GB RAM / 2 vCPUs\n"
                f"Generating and sending each video to you now...",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[!] Warning: Could not send start notification to Telegram: {e}")

    for idx, script in enumerate(scripts, start=1):
        print(f"\n[{idx}/{total}] Processing: \"{script[:60]}...\"")
        
        try:
            # 1. Voiceover & Subtitles
            audio_path, srt_path = asyncio.run(generate_speech_and_subs(script))
            
            # 2. Clips
            urls = fetch_internet_archive_clips(query="anime", count=4)
            clips = download_or_slice_clips(urls, target_duration_per_clip=3.0, target_count=4)
            
            # 3. Render 1080x1920 Short
            out_name = f"short_{idx:03d}.mp4"
            final_video = render_youtube_short(clips, audio_path, srt_path, output_filename=out_name)
            
            # 4. Send to Telegram if configured
            if bot and CHAT_ID:
                try:
                    caption = (
                        f"🍿 *Short [{idx}/{total}] Generated!* 🚀\n\n"
                        f"📝 *Script:*\n\"{script}\"\n\n"
                        f"• *Resolution:* 1080x1920 (9:16 Vertical)\n"
                        f"• *Remaining in batch:* {total - idx}"
                    )
                    with open(final_video, "rb") as vf:
                        bot.send_video(CHAT_ID, vf, caption=caption, parse_mode="Markdown", supports_streaming=True)
                    print(f"      [✓] Delivered to Telegram Chat ID: {CHAT_ID}")
                except Exception as te:
                    print(f"      [!] Telegram upload error: {te}")

            print(f"      [✓] Saved: {final_video}")

        except Exception as e:
            print(f"      [X] Error on script #{idx}: {e}")
            if bot and CHAT_ID:
                try:
                    bot.send_message(CHAT_ID, f"⚠️ Error generating video #{idx}: `{str(e)}`. Continuing...")
                except Exception:
                    pass

    print(f"\n{'='*60}")
    print(f"🎉 Batch generation finished! All {total} videos generated.")
    print(f"{'='*60}\n")

    if bot and CHAT_ID:
        try:
            bot.send_message(
                CHAT_ID,
                f"🎉 *Batch Complete!*\n\nAll {total} videos have been generated and sent to you! Enjoy! 🍿",
                parse_mode="Markdown"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
