"""
Anime YouTube Shorts Generator Agent
100% Free & Open Source - No API Keys or Subscriptions Required
"""

import os
import sys
import json
import time
import shutil
import asyncio
import argparse
import subprocess
import requests
import edge_tts

# Default Configuration
DEFAULT_VOICE = "en-US-ChristopherNeural"  # Clear, energetic narrator
DEFAULT_RESOLUTION = (1080, 1920)         # Standard 9:16 vertical Short
TEMP_DIR = "temp_workspace"
OUTPUT_DIR = "output_shorts"

# Tag synonym map for Sakugabooru tags
TAG_MAP = {
    "fight": "fighting",
    "battle": "fighting",
    "action": "fighting",
    "punch": "fighting",
    "sword": "sword_fight",
    "explosion": "explosions",
    "magic": "effects",
    "fx": "effects",
    "run": "running",
    "smoke": "smoke",
    "fire": "fire"
}


def ensure_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("clips", exist_ok=True)


def clean_temp():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    os.makedirs(TEMP_DIR, exist_ok=True)


# ==========================================
# 1. Voiceover & Subtitle Generation
# ==========================================
async def generate_speech_and_subs(text: str, voice: str = DEFAULT_VOICE) -> tuple[str, str]:
    """
    Generates natural voiceover audio and synchronized subtitle file.
    100% free via Microsoft Neural TTS.
    """
    audio_path = os.path.join(TEMP_DIR, "voiceover.mp3")
    srt_path = os.path.join(TEMP_DIR, "subtitles.srt")
    
    print(f"\n[1/4] Generating Voiceover using '{voice}'...")
    communicate = edge_tts.Communicate(text, voice, rate="+8%")
    submaker = edge_tts.SubMaker()
    
    with open(audio_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
                
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(submaker.get_srt())
        
    print(f"      Voiceover created: {audio_path}")
    print(f"      Subtitles generated: {srt_path}")
    return audio_path, srt_path


def get_audio_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(res.stdout.strip())


# ==========================================
# 2. Anime Clip Sourcing (Free Public APIs)
# ==========================================
def fetch_sakugabooru_clips(tag: str = "fighting", count: int = 4) -> list[str]:
    """
    Fetches high quality animation cuts from Sakugabooru.
    """
    mapped_tag = TAG_MAP.get(tag.lower(), tag.lower())
    print(f"\n[2/4] Sourcing anime cuts from Sakugabooru (tag: '{mapped_tag}')...")
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    urls_to_try = [
        f"https://www.sakugabooru.com/post.json?tags={mapped_tag}+order:score&limit={count * 3}",
        f"https://www.sakugabooru.com/post.json?tags=fighting+order:score&limit={count * 3}",
        f"https://www.sakugabooru.com/post.json?tags=animated+order:score&limit={count * 3}"
    ]
    
    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                posts = resp.json()
                mp4_urls = []
                for p in posts:
                    file_url = p.get("file_url")
                    if file_url and file_url.endswith((".mp4", ".webm")):
                        mp4_urls.append(file_url)
                    if len(mp4_urls) >= count * 2:
                        break
                if mp4_urls:
                    print(f"      Found {len(mp4_urls)} clip candidates.")
                    return mp4_urls
        except Exception:
            continue
            
    return []


def fetch_internet_archive_clips(query: str = "anime", count: int = 4) -> list[str]:
    """
    Searches Internet Archive (archive.org) for public video files.
    """
    print(f"\n[2/4] Sourcing archival anime from Internet Archive (query: '{query}')...")
    search_url = "https://archive.org/advancedsearch.php"
    params = {
        "q": f"mediatype:movies AND ({query} OR anime OR animation)",
        "fl[]": ["identifier", "title"],
        "rows": count * 3,
        "output": "json"
    }
    
    try:
        resp = requests.get(search_url, params=params, timeout=12).json()
        docs = resp.get("response", {}).get("docs", [])
        
        video_urls = []
        for doc in docs:
            ident = doc["identifier"]
            meta_url = f"https://archive.org/metadata/{ident}/files"
            meta_resp = requests.get(meta_url, timeout=8).json()
            for f in meta_resp.get("result", []):
                fname = f.get("name", "")
                if fname.endswith(".mp4") and not fname.endswith(("_thumb.mp4", "_ia.mp4")):
                    video_urls.append(f"https://archive.org/download/{ident}/{fname}")
                    break
            if len(video_urls) >= count * 2:
                break
                
        print(f"      Found {len(video_urls)} archival video links.")
        return video_urls
    except Exception as e:
        print(f"      Error querying Internet Archive: {e}")
        return []


def download_or_slice_clips(urls: list[str], target_duration_per_clip: float, target_count: int = 4) -> list[str]:
    """
    Slices segments from URLs using FFmpeg directly with robust reconnects and timeouts.
    """
    downloaded_files = []
    for i, url in enumerate(urls):
        if len(downloaded_files) >= target_count:
            break
            
        out_name = os.path.join(TEMP_DIR, f"source_clip_{len(downloaded_files)}.mp4")
        seek_sec = (i * 4) + 2
        print(f"      Extracting slice #{len(downloaded_files)+1} ({target_duration_per_clip:.1f}s)...")
        
        cmd = [
            "ffmpeg", "-y",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-ss", f"00:00:{seek_sec:02d}",
            "-i", url,
            "-t", str(target_duration_per_clip),
            "-an",  # Strip original clip audio
            "-c:v", "libx264", "-preset", "ultrafast",
            out_name
        ]
        
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            if res.returncode == 0 and os.path.exists(out_name) and os.path.getsize(out_name) > 1000:
                downloaded_files.append(out_name)
            else:
                print(f"      [~] Skipped unresponsive link, trying next candidate...")
        except subprocess.TimeoutExpired:
            print(f"      [~] Link timed out, trying next candidate...")
            continue
        except Exception:
            continue

    # Fallback: if we got at least 1 clip but fewer than target, duplicate to fill
    if 0 < len(downloaded_files) < target_count:
        orig = list(downloaded_files)
        while len(downloaded_files) < target_count:
            src = orig[len(downloaded_files) % len(orig)]
            copy_path = os.path.join(TEMP_DIR, f"source_clip_{len(downloaded_files)}.mp4")
            shutil.copy(src, copy_path)
            downloaded_files.append(copy_path)

    return downloaded_files


# ==========================================
# 3. Video Editing & 9:16 Shorts Rendering
# ==========================================
def render_youtube_short(
    clip_files: list[str],
    audio_path: str,
    srt_path: str,
    output_filename: str = "anime_short.mp4"
) -> str:
    """
    Takes clips, formats them into standard 9:16 YouTube Shorts:
    - Background: Blurred, scaled to 1080x1920
    - Foreground: Sharp centered anime footage
    - Subtitles: Clean modern captions burned onto the screen
    """
    print("\n[3/4] Composing 9:16 vertical video layout...")
    total_audio_duration = get_audio_duration(audio_path)
    print(f"      Total audio duration: {total_audio_duration:.2f} seconds")
    
    if not clip_files:
        raise RuntimeError("No valid anime clips available to assemble video.")

    clip_duration = total_audio_duration / len(clip_files)
    processed_clips = []
    
    # 1. Process each clip to exact 1080x1920 with background blur
    for idx, c in enumerate(clip_files):
        out_seg = os.path.join(TEMP_DIR, f"seg_{idx}.mp4")
        filter_complex = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
            "[0:v]scale=1080:-1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", c,
            "-t", str(clip_duration),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "veryfast", "-r", "30",
            out_seg
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        processed_clips.append(out_seg)

    # 2. Concat all processed segments
    concat_list = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in processed_clips:
            normalized = os.path.abspath(seg).replace("\\", "/")
            f.write(f"file '{normalized}'\n")

    concatenated_video = os.path.join(TEMP_DIR, "combined_visuals.mp4")
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        concatenated_video
    ]
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Final burn-in: Combine visuals, voiceover, and subtitles
    print("\n[4/4] Burning in subtitles & mixing final master...")
    final_output = os.path.join(OUTPUT_DIR, output_filename)
    
    # Subtitle styling: bold yellow font, black border, centered
    clean_srt_path = os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
    subtitle_style = (
        "Fontname=Arial,FontSize=18,Bold=1,"
        "PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=140"
    )
    sub_filter = f"subtitles='{clean_srt_path}':force_style='{subtitle_style}'"

    master_cmd = [
        "ffmpeg", "-y",
        "-i", concatenated_video,
        "-i", audio_path,
        "-vf", sub_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        final_output
    ]
    
    subprocess.run(master_cmd, check=True)
    print(f"\n=======================================================")
    print(f" [SUCCESS] Your YouTube Short is ready!")
    print(f" File: {os.path.abspath(final_output)}")
    print(f"=======================================================")
    return final_output


# ==========================================
# Main CLI Runner
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Create Anime YouTube Shorts from a Script (100% Free)")
    parser.add_argument("--script", type=str, help="The script text for the Short")
    parser.add_argument("--query", type=str, default="fight", help="Clip search keyword (e.g., fight, explosion, running, retro)")
    parser.add_argument("--source", type=str, choices=["sakuga", "archive", "local"], default="archive",
                        help="Clip source: 'archive' (Internet Archive), 'sakuga' (Sakugabooru cuts), or 'local' (clips/ folder)")
    parser.add_argument("--output", type=str, default="anime_short.mp4", help="Output file name")
    
    args = parser.parse_args()
    ensure_dirs()

    # If no script provided via flag, ask interactively
    script = args.script
    if not script:
        print("="*60)
        print("          ANIME SHORTS GENERATOR AGENT (FREE)         ")
        print("="*60)
        script = input("\nEnter your script for the Short (30-60 words works best):\n> ").strip()
        if not script:
            script = (
                "Did you know why Gojo Satoru never closes his eyes in battle? "
                "The Six Eyes grant him atomic-level perception of cursed energy, "
                "meaning he sees the universe in 4K high definition at all times!"
            )
            print(f"\nNo script entered. Using default sample:\n\"{script}\"")

    clean_temp()

    # Step 1: TTS & Subtitles
    audio_path, srt_path = asyncio.run(generate_speech_and_subs(script))
    total_duration = get_audio_duration(audio_path)
    target_clip_time = max(2.0, total_duration / 4)

    # Step 2: Source Clips
    clip_files = []
    
    # Check local clips folder first if chosen
    if args.source == "local":
        local_clips = [os.path.join("clips", f) for f in os.listdir("clips") if f.endswith((".mp4", ".mkv", ".mov"))]
        if local_clips:
            print(f"\nFound {len(local_clips)} local clips in 'clips/' folder.")
            clip_files = local_clips[:4]
        else:
            print("\nNo local clips found in 'clips/' folder. Sourcing from Internet Archive...")
            args.source = "archive"

    if not clip_files:
        if args.source == "sakuga":
            urls = fetch_sakugabooru_clips(args.query, count=4)
        else:
            urls = fetch_internet_archive_clips(args.query, count=4)
            
        if urls:
            clip_files = download_or_slice_clips(urls, target_clip_time, target_count=4)

    # Step 3: Render
    if clip_files:
        render_youtube_short(clip_files, audio_path, srt_path, output_filename=args.output)
    else:
        print("[!] Could not retrieve clips automatically. Please place .mp4 clips in the 'clips/' folder and run with --source local.")


if __name__ == "__main__":
    main()
