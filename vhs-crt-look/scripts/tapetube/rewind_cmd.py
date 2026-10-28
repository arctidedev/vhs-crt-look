"""The rewind command: decode the source span once (to a disk-backed buffer, so long spans stay out of memory),
then play it backwards through the look with the deck's search artifacts on the tape signal."""

from __future__ import annotations

import os
import shutil
import tempfile

import numpy as np

from . import media, pipeline, rewind, vhs


def render(
    cfg,
    src,
    out,
    t_from,
    t_to,
    duration=2.0,
    width=None,
    height=None,
    quality="standard",
    jobs=None,
    fps=None,
    reflection=None,
    progress=None,
):
    media.need_ffmpeg()
    info = media.probe(src)
    fps_f = pipeline.eval_fps(info["fps_str"]) if not fps else float(pipeline.eval_fps(str(fps)))
    dw, dh = info["width"], info["height"]
    fw, fh = (dw, dh) if cfg["frame"] == "native" else pipeline.output_size(dw, dh, cfg["frame"])
    ow, oh = pipeline.output_size(fw, fh, "native", width, height, even=True)
    cw = vhs.raster_width(ow / oh)
    lo, hi = sorted((float(t_from), float(t_to)))
    span_n = max(1, int(round((hi - lo) * fps_f)) + 1)
    need = span_n * cw * vhs.CH * 3
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free
    if need > free * 0.5:
        raise media.MediaError(f"the rewind span needs {need / 2**30:.1f} GiB of temporary space; shorten --from/--to")
    td = tempfile.mkdtemp(prefix=".vhslook_rw_", dir=os.path.dirname(os.path.abspath(out)) or ".")
    fsize = cw * vhs.CH * 3
    span = os.path.join(td, "span.raw")
    try:
        n = 0
        fps_str = f"{fps_f:.6f}"
        with open(span, "wb") as f:  # a plain file, not a memory map: Windows can delete it afterwards
            for fr in media.VideoReader(
                src, info, cw, vhs.CH, cfg["frame"], start=lo, duration=(hi - lo) + 1.5 / fps_f, fps_str=fps_str
            ):
                if n >= span_n:
                    break
                f.write(fr.tobytes())
                n += 1
        if n == 0:
            raise media.MediaError("no frames in the rewind span")
        n_out = max(2, int(round(float(duration) * fps_f)))
        pos, speed = rewind.speed_profile(n_out)

        def source(fh):
            for k in range(n_out):
                tau = t_from + (t_to - t_from) * pos[k]
                j = int(np.clip(round((tau - lo) * fps_f), 0, n - 1))
                fh.seek(j * fsize)
                yield k, np.frombuffer(fh.read(fsize), np.uint8).reshape(vhs.CH, cw, 3)

        with open(span, "rb") as fh:
            return pipeline.render_video(
                cfg,
                src,
                out,
                width,
                height,
                quality,
                fps=fps_str if fps else None,
                jobs=jobs,
                audio="none",
                reflection=reflection,
                progress=progress,
                frame_source=source(fh),
                post={"speed": [float(s) for s in speed]},
                total=n_out,
            )
    finally:
        shutil.rmtree(td, ignore_errors=True)
