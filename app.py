# Version 1.0.4
from fastapi import FastAPI, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import os
import uuid
import subprocess
import shutil
import re
import requests
from slugify import slugify

app = FastAPI()

TMP_DIR = "/tmp/videos"
SNAPSHOT_DIR = "/tmp/snapshots"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# --- Utilities ---
def run_ffmpeg_command(command):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")

def rewrite_to_piped_url(original_url):
    match = re.search(r"v=([^&]+)", original_url)
    if match:
        video_id = match.group(1)
        return f"https://piped.video/watch?v={video_id}"
    return original_url

def download_with_ytdlp(url, output_path):
    try:
        subprocess.run([
            'yt-dlp',
            '--cookies', 'cookies.txt',
            '-f', 'best',
            '-o', output_path,
            url
        ], check=True)
    except subprocess.CalledProcessError:
        fallback_url = rewrite_to_piped_url(url)
        subprocess.run([
            'yt-dlp',
            '--cookies', 'cookies.txt',
            '-f', 'best',
            '-o', output_path,
            fallback_url
        ], check=True)

def download_with_browserless(video_url, slug, interval, max_duration):
    payload = {
        "url": video_url,
        "options": {
            "fullPage": True,
            "clip": {
                "x": 0, "y": 0, "width": 720, "height": 1280
            }
        },
        "gotoOptions": {"waitUntil": "networkidle0", "timeout": 10000}
    }

    snapshot_path = os.path.join(SNAPSHOT_DIR, slug)
    os.makedirs(snapshot_path, exist_ok=True)

    for i in range(0, max_duration, interval):
        payload["wait"] = i * 1000
        ss_url = "https://chrome.browserless.io/screenshot?token=YOUR_BROWSERLESS_TOKEN"
        response = requests.post(ss_url, json=payload)
        if response.status_code == 200:
            with open(f"{snapshot_path}/frame_{i}.jpg", "wb") as f:
                f.write(response.content)
        else:
            break

    return JSONResponse({"message": "Browserless snapshots complete", "slug": slug})

def take_snapshots_with_ffmpeg(video_path, slug, interval):
    output_dir = os.path.join(SNAPSHOT_DIR, slug)
    os.makedirs(output_dir, exist_ok=True)
    snapshot_pattern = os.path.join(output_dir, "frame_%04d.jpg")
    run_ffmpeg_command([
        "ffmpeg", "-i", video_path,
        "-vf", f"fps=1/{interval}",
        snapshot_pattern
    ])
    return JSONResponse({"message": "Snapshots complete", "slug": slug})

# --- Routes ---
@app.get("/")
def root():
    return {"message": "FFmpeg API is running"}

@app.post("/snapshots")
async def take_snapshots(
    video_url: str = Form(...),
    slug: str = Form(...),
    interval: int = Form(...),
    max_duration: int = Form(...)
):
    slug = slugify(slug)
    temp_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")

    try:
        if video_url.endswith(".mp4") or "youtube.com" in video_url:
            download_with_ytdlp(video_url, temp_path)
            return take_snapshots_with_ffmpeg(temp_path, slug, interval)
        else:
            return download_with_browserless(video_url, slug, interval, max_duration)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/clip")
async def generate_clip(
    background_tasks: BackgroundTasks,
    slug: str = Form(...),
    moment_index: int = Form(...),
    interval: int = Form(...),
    clip_duration: int = Form(15)
):
    slug = slugify(slug)
    second = moment_index * interval
    clip_duration = max(15, min(clip_duration, 60))
    start = max(0, second - (clip_duration // 2))

    input_path = os.path.join(TMP_DIR, f"{slug}.mp4")
    output_path = os.path.join(TMP_DIR, f"Video Theme - {slug}.mp4")

    try:
        run_ffmpeg_command([
            "ffmpeg", "-ss", str(start), "-i", input_path,
            "-t", str(clip_duration), "-an", output_path
        ])
        background_tasks.add_task(os.remove, input_path)
        background_tasks.add_task(os.remove, output_path)
        return FileResponse(output_path, media_type="video/mp4")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/duration")
async def get_video_duration(video_url: str = Form(...)):
    temp_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")
    try:
        download_with_ytdlp(video_url, temp_path)
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", temp_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        duration = float(result.stdout.decode().strip())
        os.remove(temp_path)
        return JSONResponse({"duration": duration})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
