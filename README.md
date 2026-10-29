# Local Multivideo Composer (prototype)

A localhost-only browser UI for aligning videos, arranging them on a canvas, previewing synchronization, and exporting with FFmpeg. No cloud services or accounts.

## Requirements

- Python 3.10+
- FFmpeg **and FFprobe** available on your PATH
- Modern browser (Chrome, Edge, Firefox)

## Install / run

```bash
cd multivideo-composer
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765**. Stop with Ctrl+C.

## Use

1. Add one or more video files.
2. Drag each track horizontally to adjust its start offset; select a track to enter an exact offset in seconds.
3. Play/pause, scrub, change playback speed, or step one output frame at a time.
4. Select and drag a video in the canvas; drag the lower-right handle to resize. Set fractional source crop margins in the inspector (0–0.95).
5. Select output format and click **Render export**. Exported files also remain in `workspace/exports`.
6. Save a JSON project. Keep `workspace/uploads` to reopen that project later.

## Important prototype limitations

- Audio is intentionally omitted from the export. Preview videos are muted.
- Videos are browser-decoded for interactive preview, so simultaneous playback and frame stepping are **best effort**, not guaranteed sample/frame exact. FFmpeg export uses source timestamps and a selected output frame rate.
- Video offset is the *start position on the output timeline*. The first frame of every video starts at its offset; negative offsets and source trimming are not implemented.
- Source files are copied into `workspace/uploads` and referenced by generated safe IDs. Avoid deleting this directory while using saved projects.
- Output uses a black background. Canvas objects may overlap and are ordered by import order.
- Cropping is numeric in the inspector (not draggable crop handles yet).
- Large files and exports can consume significant disk space and CPU. There is no progress percentage, only working/done/error.
- No authentication is included. **Keep binding to 127.0.0.1** and do not expose the port publicly.
- For still export, choose the frame with the master scrubber before rendering.
- The browser may not preview codecs such as HEVC even when FFmpeg can export them; MP4 H.264 is the most compatible input.

## Project structure

- `app.py`: local FastAPI app, video upload, FFprobe, FFmpeg rendering jobs
- `static/index.html`: UI
- `static/style.css`: UI styling
- `static/app.js`: timeline, playback, canvas, project state
- `workspace/`: generated at runtime; uploaded source copies and exports
# multivideo_composer
# multivideo_composer
