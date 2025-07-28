from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import uvicorn
import os
import uuid
import subprocess

app = FastAPI()

TMP_DIR = "/tmp/videos"
os.makedirs(TMP_DIR, exist_ok=True)

def run_ffmpeg_command(command: list):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")

@app.get("/")
def root():
    return {"message": "FFmpeg API is live"}

@app.post("/trim-video")
async def trim_video(file: UploadFile = File(...), start: str = Form(...), duration: str = Form(...)):
    input_path = os.path.join(TMP_DIR, f"in_{uuid.uuid4()}.mp4")
    output_path = os.path.join(TMP_DIR, f"trimmed_{uuid.uuid4()}.mp4")

    with open(input_path, "wb") as f:
        f.write(await file.read())

    run_ffmpeg_command([
        "ffmpeg", "-ss", start, "-i", input_path,
        "-t", duration, "-c", "copy", output_path
    ])

    return FileResponse(output_path, media_type="video/mp4")

@app.post("/mute-video")
async def mute_video(file: UploadFile = File(...)):
    input_path = os.path.join(TMP_DIR, f"in_{uuid.uuid4()}.mp4")
    output_path = os.path.join(TMP_DIR, f"muted_{uuid.uuid4()}.mp4")

    with open(input_path, "wb") as f:
        f.write(await file.read())

    run_ffmpeg_command([
        "ffmpeg", "-i", input_path, "-an", output_path
    ])

    return FileResponse(output_path, media_type="video/mp4")

@app.post("/stitch-videos")
async def stitch_videos(file1: UploadFile = File(...), file2: UploadFile = File(...)):
    path1 = os.path.join(TMP_DIR, f"part1_{uuid.uuid4()}.mp4")
    path2 = os.path.join(TMP_DIR, f"part2_{uuid.uuid4()}.mp4")
    concat_path = os.path.join(TMP_DIR, f"concat_{uuid.uuid4()}.mp4")
    txt_path = os.path.join(TMP_DIR, f"concat_{uuid.uuid4()}.txt")

    with open(path1, "wb") as f:
        f.write(await file1.read())
    with open(path2, "wb") as f:
        f.write(await file2.read())

    with open(txt_path, "w") as f:
        f.write(f"file '{path1}'\nfile '{path2}'\n")

    run_ffmpeg_command([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", txt_path, "-c", "copy", concat_path
    ])

    return FileResponse(concat_path, media_type="video/mp4")

# Optional: for local dev
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
