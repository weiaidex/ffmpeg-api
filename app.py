from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
import os
import uuid
import subprocess
import shutil
import re
import requests

app = FastAPI()

TMP_DIR = "/tmp/videos"
SNAPSHOT_DIR = "/tmp/snapshots"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# --- Utilities ---
def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def run_ffmpeg_command(command):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")

def download_with_ytdlp(url, output_path):
    command = [
        'yt-dlp', '-f', 'best', '-o', output_path, url
    ]
    subprocess.run(command, check=True)

def download_with_browserless(video_url, slug):
    # Browserless Screenshot capture logic
    payload = {
        "url": video_url,
        "options": {
            "fullPage": True
        }
    }
    snapshot_path = os.path.join(SNAPSHOT_DIR, slug)
    os.makedirs(snapshot_path, exist_ok=True)

    for i in range(0, 900, 15):  # Assume max 15min videos
        ss_url = f"https://chrome.browserless.io/screenshot?token=YOUR_BROWSERLESS_TOKEN"
        payload["options"]["clip"] = {
            "x": 0, "y": 0, "width": 720, "height": 1280
        }
        payload["gotoOptions"] = {"waitUntil": "networkidle0", "timeout": 10000}
        payload["wait"] = 15000 * (i // 15)  # delay in ms

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

def trim_and_stitch(slug, second):
    input_path = os.path.join(TMP_DIR, f"{slug}.mp4")
    output_path = os.path.join(TMP_DIR, f"Video Theme - {slug}.mp4")
    start = max(0, second - 7)
    run_ffmpeg_command([
        "ffmpeg", "-ss", str(start), "-i", input_path,
        "-t", "15", "-an", output_path
    ])
    return FileResponse(output_path, media_type="video/mp4")

# --- Routes ---
@app.get("/")
def root():
    return {"message": "FFmpeg API is running"}

@app.post("/snapshots-phase1")
async def phase1_snapshots(video_url: str = Form(...), slug: str = Form(...), interval: int = Form(...)):
    slug = slugify(slug)
    temp_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")

    try:
        if video_url.endswith(".mp4") or "youtube.com" in video_url:
            download_with_ytdlp(video_url, temp_path)
            return take_snapshots_with_ffmpeg(temp_path, slug, interval)
        else:
            return download_with_browserless(video_url, slug)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/clip-phase2")
async def phase2_clip(slug: str = Form(...), moment_index: int = Form(...), interval: int = Form(...)):
    slug = slugify(slug)
    second = moment_index * interval
    try:
        return trim_and_stitch(slug, second)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
