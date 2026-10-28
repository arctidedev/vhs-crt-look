import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest
from tapetube import crt, media, osd, page, pipeline, presets, sigproc, vhs

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vhs-crt-look", "scripts")


def ref_gauss1d(a, sigma, axis):
    """Direct reference for scipy.ndimage.gaussian_filter1d (mode reflect, truncate 4)."""
    r = int(4.0 * sigma + 0.5)
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * x * x / sigma**2)
    k /= k.sum()
    a = np.moveaxis(np.asarray(a, np.float64), axis, -1)
    pad = [(0, 0)] * (a.ndim - 1) + [(r, r)]
    p = np.pad(a, pad, mode="symmetric")
    out = np.zeros_like(a)
    for i, w in enumerate(k):
        out += w * p[..., i : i + a.shape[-1]]
    return np.moveaxis(out, -1, axis)


@pytest.mark.parametrize("sigma", [0.6, 1.1, 2.6, 7.3])
@pytest.mark.parametrize("shape,axis", [((37,), 0), ((20, 33), 1), ((20, 33), 0), ((12, 17, 3), 1), ((12, 17, 2), 0)])
def test_gauss1d_matches_reference(sigma, shape, axis):
    rng = np.random.default_rng(1)
    a = rng.normal(size=shape).astype(np.float32)
    got = sigproc.gauss1d(a, sigma, axis)
    want = ref_gauss1d(a, sigma, axis)
    assert np.abs(got - want).max() < 2e-5


def test_gauss1d_matches_scipy_when_available():
    nd = pytest.importorskip("scipy.ndimage")
    a = np.random.default_rng(2).normal(size=(40, 64, 3)).astype(np.float32)
    assert np.abs(sigproc.gauss1d(a, 2.3, axis=1) - nd.gaussian_filter1d(a, 2.3, axis=1)).max() < 1e-5
    assert np.abs(sigproc.gauss2d(a, 0.8, 3.1) - nd.gaussian_filter(a, (0.8, 3.1, 0))).max() < 1e-5


def test_tvl_sigma_matches_reference():
    # looktest: f = tvl * 4/3 / 2 / 960 cycles per sample, sigma = 0.3416 / f
    assert math.isclose(vhs.tvl_sigma(240), 0.3416 / (240 * 4 / 3 / 2 / 960), rel_tol=1e-9)
    assert vhs.tvl_sigma(0) == 0.0


def test_reference_constants():
    d = presets.load()
    v2 = presets._merge(d["base_vhs"], d["vhs"]["V2"])
    assert v2["luma_tvl"] == [240, 225] and v2["chroma_tvl"] == [36, 32] and v2["gens"] == 2
    assert v2["black_lift"] == 0.065 and v2["osd"] == "OCT 26 1987"
    c2 = presets._merge(d["base_crt"], d["crt"]["C2"])
    assert c2["mask"] == "slot" and c2["triads_across"] == 640 and c2["overscan"] == 1.07
    t6 = d["treatments"]["T6"]
    assert t6["tube"]["fieldOnly"] == 1 and t6["crt"]["beam_max"] == 0.3
    assert d["looks"]["vhs-on-tv"] == {
        **d["looks"]["vhs-on-tv"],
        "tape": "V2",
        "tube": "C2",
        "treatment": "T6",
        "capture": "filmed",
    }


@pytest.mark.parametrize("look", list(presets.load()["looks"]))
def test_every_look_builds(look):
    cfg = presets.build(look=look)
    assert cfg["capture"] in presets.CAPTURES
    assert presets.describe(cfg)


def test_build_errors():
    with pytest.raises(ValueError):
        presets.build(look="nope")
    with pytest.raises(ValueError):
        presets.build(off=["warp-drive"])
    with pytest.raises(ValueError):
        presets.build(strengths={"sparkle": 1})
    with pytest.raises(ValueError, match="section"):
        presets.build(sets=[("bloom_amt", "0.1")])  # in both vhs and crt


def test_knobs_scale_parameters():
    base = presets.build(look="church-dub")
    quiet = presets.build(look="church-dub", strengths={"noise": 0, "dropouts": 0, "wobble": 0})
    assert (
        quiet["vhs"]["luma_noise"] == [0, 0] and quiet["vhs"]["dropouts"] == [0, 0] and quiet["vhs"]["jitter"] == [0, 0]
    )
    soft = presets.build(look="church-dub", strengths={"softness": 2})
    assert soft["vhs"]["luma_tvl"] == [x / 2 for x in base["vhs"]["luma_tvl"]]
    sharp = presets.build(look="church-dub", strengths={"softness": 0})
    assert sharp["vhs"]["luma_tvl"] == [0, 0] and vhs.tvl_sigma(0) == 0
    fade = presets.build(look="church-dub", strengths={"fade": 0})
    assert fade["vhs"]["chroma_sat"] == [1.0, 1.0] and fade["vhs"]["black_lift"] == 0
    flat = presets.build(look="consumer-tv", strengths={"scanlines": 0})
    assert flat["stages"]["beams"] is False


def test_raw_sets_and_parsing():
    kv = presets.parse_kv(["vhs.luma_tvl=[200,180],crt.triads_across=420", "date=JUL 4 1989"])
    assert kv == [("vhs.luma_tvl", "[200,180]"), ("crt.triads_across", "420"), ("date", "JUL 4 1989")]
    cfg = presets.build(look="church-dub", sets=kv[:2])
    assert cfg["vhs"]["luma_tvl"] == [200, 180] and cfg["crt"]["triads_across"] == 420


@pytest.mark.parametrize("w", [96, 180, 405, 540, 960, 1280])
def test_date_stamp_fits(w):
    cell, x0, y0 = osd.stamp_layout(w, 720, "OCT 26 1987")
    assert x0 >= 0 and x0 + osd.text_width("OCT 26 1987", cell) <= w
    assert y0 >= 0 and y0 + 7 * cell <= 720


def test_reference_stamp_placement():
    # reference placement: x0 = round(960 - 84 * 1.5 + 6 - 11 * 36), y0 = round(720 - 70 * 1.5 - 42)
    assert osd.stamp_layout(960, 720, "OCT 26 1987") == (6, 444, 573)


def frames(w, h, n=4, seed=0):
    rng = np.random.default_rng(seed)
    base = np.clip(
        rng.random((h, w, 3)).astype(np.float32) * 0.2 + np.linspace(0, 0.8, w, dtype=np.float32)[None, :, None], 0, 1
    )
    return [base] * n


def test_vhs_signal_shape_and_determinism():
    P = presets.build(look="church-dub")["vhs"]
    h = frames(960, 720)
    a = vhs.vhs_signal(h, P, 5, 24.0)
    b = vhs.vhs_signal(h, P, 5, 24.0)
    c = vhs.vhs_signal(h, P, 6, 24.0)
    d = vhs.vhs_signal(h, P, 5, 24.0, seed=3)
    assert a.shape == (480, 960, 3) and a.dtype == np.float32
    assert np.array_equal(a, b) and not np.array_equal(a, c) and not np.array_equal(a, d)
    assert a.min() >= P["black_lift"] - 1e-6 and a.max() <= P["white"] + 1e-6


def test_vhs_portrait_raster():
    P = presets.build(look="worn-tape")["vhs"]
    cw = vhs.raster_width(9 / 16)
    sig = vhs.vhs_signal(frames(cw, 720), P, 0, 30.0)
    assert sig.shape == (480, cw, 3) and np.isfinite(sig).all()


def test_stages_snapshots():
    P = presets.build(look="church-dub")["vhs"]
    snaps = {}
    vhs.vhs_signal(frames(960, 720), P, 2, 24.0, snaps=snaps)
    assert set(snaps) == {"S1", "S2", "S3", "S4", "S5"}


@pytest.mark.parametrize("kind", ["slot", "grille", "dot"])
def test_mask_mean_is_one(kind):
    C = presets.build(look="consumer-tv", mask=kind)["crt"]
    yy, xx = np.mgrid[0:200, 0:200].astype(np.float32)
    M = crt.phosphor_mask(xx / 200 - 0.5, yy / 200 - 0.5, C, triads=40, per_px=0.2, aspect=1.0, roll=0.45)
    assert abs(float(M.mean()) - 1.0) < 0.03 and M.std() > 0.05


@pytest.mark.parametrize("size", [(333, 601), (640, 480), (1000, 300), (65, 49)])
def test_tube_render_sizes(size):
    cfg = presets.build(look="vhs-on-tv")
    w, h = size
    cw = vhs.raster_width(w / h)
    sig = vhs.vhs_signal(frames(cw, 720), cfg["vhs"], 0, 24.0)
    alpha = np.ones(sig.shape[:2], np.float32)
    rgb, a = crt.render(
        sig, cfg["crt"], cfg["tube"], cfg["camera"], w, h, alpha=alpha, grain_rng=np.random.default_rng(0)
    )
    assert a is not None
    assert rgb.shape == (h, w, 3) and a.shape == (h, w)
    assert np.isfinite(rgb).all() and rgb.min() >= 0 and rgb.max() <= 1


def test_frame_modes():
    img = np.zeros((601, 333, 3), np.float32)
    c = pipeline.frame_transform(img, "crop43")
    p = pipeline.frame_transform(img, "pad43")
    assert abs(c.shape[1] / c.shape[0] - 4 / 3) < 0.01 and abs(p.shape[1] / p.shape[0] - 4 / 3) < 0.01
    assert pipeline.output_size(1080, 1920, "native", height=640, even=True) == (360, 640)


def test_image_roundtrip_alpha_and_16bit(tmp_path):
    rgb = np.random.default_rng(0).random((48, 64, 3)).astype(np.float32)
    a = np.linspace(0, 1, 64, dtype=np.float32)[None].repeat(48, 0)
    media.write_image(str(tmp_path / "x.png"), rgb, a, bits=16)
    r, al, bits = media.read_image(str(tmp_path / "x.png"))
    assert bits == 16 and al is not None and np.abs(r - rgb).max() < 1e-4


def test_page_is_offline(tmp_path):
    src = tmp_path / "in.png"
    media.write_image(str(src), np.random.default_rng(0).random((120, 160, 3)).astype(np.float32))
    res = page.preview_all(
        str(src),
        str(tmp_path / "pv"),
        presets.build(look="consumer-tv"),
        looks=["church-dub", "consumer-tv"],
        clip=False,
        jobs=1,
    )
    html = open(res["page"], encoding="utf-8").read()
    assert "http://" not in html and "https://" not in html and "<script src" not in html
    payload = json.loads(html.split('<script id="payload" type="application/json">')[1].split("</script>")[0])
    assert {x["id"] for x in payload["looks"]} == {"church-dub", "consumer-tv"}
    assert any(s["id"] == "L2" for s in payload["stages"])


def test_cli_help_and_params():
    out = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "vhslook.py"), "params", "--look", "worn-tape", "-s", "noise=0.5"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    cfg = json.loads(out.stdout)
    assert cfg["tape"] == "V4" and cfg["strengths"] == {"noise": 0.5}


@pytest.mark.skipif(not os.environ.get("VHSLOOK_SLOW"), reason="set VHSLOOK_SLOW=1 to run the full self-test")
def test_selftest_quick(tmp_path):
    from tapetube import selftest

    assert selftest.run(str(tmp_path / "st"), quick=True)


def test_ffbin_env_override_and_install_hint(tmp_path, monkeypatch):
    from tapetube import ffbin

    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_text("")
    monkeypatch.setenv("VHSLOOK_FFMPEG", str(fake))
    assert ffbin.find("ffmpeg") == str(fake)
    cmd = ffbin.install_command()
    assert cmd is None or (isinstance(cmd, list) and "ffmpeg" in " ".join(cmd).lower())
    assert "ffmpeg" in ffbin.manual_hint().lower()


def test_setup_ffmpeg_step_decisions(monkeypatch, capsys):
    import setup_env

    monkeypatch.setattr(setup_env.ffbin, "find", lambda name: None)
    assert setup_env.ffmpeg_step(yes=False, skip=True) is True  # stills only
    monkeypatch.setattr(setup_env.ffbin, "install_command", lambda: None)
    assert setup_env.ffmpeg_step(yes=True, skip=False) is False  # nothing to install with: manual hint
    monkeypatch.setattr(setup_env.ffbin, "install_command", lambda: [sys.executable, "-c", "pass"])
    assert setup_env.ffmpeg_step(yes=False, skip=False) is False  # not interactive and no --yes: never installs
    assert "Not installed" in capsys.readouterr().out
    assert setup_env.ffmpeg_step(yes=True, skip=False) is False  # ran the installer, ffmpeg still not visible


def test_cli_without_packages_points_to_setup(tmp_path):
    """A python without numpy and OpenCV gets one clear instruction instead of a traceback."""
    skill = os.path.dirname(SCRIPTS)
    out = subprocess.run(
        [sys.executable, "-I", "-S", os.path.join(SCRIPTS, "vhslook.py"), "doctor"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", ""), "VHSLOOK_NO_VENV": "1"},
        cwd=skill,
    )
    assert out.returncode != 0 and "setup" in (out.stdout + out.stderr)
