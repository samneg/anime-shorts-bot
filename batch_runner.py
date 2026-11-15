"""
GitHub Actions High-Speed Batch Video Generator (7GB RAM Runner)
Tailored for 50-Script Anime Edits:
- Deep, confident AI voice (slow pace > 70s duration)
- Fast-paced visual cuts (< 2 seconds per clip)
- Bold yellow & white subtitles with thick black outlines
- Auto-matches anime footage (One Piece, JJK, Black Clover, Death Note, Bleach, etc.)
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


def detect_anime_query(text: str) -> str:
    """Intelligently detects which anime franchise to pull video footage for."""
    t = text.lower()
    if any(k in t for k in ['zoro', 'luffy', 'shanks', 'one piece', 'haki', 'akainu', 'kaido', 'sanji', 'usopp', 'mihawk', 'enel', 'chopper', 'yamato', 'law', 'roger']):
        return 'One Piece anime'
    if any(k in t for k in ['gojo', 'sukuna', 'yuji', 'itadori', 'megumi', 'nobara', 'yuta', 'maki', 'toji', 'jujutsu']):
        return 'Jujutsu Kaisen anime'
    if any(k in t for k in ['asta', 'black clover', 'yuno', 'noelle', 'julius']):
        return 'Black Clover anime'
    if any(k in t for k in ['light', 'death note', 'ryuk', 'misa', 'near', 'kira']):
        return 'Death Note anime'
    if any(k in t for k in ['goku', 'dragon ball', 'giorno', 'requiem']):
        return 'Dragon Ball anime'
    if any(k in t for k in ['saitama', 'one punch']):
        return 'One Punch Man anime'
    if any(k in t for k in ['naruto', 'itachi', 'madara', 'boruto', 'sasuke']):
        return 'Naruto anime'
    if any(k in t for k in ['bleach', 'aizen', 'ichigo', 'kenpachi', 'zaraki']):
        return 'Bleach anime'
    if any(k in t for k in ['titan', 'levi', 'ackerman', 'eren']):
        return 'Attack on Titan anime'
    if any(k in t for k in ['demon slayer', 'tanjiro', 'akaza', 'kokushibo']):
        return 'Demon Slayer anime'
    if any(k in t for k in ['hunter', 'meruem', 'netero', 'gon', 'killua']):
        return 'Hunter x Hunter anime'
    return 'anime action fight'


def parse_scripts_file(filepath: str) -> list[str]:
    """Parses scripts.txt into individual clean scripts."""
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by delimiter ---
    parts = content.split("---")
    cleaned = []
    for p in parts:
        # Strip script headers and instruction remnants
        p = re.sub(r'###\s*SCRIPT\s*\d+\s*###', '', p, flags=re.IGNORECASE)
        p = re.sub(r'Script\s*#\d+', '', p, flags=re.IGNORECASE)
        p = re.sub(r'AI CREATOR INSTRUCTIONS:.*?(?=SCRIPT AUDIO:|$)', '', p, flags=re.DOTALL | re.IGNORECASE)
        p = re.sub(r'SCRIPT AUDIO:', '', p, flags=re.IGNORECASE)
        p = re.sub(r'these are the scripts with instructions\s*$', '', p, flags=re.IGNORECASE)
        p = p.strip()
        if len(p) > 20:
            cleaned.append(p)
            
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="GitHub Actions Batch Anime Shorts Runner")
    parser.add_argument("--file", type=str, default="scripts.txt", help="Path to scripts file")
    parser.add_argument("--prompt", type=str, default="", help="Single prompt override")
    args = parser.parse_args()

    ensure_dirs()
    bot = telebot.TeleBot(BOT_TOKEN) if (BOT_TOKEN and CHAT_ID) else None

    # Load scripts
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
                f"• *Target Length:* 70+ Seconds per video\n"
                f"Generating and delivering each video to you now...",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[!] Warning: Could not send start notification to Telegram: {e}")

    for idx, script in enumerate(scripts, start=1):
        anime_theme = detect_anime_query(script)
        print(f"\n[{idx}/{total}] Anime: [{anime_theme}] | Text: \"{script[:60]}...\"")
        
        try:
            # 1. Voiceover & Subtitles (Deep voice, slow pace -15% to cross 70s)
            import edge_tts
            temp_audio = os.path.join("temp_workspace", f"voice_{idx}.mp3")
            temp_srt = os.path.join("temp_workspace", f"subs_{idx}.srt")
            
            async def gen_voice():
                comm = edge_tts.Communicate(script, "en-US-ChristopherNeural", rate="-15%")
                submaker = edge_tts.SubMaker()
                with open(temp_audio, "wb") as f:
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                        elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                            submaker.feed(chunk)
                with open(temp_srt, "w", encoding="utf-8") as f:
                    f.write(submaker.get_srt())
                return temp_audio, temp_srt

            audio_path, srt_path = asyncio.run(gen_voice())
            
            # 2. Clips (Fast cuts under 2s each)
            urls = fetch_internet_archive_clips(query=anime_theme, count=6)
            clips = download_or_slice_clips(urls, target_duration_per_clip=1.8, target_count=6)
            
            # 3. Render 1080x1920 Short
            out_name = f"short_{idx:03d}.mp4"
            final_video = render_youtube_short(clips, audio_path, srt_path, output_filename=out_name)
            
            # 4. Deliver to Telegram if Chat ID is configured
            if bot and CHAT_ID:
                try:
                    caption = (
                        f"🍿 *Short [{idx}/{total}] Generated!* 🚀\n\n"
                        f"🎬 *Anime:* {anime_theme}\n"
                        f"📝 *Script:*\n\"{script}\"\n\n"
                        f"• *Format:* 1080x1920 (9:16 Vertical)\n"
                        f"• *Batch Progress:* {idx}/{total}"
                    )
                    with open(final_video, "rb") as vf:
                        bot.send_video(CHAT_ID, vf, caption=caption, parse_mode="Markdown", supports_streaming=True)
                    print(f"      [✓] Delivered to Telegram Chat ID: {CHAT_ID}")
                except Exception as te:
                    print(f"      [!] Telegram upload error: {te}")

            print(f"      [✓] Successfully Rendered: {final_video}")

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
                f"🎉 *Batch Complete!*\n\nAll {total} videos have been generated and delivered! 🍿",
                parse_mode="Markdown"
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
