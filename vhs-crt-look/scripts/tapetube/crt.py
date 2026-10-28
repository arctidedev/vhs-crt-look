"""The CRT of "My Own Funeral" in numpy: a port of the film's three.js tube (comp/index_bd2.html, face and glass
shaders and the camera passes) with the look test's band-limited phosphor masks (looktest.py phosphor_mask).
No GPU, no browser: every output pixel is computed in linear light, never an overlay.

Layers (cumulative, as in the breakdown):
  L0 the signal on the raster, through the tube's drive (gamma)
  L1 480 Gaussian beam lines, each line's width grows with that gun's current; white smear to the right
  L2 the phosphor mask (slot, aperture grille with damper wires, or dot triads), band-limited by the camera's PSF so
     it resolves only when the screen is large in frame and fades (never aliases) when it is small
  L3 faceplate bloom, halation (also past the raster edge), whites blooming, milky lift and scatter
  L4 the front glass: tube black, the room's reflection, the lamp's specular
  L5 the tube's light on its surround (the bezel's inner lip), visible when the bezel is in frame
  L6 the filming camera: one recorded 240-line field, the refresh roll of an unsynced shutter, lens bloom and glare,
     camera grain

Geometry: the camera looks straight at the tube; `fill` sets how much of the frame the raster spans and
`curvature` bends a flat 2005 face (0) toward a curved older set (1). Overscan (7 %), the residual pincushion, the
rounded raster corners with soft edges and the beam defocus toward the corners come from the film.
"""

from __future__ import annotations

import math
from typing import Optional

import cv2
import numpy as np

from .sigproc import gauss1d, gauss2d, linear_to_srgb, smoothstep

LUM709 = np.array([0.2126, 0.7152, 0.0722], np.float32)


def luma(x):
    return x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722


LAYER_NAMES = ["signal", "beams", "mask", "glow", "glass", "light", "camera"]


def comb(x, s, per_px, roll=0.45):
    """Sum of unit-area Gaussians (sigma s, period 1) at the integers, mean 1, as a Fourier series. Harmonics above
    `roll` cycles per output pixel are rolled off so the pattern can never alias (looktest.comb, shader roll())."""
    out = np.ones_like(x)
    n = 1
    while n <= 32:
        a = math.exp(-2 * math.pi**2 * s * s * n * n) * float(np.clip((roll - n * per_px) / 0.15, 0, 1))
        if a < 1e-3:
            break
        out = out + np.float32(2 * a) * np.cos(np.float32(2 * math.pi * n) * x)
        n += 1
    return out


def square_blur(x, s, per_px, roll=0.45):
    """Band-limited square wave in [0, 1] with period 2 (the stagger phase of slot-mask columns)."""
    out = np.full_like(x, 0.5)
    for n in range(1, 30, 2):
        a = math.exp(-2 * math.pi**2 * s * s * (n / 2) ** 2) * float(np.clip((roll - n / 2 * per_px) / 0.15, 0, 1))
        if a < 1e-3:
            break
        out = out + np.float32((2 / math.pi) * a / n) * np.sin(np.float32(math.pi * n) * x)
    return out


def phosphor_mask(pqx, pqy, C, triads, per_px, aspect, roll):
    """Per-channel mask (h, w, 3), mean 1, on face coordinates pq in [-0.5, 0.5]. RGB order."""
    xm = (pqx + 0.5) * triads
    ym = (pqy + 0.5) * triads / aspect  # same physical units vertically
    sc = C["cam_psf"] * per_px  # camera PSF in triad units
    M = np.empty(pqx.shape + (3,), np.float32)
    kind = C["mask"]
    if kind == "grille":
        s = math.hypot(C["stripe_sigma"], sc)
        for c in range(3):
            M[..., c] = comb(xm - c / 3.0, s, per_px, roll)
    elif kind == "dot":
        h = 0.2887  # row spacing in triad units (equal nearest-neighbour distance 1/3)
        s = math.hypot(C["dot_sigma"], sc)
        ra = comb(ym / (2 * h), s / (2 * h), per_px / (2 * h), roll)
        rb = comb(ym / (2 * h) - 0.5, s / (2 * h), per_px / (2 * h), roll)
        for c in range(3):
            M[..., c] = 0.5 * (
                comb(xm - c / 3.0, s, per_px, roll) * ra + comb(xm - c / 3.0 - 0.5, s, per_px, roll) * rb
            )
    else:  # slot mask: R, G, B slots in staggered columns with thin bridges
        s = math.hypot(C["stripe_sigma"], sc)
        pv = C["slot_pitch"]
        sb = math.hypot(C["bridge_sigma"], sc) / pv
        b = C["slot_bridge"]
        ph = square_blur(xm, sc / 2.0, per_px, roll)
        bridges0 = comb(ym / pv, sb, per_px / pv, roll)
        bridges1 = comb(ym / pv - 0.5, sb, per_px / pv, roll)
        S = (1 - b * ((1 - ph) * bridges0 + ph * bridges1)) / (1 - b)
        for c in range(3):
            M[..., c] = comb(xm - c / 3.0, s, per_px, roll) * S
    if kind == "grille":
        for vw in C.get("damper_wires", []):  # thin wire shadows, energy-correct when blurred by the camera
            sv = C["wire_sigma"] / triads * aspect
            se = math.hypot(C["wire_sigma"], sc) / triads * aspect
            M *= (1 - C["wire_depth"] * (sv / se) * np.exp(-0.5 * ((pqy + 0.5 - vw) / se) ** 2))[..., None]
    return M


def _sample(img, mx, my, border=cv2.BORDER_CONSTANT):
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=border)


def _lin(x, gamma):
    return np.clip(x, 0, 1) ** gamma


def _rounded_sd(fx, fy, hx, hy, r):
    dqx = np.abs(fx) - (hx - r)
    dqy = np.abs(fy) - (hy - r)
    return np.sqrt(np.maximum(dqx, 0) ** 2 + np.maximum(dqy, 0) ** 2) + np.minimum(np.maximum(dqx, dqy), 0) - r


def _default_room(h, w):
    """A dim, very soft room behind the camera for the glass to mirror (used when no reflection image is given):
    a lighter wall above, darker furniture below, a warm practical up left."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = xx / max(w - 1, 1), yy / max(h - 1, 1)
    room = 0.05 + 0.10 * smoothstep(0.85, 0.25, v)
    room = room + 0.35 * np.exp(-(((u - 0.2) / 0.12) ** 2 + ((v - 0.22) / 0.1) ** 2))
    room = room * (1 - 0.6 * np.exp(-(((u - 0.55) / 0.22) ** 2 + ((v - 0.78) / 0.22) ** 2)))
    return np.stack([room * 1.0, room * 0.93, room * 0.82], -1).astype(np.float32)


def render(
    sig: np.ndarray,
    C: dict,
    T: dict,
    CAM: dict,
    out_w: int,
    out_h: int,
    t: float = 0.0,
    parity: int = 0,
    on: Optional[dict] = None,
    ss: int = 1,
    alpha: Optional[np.ndarray] = None,
    reflection: Optional[np.ndarray] = None,
    grain_rng=None,
    strip: int = 192,
):
    """The tube showing `sig` (LINES x SW gamma-encoded RGB, what leaves the VCR), as an out_w x out_h sRGB float
    image (and the picture's alpha when `alpha` (LINES x SW, 0..1) is given). on = {beams, mask, glow, glass, light,
    camera}: the layers to include (all by default)."""
    on = {k: True for k in LAYER_NAMES[1:]} if on is None else on
    LINES, SW = sig.shape[:2]
    tube_gamma = C["gamma"]
    gain = C["gain"]
    A_p = SW / 720.0  # picture aspect (720 samples per picture height along a line)
    A_f = out_w / out_h
    fill = float(T.get("fill", 1.0))
    curv = float(T.get("curvature", 0.0))
    hp, wp = (A_f / A_p, A_f) if A_p >= A_f else (1.0, A_p)
    hp, wp = hp * fill, wp * fill  # raster size in frame-height units
    pic_h_px = hp * out_h
    lpp = LINES / C["overscan"] / pic_h_px  # lines per output pixel
    spp = SW / C["overscan"] / (wp * out_h)  # samples per output pixel
    scl = C["cam_psf"] * lpp
    triads = C["triads_across"] * A_p / (4.0 / 3.0)
    tpp = triads / (wp * out_h)  # triads per output pixel
    roll = float(T.get("maskRoll", 0.45))
    mask_k = float(T.get("maskK", 1.0))
    halfx, halfy = A_p / 2.0, 0.5
    cr = T["cornerR"]
    soft = T["edgeSoft"] * A_p
    beam_k = float(T.get("beamK", 1.0))
    bmin, bmax = C["beam_min"] * beam_k, C["beam_max"] * beam_k
    field = bool(on.get("camera")) and bool(T.get("fieldOnly", 0))
    conv = max(float(T.get("conv", 0.0)), float(C.get("convergence", 0.0)))
    glow = bool(on.get("glow"))
    glass = bool(on.get("glass"))
    light = bool(on.get("light"))
    camera = bool(on.get("camera"))

    lin = _lin(sig, tube_gamma).astype(np.float32)
    mean_lin = lin.reshape(-1, 3).mean(0) * gain
    sx = math.hypot(C["beam_h"] * 1.5 * beam_k, C["cam_psf"] * spp)
    linb = gauss1d(lin, sx, axis=1) if sx > 0.3 else lin
    # faceplate light at the tape's own resolution (the shader's mip lookups, as Gaussians in samples and lines)
    sig_c = np.clip(sig, 0, 1).astype(np.float32)
    s_sc = C["bloom_r"] * 960.0
    s_ha = C["halation_r"] * 960.0
    scat_t = _lin(gauss2d(sig_c, s_sc, s_sc), tube_gamma)
    hal_t = _lin(gauss2d(sig_c, s_ha, s_ha), tube_gamma)
    hi_t = np.maximum(_lin(gauss2d(sig_c, 2.0, 2.0), tube_gamma) - 0.42, 0) + 0.5 * np.maximum(scat_t - 0.35, 0)
    smear_t = None
    if T.get("smear", 0) > 0 and on.get("beams"):
        base = _lin(gauss2d(sig_c, 1.41, 1.41), tube_gamma)
        acc_s, ws = np.zeros_like(base), 0.0
        for j in range(1, 7):
            w = math.exp(-j / 2.5)
            ws += w
            M = np.float32([[1, 0, j * T["smearLen"] / 6.0 * SW / 960.0], [0, 1, 0]])
            sh = cv2.warpAffine(base, M, (SW, LINES), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            acc_s += w * np.maximum(sh - 0.35, 0)
        smear_t = acc_s / ws
    tint = np.array(T.get("tint", [1, 1, 1]), np.float32)
    pic_lift = np.array(T.get("picLift", [0, 0, 0]), np.float32) if glow else np.zeros(3, np.float32)
    scatter_k = float(T.get("scatter", 0.0)) if glow else 0.0
    glass_black = np.array(T["glassBlack"], np.float32) if glass else np.zeros(3, np.float32)
    exposure = float(CAM.get("exposure", 1.0))

    Wr, Hr = out_w * ss, out_h * ss
    xs = (((np.arange(Wr, dtype=np.float32) + 0.5) / Wr) - 0.5) * A_f
    out = np.empty((Hr, Wr, 3), np.float32)
    a_out = np.empty((Hr, Wr), np.float32) if alpha is not None else None
    room = None
    if glass and T.get("reflection", 0) > 0:
        room = reflection if reflection is not None else _default_room(256, int(256 * A_f))
        room = cv2.resize(room, (Wr, Hr), interpolation=cv2.INTER_LINEAR)
        rb = T.get("reflBlur_px", 18) * out_w / 1440.0 * ss
        room = cv2.GaussianBlur(room, (0, 0), max(rb, 0.5))[:, ::-1]
    # the bezel opening: the raster plus an even black tube border, rounded
    ohx, ohy, ocr = halfx + 0.03, halfy + 0.03, 0.06

    for y0 in range(0, Hr, strip):
        y1 = min(Hr, y0 + strip)
        ys = ((np.arange(y0, y1, dtype=np.float32) + 0.5) / Hr) - 0.5
        X, Y = np.meshgrid(xs, ys)
        pqx, pqy = X / wp, Y / hp
        pqx0, pqy0 = pqx, pqy
        if curv > 0:  # a curved face seen head on: the raster's edges bow outward, its corners pull in
            k = 0.18 * curv
            pqx, pqy = pqx * (1 + k * (2 * pqy) ** 2), pqy * (1 + k * (2 * pqx) ** 2)
        r2 = (2 * pqx) ** 2 + (2 * pqy) ** 2
        fbx = 2 * halfx * pqx / (1 + T["edgeBow"] * (1 - 4 * pqy * pqy))
        fby = 2 * halfy * pqy / (1 + T["edgeBow"] * (1 - 4 * pqx * pqx))
        sd = _rounded_sd(fbx, fby, halfx, halfy, cr)
        inP = 1 - smoothstep(-soft, soft, sd)
        foc = 1 + T["defocus"] * r2
        g = 1 - C["geom_k"] * r2
        tux = pqx * g / C["overscan"] + 0.5
        tuy = pqy * g / C["overscan"] + 0.5
        mx = (tux * SW - 0.5).astype(np.float32)
        ly = tuy * LINES
        if on.get("beams"):
            smax = math.sqrt((bmax * float(foc.max())) ** 2 + scl * scl)
            R = int(math.ceil(3 * smax)) + 1
            n0 = np.floor(ly - 0.5).astype(np.int32)
            acc = np.zeros(X.shape + (3,), np.float32)
            cw = (2 * pqx) ** 2
            cvv = conv * cw * np.sign(pqy) * 4 * pqy * pqy if conv else None
            cvh = conv * 1.5 / 960.0 * 2 * pqx * cw * SW if conv else None
            for kk in range(-R + 1, R + 1):
                n = n0 + kk
                ok = (n >= 0) & (n < LINES)
                if field:
                    ok &= (n & 1) == parity
                if not ok.any():
                    continue
                ny = np.clip(n, 0, LINES - 1).astype(np.float32)
                v = _sample(linb, mx, ny)
                if conv:
                    v[..., 0] = _sample(linb[..., 0], mx + cvh, ny)
                    v[..., 2] = _sample(linb[..., 2], mx - cvh, ny)
                sb = (bmin + (bmax - bmin) * np.power(np.maximum(v, 0), C["beam_pow"])) * foc[..., None]
                s2 = sb * sb + scl * scl
                d = (ly - (n + 0.5))[..., None]
                if conv:
                    d = d + np.stack([cvv, np.zeros_like(cvv), -cvv], -1)
                w = (2.0 if field else 1.0) * ok
                acc += (w[..., None] * v) * np.exp(-0.5 * d * d / s2) / (np.sqrt(s2) * 2.5066283)
        else:
            acc = _sample(lin, mx, (ly - 0.5).astype(np.float32))
        if on.get("mask"):
            M = phosphor_mask(pqx, pqy, C, triads, tpp, A_p, roll)
            if mask_k != 1.0:
                M = 1 + mask_k * (M - 1)
            crt = acc * M * gain
        else:
            crt = acc * gain
        crt *= (1 - T["cornerDim"] * np.power(r2 * 0.5, 1.5))[..., None]
        tmx = (np.clip(tux, 0, 1) * SW - 0.5).astype(np.float32)
        tmy = (np.clip(tuy, 0, 1) * LINES - 0.5).astype(np.float32)
        if smear_t is not None:
            crt += T["smear"] * gain * _sample(smear_t, tmx, tmy, cv2.BORDER_REPLICATE)
        contrast = float(T.get("contrast", 1.0))
        if contrast != 1.0:
            crt = gain * np.power(np.maximum(crt / gain, 0), contrast)
        lum = luma(crt)[..., None]
        crt = (lum + float(T.get("sat", 1.0)) * (crt - lum)) * tint
        if camera and T.get("roll", 0) > 0:  # unsynced film shutter vs 60 Hz: a soft bar rolls down
            dy = np.abs(np.mod(tuy - math.fmod(t * T["rollRate"], 1.0) + 0.5, 1.0) - 0.5)
            crt *= (1 - T["roll"] * np.exp(-0.5 * dy * dy / (T["rollW"] ** 2)))[..., None]
        crt = crt * inP[..., None]
        if glow:
            scat = _sample(scat_t, tmx, tmy, cv2.BORDER_REPLICATE)
            hal = _sample(hal_t, tmx, tmy, cv2.BORDER_REPLICATE)
            hi = _sample(hi_t, tmx, tmy, cv2.BORDER_REPLICATE)
            out1 = np.exp(-np.maximum(sd, 0) / (0.012 * halfx))
            crt += gain * (
                (C["bloom_amt"] * scat + T["hiBloom"] * hi) * inP[..., None] + C["halation_amt"] * hal * out1[..., None]
            )
        col = glass_black + crt + inP[..., None] * (pic_lift + scatter_k * mean_lin * tint)
        # the bezel opening (only in frame when fill < 1)
        osd_ = _rounded_sd(2 * halfx * pqx0, 2 * halfy * pqy0, ohx, ohy, ocr)
        inG = 1 - smoothstep(-0.0015, 0.0015, osd_)
        if glass:
            if room is not None:
                col += T["reflection"] * room[y0:y1]
            lamp = np.exp(-0.5 * (((pqx + 0.22) / 0.34) ** 2 + ((pqy + 0.24) / 0.33) ** 2))
            col += (T["specular"] * lamp)[..., None] * np.array([1.0, 0.92, 0.8], np.float32)
            sh = np.exp(-((pqx + 0.42) ** 2 + (pqy + 0.4) ** 2) / (0.02 + 0.05 * curv))
            col += (T["sheen"] * (0.3 + curv) * sh)[..., None] * np.array([1.0, 0.86, 0.66], np.float32)
        col = col * exposure
        if fill < 1.2:
            bez = np.array(T.get("bezel", [0.016, 0.0145, 0.013]), np.float32)
            shade = (0.75 + 0.5 * np.clip(0.5 - Y, 0, 1))[..., None]
            bcol = bez * shade
            if light:  # the picture's light on the bezel's inner lip and face
                dist = np.maximum(osd_, 0)
                bcol = bcol + (T["lipGlow"] * np.exp(-dist / 0.012))[..., None] * mean_lin * exposure
                bcol = bcol + (C["edge_glow"] * 0.05 * np.exp(-dist / 0.05))[..., None] * mean_lin * exposure
            col = col * inG[..., None] + bcol * (1 - inG[..., None])
        out[y0:y1] = col
        if a_out is not None:
            a_out[y0:y1] = _sample(alpha, tmx, tmy, cv2.BORDER_REPLICATE) * inP

    if ss > 1:
        out = cv2.resize(out, (out_w, out_h), interpolation=cv2.INTER_AREA)
        if a_out is not None:
            a_out = cv2.resize(a_out, (out_w, out_h), interpolation=cv2.INTER_AREA)
    if camera and (CAM.get("bloom", 0) > 0 or CAM.get("glare", 0) > 0):
        out = lens_bloom(out, CAM)
    rgb = linear_to_srgb(out)
    if camera and grain_rng is not None and (CAM.get("grainLuma", 0) > 0 or CAM.get("grainChroma", 0) > 0):
        rgb = add_grain(rgb, CAM, grain_rng)
    rgb = np.clip(rgb, 0, 1).astype(np.float32)
    return rgb, a_out


def lens_bloom(lin: np.ndarray, CAM: dict) -> np.ndarray:
    """The filming camera's lens bloom and glare: a bright pass above a luminance knee, spread at six scales (bloom)
    and three very wide ones (glare). Scales follow the output width (the film: 1440 px)."""
    h, w = lin.shape[:2]
    k0, k1 = CAM.get("bloomKnee", [0.12, 0.5])
    hw, hh = max(1, w // 2), max(1, h // 2)
    half = cv2.resize(lin, (hw, hh), interpolation=cv2.INTER_AREA)
    l = luma(half)
    bright = half * smoothstep(k0, k1, l)[..., None]
    px = w / 1440.0  # output px per film px

    def lvl(level):
        return 0.5 * (2.0**level) * px / 2.0  # sigma in half-res px

    from .sigproc import big_blur

    b = sum(wt * big_blur(bright, lvl(L)) for wt, L in ((0.30, 1), (0.26, 2), (0.2, 3), (0.14, 4), (0.1, 5), (0.06, 6)))
    gl = sum(wt * big_blur(bright, lvl(L)) for wt, L in ((0.4, 6.5), (0.35, 7.5), (0.25, 8.5)))
    add = CAM.get("bloom", 0) * b + CAM.get("glare", 0) * gl
    return lin + cv2.resize(add, (w, h), interpolation=cv2.INTER_LINEAR)


def add_grain(rgb: np.ndarray, CAM: dict, rng) -> np.ndarray:
    """The film's camera-side grain: uniform per-frame noise on 8-bit luma (+/- grainLuma / 2 levels) and chroma
    (+/- grainChroma / 2), as ffmpeg's noise filter applied it (c0s=7, c1s=c2s=2, temporal, uniform)."""
    h, w = rgb.shape[:2]
    gy = CAM.get("grainLuma", 0) / 255.0
    gc = CAM.get("grainChroma", 0) / 255.0
    ny = (rng.random((h, w), dtype=np.float32) - 0.5) * gy
    ncb = (rng.random((h, w), dtype=np.float32) - 0.5) * gc
    ncr = (rng.random((h, w), dtype=np.float32) - 0.5) * gc
    d = np.stack([ny + 1.5748 * ncr, ny - 0.1873 * ncb - 0.4681 * ncr, ny + 1.8556 * ncb], -1)
    return rgb + d
