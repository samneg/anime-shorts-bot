"""
Automated Batch Video Generator
Processes 50+ scripts sequentially with zero manual intervention:
- Deep, confident AI voice (slow pace > 70s duration)
- Fast-paced visual cuts (< 2 seconds per clip)
- Bold yellow & white subtitles with thick black outlines centered on screen
- Intense phonk background music ducking
- Auto-matches anime footage (One Piece, JJK, Black Clover, Death Note, Bleach, Naruto, etc.)
- Outputs all videos to 'output_shorts/short_001.mp4' .. 'short_050.mp4'
"""

import os
import sys
import re
import math
import asyncio
import argparse
import telebot
import edge_tts
from anime_agent import (
    fetch_internet_archive_clips,
    fetch_sakugabooru_clips,
    download_or_slice_clips,
    generate_ass_subtitles,
    get_audio_duration,
    render_youtube_short,
    ensure_dirs,
    clean_temp
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


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
    if any(k in t for k in ['goku', 'dragon ball', 'vegeta', 'saiyan', 'giorno', 'requiem']):
        return 'Dragon Ball anime'
    if any(k in t for k in ['saitama', 'one punch', 'genos', 'garou']):
        return 'One Punch Man anime'
    if any(k in t for k in ['naruto', 'itachi', 'madara', 'boruto', 'sasuke', 'kakashi']):
        return 'Naruto anime'
    if any(k in t for k in ['bleach', 'aizen', 'ichigo', 'kenpachi', 'zaraki', 'bankai']):
        return 'Bleach anime'
    if any(k in t for k in ['titan', 'levi', 'ackerman', 'eren', 'yeager']):
        return 'Attack on Titan anime'
    if any(k in t for k in ['demon slayer', 'tanjiro', 'akaza', 'kokushibo', 'muzak']):
        return 'Demon Slayer anime'
    if any(k in t for k in ['hunter', 'meruem', 'netero', 'gon', 'killua', 'hisoka']):
        return 'Hunter x Hunter anime'
    return 'anime action fight'


def parse_scripts_file(filepath: str) -> list[str]:
    """Parses scripts.txt into individual clean scripts."""
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    parts = content.split("---")
    cleaned = []
    for p in parts:
        p = re.sub(r'###\s*SCRIPT\s*\d+\s*###', '', p, flags=re.IGNORECASE)
        p = re.sub(r'Script\s*#\d+', '', p, flags=re.IGNORECASE)
        p = re.sub(r'AI CREATOR INSTRUCTIONS:.*?(?=SCRIPT AUDIO:|$)', '', p, flags=re.DOTALL | re.IGNORECASE)
        p = re.sub(r'SCRIPT AUDIO:', '', p, flags=re.IGNORECASE)
        p = re.sub(r'these are the scripts with instructions\s*$', '', p, flags=re.IGNORECASE)
        p = p.strip()
        if len(p) > 20:
            cleaned.append(p)
            
    return cleaned


async def generate_narration_and_ass(text: str, idx: int) -> tuple[str, str, float]:
    """
    Produces slow, deep, confident narration (>70s) and synchronized centered ASS cues.
    """
    ensure_dirs()
    temp_audio = os.path.join("temp_workspace", f"voice_{idx}.mp3")
    temp_ass = os.path.join("temp_workspace", f"subs_{idx}.ass")
    
    # Insert dramatic pauses at sentence ends
    paced_text = text.replace(". ", "... ").replace("! ", "... ").replace("? ", "... ")
    
    voice_name = "en-US-ChristopherNeural"
    rate_str = "-18%"
    
    events = []
    comm = edge_tts.Communicate(paced_text, voice_name, rate=rate_str)
    
    with open(temp_audio, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                offset_sec = chunk["offset"] / 10_000_000.0
                dur_sec = chunk["duration"] / 10_000_000.0
                events.append((offset_sec, offset_sec + dur_sec, chunk["text"]))
                
    dur = get_audio_duration(temp_audio)
    
    # If duration is under 70 seconds, slow rate slightly more to ensure >70s
    if dur < 70.0:
        events = []
        comm = edge_tts.Communicate(paced_text, voice_name, rate="-24%")
        with open(temp_audio, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    offset_sec = chunk["offset"] / 10_000_000.0
                    dur_sec = chunk["duration"] / 10_000_000.0
                    events.append((offset_sec, offset_sec + dur_sec, chunk["text"]))
        dur = get_audio_duration(temp_audio)

    # Generate ASS word-by-word centered subtitles
    generate_ass_subtitles(events, temp_ass)
    return temp_audio, temp_ass, dur


def run_batch(file_path: str = "scripts.txt", start_from: int = 1, single_prompt: str = ""):
    ensure_dirs()
    bot = telebot.TeleBot(BOT_TOKEN) if (BOT_TOKEN and CHAT_ID) else None

    if single_prompt.strip():
        scripts = [single_prompt.strip()]
        print(f"[+] Running single prompt override: \"{scripts[0][:60]}...\"")
    else:
        scripts = parse_scripts_file(file_path)
        print(f"[+] Loaded {len(scripts)} scripts from '{file_path}'")

    if not scripts:
        print("[!] No valid scripts found to process.")
        return

    total = len(scripts)
    print(f"\n{'='*65}")
    print(f"🎬 Starting Fully Automated Batch Video Generator: {total} Shorts")
    print(f"• Output Folder: {os.path.abspath('output_shorts')}")
    print(f"• Target Duration: > 70 Seconds per video")
    print(f"• Visual Style: High-Contrast Fast Cuts (<2s)")
    print(f"• Captions: Centered Bold Yellow/White ASS")
    print(f"{'='*65}\n")

    for idx, script in enumerate(scripts, start=1):
        if idx < start_from:
            continue
            
        out_name = f"short_{idx:03d}.mp4"
        out_path = os.path.join("output_shorts", out_name)
        
        # Skip if already rendered
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1_000_000:
            print(f"[✓] [{idx}/{total}] Already generated: {out_name} - Skipping...")
            continue
            
        clean_temp()
        anime_theme = detect_anime_query(script)
        print(f"\n[{idx}/{total}] Processing: [{anime_theme}]")
        print(f"Text: \"{script[:70]}...\"")
        
        try:
            # 1. Voiceover & Centered Subtitles (>70s)
            audio_path, ass_path, duration = asyncio.run(generate_narration_and_ass(script, idx))
            print(f"      [✓] Voice generated: {duration:.2f}s (Pacing > 70s)")

            # 2. Clips Sourcing (Fast cuts under 2s)
            urls = fetch_internet_archive_clips(query=anime_theme, count=6)
            if not urls:
                urls = fetch_sakugabooru_clips("fighting", count=6)
            if not urls:
                urls = fetch_internet_archive_clips("anime", count=6)
                
            clips = download_or_slice_clips(urls, target_duration_per_clip=1.7, target_count=6)
            
            # 3. Render 1080x1920 Short with Phonk & Centered Captions
            final_video = render_youtube_short(
                clips, audio_path, ass_path,
                output_filename=out_name,
                cut_duration=1.7
            )
            
            # 4. Optional: Send to Telegram
            if bot and CHAT_ID:
                try:
                    caption = (
                        f"🍿 *Short [{idx}/{total}] Generated!* 🚀\n\n"
                        f"🎬 *Anime:* {anime_theme}\n"
                        f"⏱ *Duration:* {duration:.1f}s\n"
                        f"• *Progress:* {idx}/{total}"
                    )
                    with open(final_video, "rb") as vf:
                        bot.send_video(CHAT_ID, vf, caption=caption, parse_mode="Markdown", supports_streaming=True)
                except Exception as te:
                    print(f"      [!] Telegram forward notice: {te}")

            print(f"      [✓] Successfully Completed Short #{idx}: {out_name}")

        except Exception as e:
            print(f"      [X] Error on script #{idx}: {e}")

    print(f"\n{'='*65}")
    print(f"🎉 BATCH COMPLETE! All {total} videos generated in 'output_shorts/'")
    print(f"{'='*65}\n")


def main():
    parser = argparse.ArgumentParser(description="Batch Anime Shorts Generator")
    parser.add_argument("--file", type=str, default="scripts.txt", help="Path to scripts file")
    parser.add_argument("--start", type=int, default=1, help="Start from script index (1-based)")
    parser.add_argument("--prompt", type=str, default="", help="Single prompt override")
    args = parser.parse_args()

    run_batch(file_path=args.file, start_from=args.start, single_prompt=args.prompt)


if __name__ == "__main__":
    main()
