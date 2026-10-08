"""Construye el anuncio completo.

    python3 tools/build.py              # todo (si ya hay captura de la tienda, la reutiliza)
    python3 tools/build.py --store      # vuelve a grabar también la tienda

Pasos: grabar la tienda (tools/capture_store.cjs) → fotogramas del fragmento LED →
render del anuncio en paralelo con desenfoque de movimiento (tools/render_promo.cjs) →
música (tools/music.py) → vídeo final a -14 LUFS, versión ligera para WhatsApp y portada.
"""
import json
import os
import struct
import subprocess
import sys
import threading
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
OUT = ROOT / "video"
FPS = 30
DUR = 19.8
NAME = "AlldesignKarl_Tienda_Online_1080x1920"
NODE_ENV = dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip())


def run(cmd, **kw):
    print("·", " ".join(str(c) for c in cmd)[:160], flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def capture_store(force):
    if force or not (BUILD / "store" / "meta.json").exists():
        run(["node", "tools/capture_store.cjs", "build/store"], env=NODE_ENV)


def clip_frames():
    d = BUILD / "clips" / "resina"
    if not (d / "f0099.jpg").exists():
        d.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-i", "assets/clips/resina_led.mp4", "-q:v", "2", str(d / "f%04d.jpg")])


def read_exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError
    return b


def render_frames(workers):
    frames = BUILD / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    total = int(round(DUR * FPS))
    todo = [i for i in range(total) if not (frames / f"f{i:05d}.png").exists()]
    if not todo:
        return total
    a0, a1 = todo[0], total
    step = -(-(a1 - a0) // workers)
    errors = []

    def worker(a, b):
        p = subprocess.Popen(["node", "tools/render_promo.cjs", "--frames", f"{a}:{b}"], cwd=ROOT, env=NODE_ENV,
                             stdout=subprocess.PIPE, stderr=sys.stderr)
        rng = np.random.default_rng(a)
        try:
            while True:
                try:
                    idx, n = struct.unpack("<II", read_exact(p.stdout, 8))
                except EOFError:
                    break
                acc = None
                for _ in range(n):
                    (ln,) = struct.unpack("<I", read_exact(p.stdout, 4))
                    im = np.asarray(Image.open(BytesIO(read_exact(p.stdout, ln))).convert("RGB"), dtype=np.float32)
                    acc = im if acc is None else acc + im
                acc /= n
                # tramado triangular: evita escalones en los degradados al pasar a 8 bits
                acc += rng.random(acc.shape, dtype=np.float32) - rng.random(acc.shape, dtype=np.float32)
                Image.fromarray(np.clip(acc + 0.5, 0, 255).astype(np.uint8)).save(frames / f"f{idx:05d}.png", compress_level=1)
                if idx % 30 == 0:
                    print(f"  fotograma {idx}/{total}", flush=True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
        if p.wait() != 0:
            errors.append(RuntimeError(f"render {a}:{b} terminó con error"))

    threads = [threading.Thread(target=worker, args=(a, min(a1, a + step))) for a in range(a0, a1, step)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    return total


def music():
    (BUILD / "audio").mkdir(parents=True, exist_ok=True)
    run([sys.executable, "tools/music.py", "build/audio/musica.f32"])
    raw = ["-f", "f32le", "-ar", "48000", "-ac", "2", "-i", "build/audio/musica.f32"]
    # dos pasadas de normalización: -14 LUFS con el pico real por debajo de -1,5 dB (Instagram, TikTok, YouTube)
    # limitador suave antes de normalizar: así la normalización es una ganancia lineal (sin bombeo)
    # y el pico real queda holgado incluso después de comprimir a AAC
    lim = "alimiter=limit=0.66:attack=2:release=80:level=0,"
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *raw, "-af", lim + "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                          cwd=ROOT, capture_output=True, text=True).stderr
    m = json.loads(meas[meas.rindex("{"):meas.rindex("}") + 1])
    flt = (lim + f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
           f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    OUT.mkdir(exist_ok=True)
    (ROOT / "audio").mkdir(exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", *raw, "-af", flt, "-c:a", "flac", "-sample_fmt", "s32", "audio/banda_sonora.flac"])


def encode(total):
    color = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    vf = "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
    final = OUT / f"{NAME}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", "build/frames/f%05d.png", "-i", "audio/banda_sonora.flac",
         "-frames:v", str(total), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-profile:v", "high", "-level", "4.2",
         "-tune", "film", *color, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(final)])
    run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vf", "scale=720:1280:flags=lanczos,format=yuv420p", "-c:v", "libx264",
         "-preset", "slow", "-crf", "22", "-profile:v", "high", *color, "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
         str(OUT / f"{NAME.replace('_1080x1920', '')}_WhatsApp_720p.mp4")])
    Image.open(BUILD / "frames" / f"f{int(18.6 * FPS):05d}.png").convert("RGB").save(OUT / "portada.jpg", quality=92)


if __name__ == "__main__":
    capture_store("--store" in sys.argv)
    clip_frames()
    if "--fresh" in sys.argv:
        for f in (BUILD / "frames").glob("*.png"):
            f.unlink()
    n = render_frames(int(os.environ.get("WORKERS", "3")))
    music()
    encode(n)
    print("listo:", OUT)
