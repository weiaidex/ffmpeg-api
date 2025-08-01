# Version 1.0.4
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, JSONResponse
import os
import uuid
import subprocess
import re

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
    if not os.path.exists("cookies.txt"):
        raise RuntimeError("cookies.txt not found!")
    command = [
        'yt-dlp',
        '--cookies', 'cookies.txt',
        '-o', output_path,
        url
    ]
    subprocess.run(command, check=True)

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
    return {"message": "FFmpeg API (yt-dlp only) is running"}

@app.post("/snapshots")
async def generate_snapshots(video_url: str = Form(...), slug: str = Form(...), interval: int = Form(...)):
    slug = slugify(slug)
    temp_path = os.path.join(TMP_DIR, f"{uuid.uuid4()}.mp4")

    try:
        download_with_ytdlp(video_url, temp_path)
        return take_snapshots_with_ffmpeg(temp_path, slug, interval)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
