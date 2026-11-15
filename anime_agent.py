"""
Anime YouTube Shorts Generator Agent
100% Free, Automated Architecture:
- Voiceover & Synced Subtitles: Microsoft Neural TTS (Edge-TTS)
- Subtitle Styler: High-impact Centered ASS word-by-word with Yellow/White & Black Outlines
- Anime Clip Sourcing: Internet Archive & Sakugabooru Public Booru API
- Video Editing: FFmpeg 1080x1920 (9:16 Vertical) with Blurred Background & Phonk Ducking
"""

import os
import sys
import math
import shutil
import asyncio
import requests
import subprocess
from urllib.parse import quote_plus

TEMP_DIR = "temp_workspace"
OUTPUT_DIR = "output_shorts"
ASSETS_DIR = "assets"
PHONK_TRACK = os.path.join(ASSETS_DIR, "bg_phonk.mp3")

TAG_MAP = {
    "fight": "fighting",
    "battle": "fighting",
    "action": "fighting",
    "punch": "fighting",
    "sword": "sword",
    "jujutsu kaisen": "jujutsu_kaisen",
    "jjk": "jujutsu_kaisen",
    "naruto": "naruto_shippuuden",
    "bleach": "bleach",
    "one piece": "one_piece",
    "dragon ball": "dragon_ball",
    "demon slayer": "kimetsu_no_yaiba",
    "hunter": "hunter_x_hunter",
    "black clover": "black_clover"
}


def ensure_dirs():
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs("clips", exist_ok=True)


def clean_temp():
    ensure_dirs()
    if os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            fp = os.path.join(TEMP_DIR, f)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                elif os.path.isdir(fp):
                    shutil.rmtree(fp, ignore_errors=True)
            except Exception:
                pass


def format_ass_time(sec: float) -> str:
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        secs += 1
        cs -= 100
    return f"{hrs:d}:{mins:02d}:{secs:02d}.{cs:02d}"


def generate_ass_subtitles(events: list[tuple[float, float, str]], output_ass_path: str):
    """
    Creates dynamic, word-by-word / 2-word centered subtitles:
    - Center of screen (Alignment 5)
    - Bold Arial, high visibility
    - Yellow (&H0000FFFF&) and White (&H00FFFFFF&) colors with thick black outline
    """
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,0,5,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogues = []
    for s_start, s_end, text in events:
        words = text.strip().split()
        if not words:
            continue
        dur = max(0.2, s_end - s_start)
        chunks = [words[i:i+2] for i in range(0, len(words), 2)]
        chunk_dur = dur / len(chunks)
        for idx, chk in enumerate(chunks):
            c_start = s_start + (idx * chunk_dur)
            c_end = c_start + chunk_dur
            if len(chk) == 1:
                styled_text = f"{{\\c&H0000FFFF&}}{chk[0].upper()}"
            else:
                styled_text = f"{{\\c&H0000FFFF&}}{chk[0].upper()} {{\\c&H00FFFFFF&}}{chk[1].upper()}"
            dialogues.append(
                f"Dialogue: 0,{format_ass_time(c_start)},{format_ass_time(c_end)},Default,,0,0,0,,{styled_text}"
            )
            
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(dialogues) + "\n")


def get_audio_duration(file_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 60.0


def fetch_internet_archive_clips(query: str = "One Piece anime", count: int = 6) -> list[str]:
    """Queries archive.org for anime episodes."""
    print(f"\n[Sourcing] Internet Archive search: '{query}'...")
    try:
        clean_q = quote_plus(f"{query} mediatype:movies")
        search_url = f"https://archive.org/advancedsearch.php?q={clean_q}&fl[]=identifier,title&sort[]=downloads+desc&rows=15&page=1&output=json"
        resp = requests.get(search_url, timeout=10).json()
        docs = resp.get("response", {}).get("docs", [])
        
        video_urls = []
        for doc in docs:
            ident = doc.get("identifier")
            if not ident:
                continue
            meta_url = f"https://archive.org/metadata/{ident}/files"
            meta_resp = requests.get(meta_url, timeout=10).json()
            for f in meta_resp.get("result", []):
                fname = f.get("name", "")
                if fname.endswith(".mp4") and not fname.endswith(("_thumb.mp4", "_ia.mp4")):
                    video_urls.append(f"https://archive.org/download/{ident}/{fname}")
                    break
            if len(video_urls) >= count:
                break
                
        print(f"      Found {len(video_urls)} archival video links.")
        return video_urls
    except Exception as e:
        print(f"      [!] Archive query error: {e}")
        return []


def fetch_sakugabooru_clips(tag: str = "fighting", count: int = 6) -> list[str]:
    """Queries Sakugabooru for animation cuts."""
    mapped_tag = TAG_MAP.get(tag.lower(), tag.lower())
    print(f"\n[Sourcing] Sakugabooru cuts: '{mapped_tag}'...")
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
                mp4_urls = [p["file_url"] for p in posts if p.get("file_url", "").endswith((".mp4", ".webm"))]
                if mp4_urls:
                    print(f"      Found {len(mp4_urls)} sakuga clips.")
                    return mp4_urls[:count]
        except Exception:
            continue
    return []


def download_or_slice_clips(urls: list[str], target_duration_per_clip: float = 1.7, target_count: int = 6) -> list[str]:
    """
    Slices segments from action timestamps (2m, 4m, 6m, 8m, 10m, 12m, 15m)
    using FFmpeg streaming directly.
    """
    downloaded_files = []
    action_timestamps = [120, 240, 360, 480, 600, 750, 900]
    
    for i, url in enumerate(urls):
        if len(downloaded_files) >= target_count:
            break
            
        out_name = os.path.join(TEMP_DIR, f"source_clip_{len(downloaded_files)}.mp4")
        seek_sec = action_timestamps[i % len(action_timestamps)]
        print(f"      Extracting slice #{len(downloaded_files)+1} ({target_duration_per_clip:.1f}s at {seek_sec}s)...")
        
        cmd = [
            "ffmpeg", "-y",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-ss", str(seek_sec),
            "-i", url,
            "-t", str(target_duration_per_clip),
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast",
            out_name
        ]
        
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
            if res.returncode == 0 and os.path.exists(out_name) and os.path.getsize(out_name) > 1000:
                downloaded_files.append(out_name)
            else:
                cmd[6] = str((i * 5) + 3)
                res2 = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                if res2.returncode == 0 and os.path.exists(out_name) and os.path.getsize(out_name) > 1000:
                    downloaded_files.append(out_name)
        except Exception:
            continue

    if 0 < len(downloaded_files) < target_count:
        orig = list(downloaded_files)
        while len(downloaded_files) < target_count:
            src = orig[len(downloaded_files) % len(orig)]
            copy_path = os.path.join(TEMP_DIR, f"source_clip_{len(downloaded_files)}.mp4")
            shutil.copy(src, copy_path)
            downloaded_files.append(copy_path)

    return downloaded_files


def render_youtube_short(
    clip_files: list[str],
    audio_path: str,
    ass_path: str,
    output_filename: str = "anime_short.mp4",
    cut_duration: float = 1.7
) -> str:
    """
    Renders high-contrast, edgy vertical 9:16 anime short:
    - Motion-blurred vertical background (270x480 -> boxblur -> 1080x1920)
    - High-contrast centered foreground (eq=contrast=1.18:saturation=1.25)
    - Fast cuts under 2 seconds (1.7s) cycled to cover full 70+s duration
    - Intense phonk background ducking
    - Centered bold yellow/white ASS captions
    """
    ensure_dirs()
    print("\n[Composing] 9:16 vertical layout with fast cuts (<2s)...")
    total_audio_duration = get_audio_duration(audio_path)
    print(f"      Total audio duration: {total_audio_duration:.2f} seconds")
    
    if not clip_files:
        raise RuntimeError("No valid anime clips available to assemble video.")

    # 1. Format each unique source clip into 9:16 vertical 1080x1920
    processed_clips = []
    for idx, c in enumerate(clip_files):
        out_seg = os.path.join(TEMP_DIR, f"seg_{idx}.mp4")
        filter_complex = (
            "[0:v]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920[bg];"
            "[0:v]scale=1080:-1,eq=contrast=1.18:saturation=1.25[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", c,
            "-threads", "2",
            "-t", str(cut_duration),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-r", "30",
            out_seg
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        processed_clips.append(out_seg)

    # 2. Build concat list cycling through segments to cover entire audio duration
    cuts_needed = int(math.ceil(total_audio_duration / cut_duration)) + 1
    concat_list = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for i in range(cuts_needed):
            seg = processed_clips[i % len(processed_clips)]
            f.write(f"file '{os.path.basename(seg)}'\n")

    concatenated_video = os.path.join(TEMP_DIR, "combined_visuals.mp4")
    concat_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-threads", "2",
        "-i", concat_list,
        "-c", "copy",
        concatenated_video
    ]
    subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # 3. Final Master Render: Video + Audio (Voice + Phonk) + ASS Subtitles
    print("\n[Mastering] Burning centered ASS captions & phonk ducking...")
    ensure_dirs()
    final_output = os.path.join(OUTPUT_DIR, output_filename)
    
    # Use relative path so colons never break FFmpeg on Windows
    rel_ass = os.path.relpath(ass_path).replace("\\", "/")
    has_phonk = os.path.exists(PHONK_TRACK) and os.path.getsize(PHONK_TRACK) > 10000
    
    if has_phonk:
        rel_phonk = os.path.relpath(PHONK_TRACK).replace("\\", "/")
        filter_complex = (
            f"[2:a]volume=0.20[bg];[1:a]volume=1.4[voice];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[aout];"
            f"[0:v]ass='{rel_ass}'[vout]"
        )
        master_cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", concatenated_video,
            "-i", audio_path,
            "-stream_loop", "-1", "-i", rel_phonk,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            final_output
        ]
    else:
        filter_complex = f"[0:v]ass='{rel_ass}'[vout]"
        master_cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", concatenated_video,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
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
