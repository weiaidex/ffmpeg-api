from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import uuid
import subprocess
import shutil

app = FastAPI()

TMP_DIR = "/tmp/videos"
os.makedirs(TMP_DIR, exist_ok=True)

COOKIES_PATH = "/app/cookies.txt"  # Optional: provide a cookies.txt file via volume or deployment

# Serve the directory at /output publicly
app.mount("/output", StaticFiles(directory=TMP_DIR), name="output")

def run_ffmpeg_command(command: list):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")

def cleanup_files(*paths):
    for path in paths:
        try:
            os.remove(path)
        except Exception:
            pass

def download_video(video_url: str, output_path: str):
    yt_dlp_cmd = ["yt-dlp"]
    if os.path.exists(COOKIES_PATH):
        yt_dlp_cmd += ["--cookies", COOKIES_PATH]
    yt_dlp_cmd += ["-f", "best", "-o", output_path, video_url]

    try:
        subprocess.run(yt_dlp_cmd, check=True)
    except subprocess.CalledProcessError:
        # Try fallback: piped.video/watch?v=<id>
        video_id = video_url.split("v=")[-1].split("&")[0]
        fallback_url = f"https://piped.video/watch?v={video_id}"
        yt_dlp_cmd[-1] = fallback_url
        subprocess.run(yt_dlp_cmd, check=True)  # Let this raise if it fails again

@app.get("/")
def root():
    return {"message": "FFmpeg API is live"}

@app.post("/trim-video")
async def trim_video_from_youtube(
    video_url: str = Form(...),
    start: str = Form(...),
    duration: str = Form(...),
):
    video_id = str(uuid.uuid4())
    input_path = os.path.join(TMP_DIR, f"{video_id}_input.mp4")
    output_path = os.path.join(TMP_DIR, f"{video_id}_output.mp4")

    try:
        download_video(video_url, input_path)
        run_ffmpeg_command([
            "ffmpeg", "-ss", start, "-i", input_path,
            "-t", duration, "-c:v", "libx264", "-c:a", "aac", "-y", output_path
        ])
        public_url = f"/output/{os.path.basename(output_path)}"
        return {"url": public_url}
    finally:
        cleanup_files(input_path)

@app.post("/mute-video")
async def mute_video(
    video_url: str = Form(None),
    file: UploadFile = File(None)
):
    input_path = os.path.join(TMP_DIR, f"in_{uuid.uuid4()}.mp4")
    output_path = os.path.join(TMP_DIR, f"muted_{uuid.uuid4()}.mp4")

    try:
        if video_url:
            download_video(video_url, input_path)
        elif file:
            with open(input_path, "wb") as f_out:
                f_out.write(await file.read())
        else:
            raise HTTPException(400, detail="Must provide either 'video_url' or 'file'.")

        run_ffmpeg_command(["ffmpeg", "-i", input_path, "-an", output_path])
        public_url = f"/output/{os.path.basename(output_path)}"
        return {"url": public_url}
    finally:
        cleanup_files(input_path)

@app.post("/stitch-videos")
async def stitch_videos(
    video_url_1: str = Form(None),
    video_url_2: str = Form(None),
    file1: UploadFile = File(None),
    file2: UploadFile = File(None)
):
    path1 = os.path.join(TMP_DIR, f"part1_{uuid.uuid4()}.mp4")
    path2 = os.path.join(TMP_DIR, f"part2_{uuid.uuid4()}.mp4")
    concat_path = os.path.join(TMP_DIR, f"concat_{uuid.uuid4()}.mp4")
    txt_path = os.path.join(TMP_DIR, f"concat_{uuid.uuid4()}.txt")

    try:
        if video_url_1 and video_url_2:
            download_video(video_url_1, path1)
            download_video(video_url_2, path2)
        elif file1 and file2:
            with open(path1, "wb") as f1:
                f1.write(await file1.read())
            with open(path2, "wb") as f2:
                f2.write(await file2.read())
        else:
            raise HTTPException(400, detail="Must provide either two URLs or two uploaded files.")

        with open(txt_path, "w") as f:
            f.write(f"file '{path1}'\nfile '{path2}'\n")

        run_ffmpeg_command([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", txt_path, "-c", "copy", concat_path
        ])

        public_url = f"/output/{os.path.basename(concat_path)}"
        return {"url": public_url}
    finally:
        cleanup_files(path1, path2, txt_path)

# Optional: for local dev
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
