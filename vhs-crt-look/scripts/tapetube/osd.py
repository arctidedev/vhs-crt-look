"""The camcorder's on-screen-display lettering and the burned-in date stamp.

GLYPHS is the film's 5x7 OSD drawing (squared C and O, single-cell strokes): the 1987 date stamp's digits and
letters, completed to A-Z, the VCR's play arrow and divider, plus a few punctuation marks for labels.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

GLYPHS = {
    "0": ["#####", "#...#", "#..##", "#.#.#", "##..#", "#...#", "#####"],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": ["#####", "....#", "....#", "#####", "#....", "#....", "#####"],
    "3": ["#####", "....#", "....#", ".####", "....#", "....#", "#####"],
    "4": ["#...#", "#...#", "#...#", "#####", "....#", "....#", "....#"],
    "5": ["#####", "#....", "#....", "#####", "....#", "....#", "#####"],
    "6": ["#####", "#....", "#....", "#####", "#...#", "#...#", "#####"],
    "7": ["#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."],
    "8": ["#####", "#...#", "#...#", "#####", "#...#", "#...#", "#####"],
    "9": ["#####", "#...#", "#...#", "#####", "....#", "....#", "#####"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": ["#####", "#....", "#....", "#....", "#....", "#....", "#####"],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": ["#####", "#....", "#....", "#.###", "#...#", "#...#", "#####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "J": ["....#", "....#", "....#", "....#", "#...#", "#...#", "#####"],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": ["#####", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": ["#####", "#...#", "#...#", "#...#", "#.#.#", "#..#.", "##.##"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": ["#####", "#....", "#....", "#####", "....#", "....#", "#####"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    ":": [".....", "..#..", ".....", ".....", ".....", "..#..", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    "|": ["..#..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    ">": ["#....", "##...", "###..", "####.", "###..", "##...", "#...."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    # label punctuation, same squared drawing
    ",": [".....", ".....", ".....", ".....", ".....", "..#..", ".#..."],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "(": ["...#.", "..#..", "..#..", "..#..", "..#..", "..#..", "...#."],
    ")": [".#...", "..#..", "..#..", "..#..", "..#..", "..#..", ".#..."],
    "%": ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
    "'": ["..#..", "..#..", ".....", ".....", ".....", ".....", "....."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    "?": ["#####", "....#", "....#", "..###", "..#..", ".....", "..#.."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    "&": [".##..", "#..#.", ".##..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    "#": [".#.#.", "#####", ".#.#.", ".#.#.", ".#.#.", "#####", ".#.#."],
    "x": [".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
}

# The film's stamp placement (comp/look.json tape block): margins from the right and bottom edges, given on a
# 640x480 frame and scaled with the picture height.
DATE_MARGIN_RIGHT = 84
DATE_MARGIN_BOTTOM = 70
DEFAULT_DATE = "OCT 26 1987"
INK = np.array([0.97, 0.97, 0.95], np.float32)


def glyph(ch: str):
    g = GLYPHS.get(ch)
    if g is None:
        g = GLYPHS.get(ch.upper(), GLYPHS[" "])
    return g


def text_width(text: str, cw: float) -> float:
    return (6 * len(text) - 1) * cw


def text_mask(
    shape: Tuple[int, int], text: str, x0: float, y0: float, cw: float, ch: Optional[float] = None
) -> np.ndarray:
    """Hard 0/1 mask of the glyph cells (cw x ch pixels per cell)."""
    ch = cw if ch is None else ch
    m = np.zeros(shape, np.float32)
    cx = x0
    for c in text:
        for r, row in enumerate(glyph(c)):
            for k, b in enumerate(row):
                if b == "#":
                    ya, yb = int(round(y0 + r * ch)), int(round(y0 + (r + 1) * ch))
                    xa, xb = int(round(cx + k * cw)), int(round(cx + (k + 1) * cw))
                    m[max(ya, 0) : max(yb, 0), max(xa, 0) : max(xb, 0)] = 1
        cx += 6 * cw
    return m


def stamp_layout(cw_px: int, ch_px: int, text: str, pos: str = "br", cell: Optional[int] = None):
    """Cell size and top-left corner of the date stamp on a cw_px x ch_px camcorder raster.

    The film placed the stamp 84 px from the right and 70 px from the bottom of a 640x480 frame with 6 px cells on
    the 960x720 raster. Both scale with the picture height; on narrow (portrait) rasters the cell shrinks until the
    text fits between equal side margins."""
    s = ch_px / 480.0
    cell = cell or max(1, int(round(6 * ch_px / 720.0)))
    mr, mb = DATE_MARGIN_RIGHT * s, DATE_MARGIN_BOTTOM * s
    while cell > 1 and text_width(text, cell) + 2 * mr > cw_px:
        cell -= 1
    if text_width(text, cell) + 2 * mr > cw_px:
        mr = max(float(cell), (cw_px - text_width(text, cell)) / 2)
    if pos[1] == "r":
        x0 = cw_px - mr + cell - len(text) * 6 * cell
    else:
        x0 = mr
    if pos[0] == "b":
        y0 = ch_px - mb - 7 * cell
    else:
        y0 = mb
    return cell, int(round(x0)), int(round(y0))


def draw_date(img: np.ndarray, text: str, pos: str = "br", cell: Optional[int] = None) -> np.ndarray:
    """The camcorder's burned-in stamp as the film drew it (comp/prep_tape.py): white blocky glyphs, a one-cell dark
    edge, and the character generator's own edge softness (0.9 px Gaussian on the 960x720 raster)."""
    h, w = img.shape[:2]
    cell, x0, y0 = stamp_layout(w, h, text, pos, cell)
    mask = text_mask((h, w), text, x0, y0, cell)
    edge = cv2.dilate(mask, np.ones((3, 3), np.uint8)) - mask
    soft = 0.9 * h / 720.0
    mask, edge = cv2.GaussianBlur(mask, (0, 0), soft), cv2.GaussianBlur(edge, (0, 0), soft)
    img = img * (1 - 0.6 * edge[..., None])
    return img * (1 - mask[..., None]) + mask[..., None] * INK


def draw_lines(
    img: np.ndarray, lines: Sequence[Tuple[str, float, float, float]], ink=None, edge_k: float = 0.7, soft: float = 0.8
):
    """Labels in the OSD lettering: lines = [(text, x0, y0, cell)], white glyphs with a dark one-cell edge."""
    h, w = img.shape[:2]
    m = np.zeros((h, w), np.float32)
    for text, x0, y0, cw in lines:
        m = np.maximum(m, text_mask((h, w), text.upper(), x0, y0, cw))
    edge = np.clip(cv2.dilate(m, np.ones((3, 3), np.uint8)) - m, 0, 1)
    if soft > 0:
        m, edge = cv2.GaussianBlur(m, (0, 0), soft), cv2.GaussianBlur(edge, (0, 0), soft)
    ink = INK if ink is None else np.asarray(ink, np.float32)
    img = img * (1 - edge_k * edge[..., None])
    return img * (1 - m[..., None]) + m[..., None] * ink


def wrap(text: str, max_chars: int) -> List[str]:
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    return out
