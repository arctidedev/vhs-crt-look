"""A VCR in rewind search (the film's breakdown/tools/rewind_vhs.py): the source runs backwards fast, as a 1987 deck
shows it. In visible search the heads cross several tracks per field, so noise bars (snow with bright streaks) roll
down the picture with the picture from alternate tracks between them; rows shift sideways in a sawtooth with each
bar (the shuttle's time-base error); the bottom lines bend at the head switch; the picture bounces a little while
the deck changes speed. Ease: from play speed into search and out again onto the target."""

from __future__ import annotations

import math

import cv2
import numpy as np

from .sigproc import shift_rows


def speed_profile(n: int):
    """(source position 0..1, search strength 0..1) for each of n output frames."""
    u = np.linspace(0, 1, n)
    w = np.sin(np.pi * u) ** 0.6
    pos = np.cumsum(w)
    pos = (pos - pos[0]) / max(pos[-1] - pos[0], 1e-9)
    speed = np.clip(w * 1.25 - 0.1, 0, 1)
    return pos, speed


def search(yiq: np.ndarray, rng, i: int, speed: float) -> np.ndarray:
    """Search artifacts on a YIQ tape signal, their strength following the shuttle speed (0 = play, 1 = search)."""
    LINES, SW = yiq.shape[:2]
    L = np.arange(LINES, dtype=np.float32)
    s = float(np.clip(speed, 0, 1))
    out = yiq.copy()
    if s <= 0.01:
        return out
    nb = 3
    phase = (i * 0.37) % 1.0
    noise_w = np.zeros(LINES, np.float32)
    for b in range(nb):
        yc = ((b + phase) / nb) * (LINES + 60) - 30
        band = np.exp(-0.5 * ((L - yc) / (7 + 5 * s)) ** 2)
        noise_w = np.maximum(noise_w, band)
    dx = s * (6 * ((L / LINES * nb + phase) % 1.0) - 3)
    dx = dx + s * rng.normal(0, 1.2, LINES)
    hs = L >= LINES - 22
    dx[hs] += s * (L[hs] - (LINES - 22)) * 1.6
    out = shift_rows(out, dx.astype(np.float32))
    Y = out[..., 0]
    nz = rng.random((LINES, SW)).astype(np.float32)
    streak = cv2.GaussianBlur(nz, (0, 0), sigmaX=6, sigmaY=0.4)
    snow = 0.25 + 0.6 * nz * (0.6 + 0.8 * streak)
    w = (noise_w * s)[:, None]
    out[..., 0] = Y * (1 - w) + snow * w
    out[..., 1:] *= (1 - 0.8 * w)[..., None]
    # the vertical bounce while the deck changes speed
    bounce = int(round(3 * math.sin(i * 1.7) * s * (1 - s) * 4))
    if bounce:
        out = np.roll(out, bounce, axis=0)
    return out


def search_post(speed: float):
    return lambda yiq, rng, i: search(yiq, rng, i, speed)
