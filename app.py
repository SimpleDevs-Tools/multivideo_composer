from __future__ import annotations
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'workspace'
UPLOADS = DATA / 'uploads'
EXPORTS = DATA / 'exports'
for folder in (UPLOADS, EXPORTS): folder.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='Local Multivideo Composer')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.mount('/media', StaticFiles(directory=UPLOADS), name='media')
app.mount('/exports', StaticFiles(directory=EXPORTS), name='exports')
JOBS = {}

class RenderRequest(BaseModel):
    project: dict
    format: str = 'mp4'
    time: float = 0.0

@app.get('/')
def index(): return FileResponse(ROOT / 'static' / 'index.html')

@app.post('/api/upload')
async def upload(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        ext = Path(f.filename or '').suffix.lower()
        if ext not in {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}:
            raise HTTPException(400, f'Unsupported video extension: {ext}')
        uid = uuid.uuid4().hex
        name = uid + ext
        target = UPLOADS / name
        with target.open('wb') as out:
            while chunk := await f.read(1024 * 1024): out.write(chunk)
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(target)], capture_output=True, text=True, check=True)
            duration = float(json.loads(probe.stdout)['format']['duration'])
        except Exception:
            target.unlink(missing_ok=True)
            raise HTTPException(400, f'Cannot read video: {f.filename}')
        results.append({'id': uid, 'file': name, 'name': f.filename, 'duration': duration, 'url': '/media/' + quote(name)})
    return results

def even(x): return max(2, int(round(float(x) / 2) * 2))

def render(job_id, req):
    job = JOBS[job_id]
    try:
        p = req.project
        clips = p.get('clips', [])
        if not clips: raise ValueError('Add a video before exporting')
        fmt = req.format.lower()
        if fmt not in ('mp4', 'webm', 'mov', 'gif', 'png', 'jpg'): raise ValueError('Unsupported format')
        width, height = even(p.get('width', 1280)), even(p.get('height', 720))
        fps = min(120, max(1, float(p.get('fps', 30))))
        duration = max(float(c['offset']) + float(c['duration']) for c in clips)
        still = fmt in ('png', 'jpg')
        duration = max(duration, 1 / fps)
        cmd = ['ffmpeg', '-hide_banner', '-y', '-loglevel', 'error']
        # Inputs loop their last frame; timeline visibility is explicitly gated below.
        for c in clips:
            file = str(c['file'])
            if Path(file).name != file or not (UPLOADS / file).is_file(): raise ValueError('Invalid source file')
            cmd += ['-i', str(UPLOADS / file)]
        base = f'color=c=black:s={width}x{height}:r={fps}:d={duration:.6f},format=rgba[base]'
        filters = [base]
        last = 'base'
        for i, c in enumerate(sorted(enumerate(clips), key=lambda item: item[1].get('z', item[0]))):
            source_index, clip = c
            x, y = int(round(float(clip['x']))), int(round(float(clip['y'])))
            w, h = even(clip['w']), even(clip['h'])
            crop = clip.get('crop', {})
            left = max(0, min(.95, float(crop.get('left', 0))))
            top = max(0, min(.95, float(crop.get('top', 0))))
            right = max(0, min(.95, float(crop.get('right', 0))))
            bottom = max(0, min(.95, float(crop.get('bottom', 0))))
            if left + right >= .99 or top + bottom >= .99: raise ValueError('Invalid crop')
            off = float(clip['offset'])
            dur = float(clip['duration'])
            # Crop source in normalized coordinates; scale cropped content to displayed rectangle.
            chain = (f'[{source_index}:v]setpts=PTS-STARTPTS,'
                     f'crop=iw*{1-left-right:.8f}:ih*{1-top-bottom:.8f}:iw*{left:.8f}:ih*{top:.8f},'
                     f'scale={w}:{h}:flags=lanczos,setsar=1,format=rgba,'
                     f'setpts=PTS+{off:.6f}/TB[v{source_index}]')
            filters.append(chain)
            output = f'out{source_index}'
            filters.append(f'[{last}][v{source_index}]overlay=x={x}:y={y}:eof_action=pass:enable=\'between(t,{off:.6f},{off+dur:.6f})\'[{output}]')
            last = output
        filters.append(f'[{last}]format=yuv420p[vfinal]' if fmt in ('mp4','mov','webm') else f'[{last}]format=rgb24[vfinal]')
        # GIF needs palette generation to avoid poor default colors.
        if fmt == 'gif':
            filters.append('[vfinal]split[gifsrc][palettesrc]')
            filters.append('[palettesrc]palettegen=stats_mode=diff[palette]')
            filters.append('[gifsrc][palette]paletteuse=dither=bayer[rendered]')
            mapping = '[rendered]'
        else: mapping = '[vfinal]'
        cmd += ['-filter_complex', ';'.join(filters), '-map', mapping, '-an']
        if still:
            cmd += ['-ss', f'{max(0, float(req.time)):.6f}', '-frames:v', '1', '-update', '1']
        elif fmt == 'mp4': cmd += ['-c:v', 'libx264', '-crf', '20', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart']
        elif fmt == 'mov': cmd += ['-c:v', 'libx264', '-crf', '20', '-preset', 'veryfast', '-pix_fmt', 'yuv420p']
        elif fmt == 'webm': cmd += ['-c:v', 'libvpx-vp9', '-crf', '32', '-b:v', '0']
        elif fmt == 'gif': cmd += ['-loop', '0']
        if not still: cmd += ['-t', f'{duration:.6f}']
        filename = f'composition-{job_id[:8]}.{fmt}'
        cmd.append(str(EXPORTS / filename))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode: raise RuntimeError(result.stderr[-3000:])
        job.update(status='done', url='/exports/' + filename)
    except Exception as exc:
        job.update(status='error', error=str(exc))

@app.post('/api/render')
def start_render(req: RenderRequest):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {'status': 'working'}
    threading.Thread(target=render, args=(job_id, req), daemon=True).start()
    return {'id': job_id}

@app.get('/api/render/{job_id}')
def render_status(job_id: str):
    if job_id not in JOBS: raise HTTPException(404, 'Job not found')
    return JOBS[job_id]
