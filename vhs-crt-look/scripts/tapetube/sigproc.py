"""Small signal-processing helpers on numpy + OpenCV only.

gauss1d / gauss2d reproduce scipy.ndimage.gaussian_filter1d / gaussian_filter (mode 'reflect', truncate 4.0):
same kernel radius, same weights, same border rule (scipy 'reflect' is OpenCV BORDER_REFLECT). The look test
that the film used was written against SciPy; this keeps the port numerically faithful without that dependency.
"""

from __future__ import annotations

import cv2
import numpy as np

SRGB_A = 0.055


def _kernel(sigma: float, truncate: float = 4.0) -> np.ndarray:
    r = int(truncate * float(sigma) + 0.5)
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 / (sigma * sigma) * x * x)
    return (k / k.sum()).astype(np.float32)


_ONE = np.ones(1, np.float32)


def _sep(a: np.ndarray, kx: np.ndarray, ky: np.ndarray) -> np.ndarray:
    a = np.ascontiguousarray(a, np.float32)
    if a.ndim == 3 and a.shape[2] not in (1, 3, 4):
        return np.stack([_sep(a[..., c], kx, ky) for c in range(a.shape[2])], -1)
    out = cv2.sepFilter2D(a, -1, kx, ky, borderType=cv2.BORDER_REFLECT)
    if a.ndim == 3 and out.ndim == 2:
        out = out[..., None]
    return out


def gauss1d(a: np.ndarray, sigma: float, axis: int = -1) -> np.ndarray:
    """scipy.ndimage.gaussian_filter1d(a, sigma, axis) for 1-D, 2-D and (H, W, C) float arrays (axis 0 or 1)."""
    a = np.asarray(a, np.float32)
    if sigma <= 0:
        return a.copy()
    k = _kernel(sigma)
    if a.ndim == 1:
        r = len(k) // 2
        p = np.pad(a, r, mode="symmetric")
        return np.convolve(p, k, mode="valid").astype(np.float32)
    axis = axis % a.ndim
    if axis == 1:
        return _sep(a, k, _ONE)
    if axis == 0:
        return _sep(a, _ONE, k)
    raise ValueError("gauss1d filters along axis 0 or 1 only")


def gauss2d(a: np.ndarray, sy: float, sx: float) -> np.ndarray:
    """scipy.ndimage.gaussian_filter(a, (sy, sx[, 0]))."""
    ky = _kernel(sy) if sy > 0 else _ONE
    kx = _kernel(sx) if sx > 0 else _ONE
    return _sep(a, kx, ky)


def big_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Wide Gaussian via a downsampled pass (the look test's big_blur)."""
    if sigma <= 0:
        return img.copy()
    if sigma < 6:
        return cv2.GaussianBlur(img, (0, 0), sigma)
    f = max(1, int(sigma / 4))
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma / f)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def shift_rows(a: np.ndarray, dx: np.ndarray) -> np.ndarray:
    """Shift each line of a (L, W[, C]) array right by dx[line] samples (linear interpolation)."""
    L, Wd = a.shape[:2]
    mapx = (np.arange(Wd, dtype=np.float32)[None, :] - dx[:, None]).astype(np.float32)
    mapy = np.repeat(np.arange(L, dtype=np.float32)[:, None], Wd, 1)
    return cv2.remap(a, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def frac_shift(a: np.ndarray, d: float) -> np.ndarray:
    M = np.float32([[1, 0, d], [0, 1, 0]])
    return cv2.warpAffine(
        a,
        M,
        (a.shape[1], a.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + SRGB_A) / (1 + SRGB_A)) ** 2.4).astype(np.float32)


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, (1 + SRGB_A) * np.power(c, 1 / 2.4) - SRGB_A).astype(np.float32)
