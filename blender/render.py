"""Render the camera shots of the Qingyun model.

    python blender/render.py --blend model/qingyun_airport.blend --shots all \
        --res 3840x2160 --samples 192 --out renders

Pipeline: Cycles path tracing (OIDN denoise) -> multilayer EXR (Combined + Mist)
-> numpy post: aerial-perspective haze from the mist pass, HDR bloom pyramid,
vignette -> AgX view transform via Blender colour management -> PNG + JPEG.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import addon_utils  # noqa: E402
import numpy as np  # noqa: E402


def read_exr(path):
    import OpenEXR
    ch = {}
    with OpenEXR.File(path, separate_channels=True) as f:
        for part in f.parts:
            for k, v in part.channels.items():
                ch[k] = v
    names = list(ch.keys())

    def get(suffix):
        for n in names:
            if n.endswith(suffix):
                return np.asarray(ch[n].pixels, dtype=np.float32)
        return None
    rgb = np.dstack([get('Combined.R'), get('Combined.G'), get('Combined.B')])
    mist = get('Mist.Z')
    if mist is None:
        mist = get('Mist.V')
    return rgb, mist


def _blur(img, sigma):
    from scipy.ndimage import gaussian_filter
    return np.dstack([gaussian_filter(img[..., c], sigma, mode='nearest') for c in range(img.shape[2])])


def bloom(rgb, threshold=1.6, strength=0.06):
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    k = np.clip((lum - threshold) / np.maximum(lum, 1e-4), 0, 1)[..., None]
    bright = np.minimum(rgb * k, 60.0)
    H, W = rgb.shape[:2]
    acc = np.zeros_like(rgb)
    total = 0.0
    for lvl, w in enumerate((1.0, 0.8, 0.6, 0.45, 0.35)):
        f = 2 ** (lvl + 1)
        h2, w2 = max(H // f, 4), max(W // f, 4)
        # box-downsample
        s = bright[:h2 * f, :w2 * f].reshape(h2, f, w2, f, 3).mean(axis=(1, 3))
        s = _blur(s, 2.0)
        from scipy.ndimage import zoom
        up = zoom(s, (H / h2, W / w2, 1), order=1)[:H, :W]
        if up.shape[0] < H or up.shape[1] < W:
            up = np.pad(up, ((0, H - up.shape[0]), (0, W - up.shape[1]), (0, 0)), mode='edge')
        acc += up * w
        total += w
    return rgb + acc / total * strength * 8.0


def post(rgb, mist, shot):
    H, W = rgb.shape[:2]
    out = rgb.copy()
    k = shot.get('haze_k', 0.0)
    if k > 0 and mist is not None:
        sky = mist >= 0.9995
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        if sky.sum() > 500:
            rows = np.where(sky.any(axis=1))[0]
            low = sky & (np.arange(H)[:, None] >= rows.max() - max(8, (rows.max() - rows.min()) // 6))
            Ls = float(np.percentile(lum[low if low.sum() > 100 else sky], 50))
        else:
            Ls = float(np.percentile(lum, 90))
        hc = np.asarray(shot.get('haze', (1, 1, 1)), np.float32)
        hc = hc / max(hc @ np.array([0.2126, 0.7152, 0.0722]), 1e-4) * Ls * 0.82
        # mist = distance / 60 km (linear); Koschmieder-style extinction, L = visibility scale
        Lv = shot.get('haze_L', 14000.0)
        f = (k * (1.0 - np.exp(-np.clip(mist, 0, 1) * 60000.0 / Lv)))[..., None]
        f = np.where(sky[..., None], 0.0, f)
        out = out * (1 - f) + hc * f
    out = bloom(out, threshold=shot.get('bloom_t', 1.6), strength=shot.get('bloom', 0.05))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / np.sqrt(2)
    out *= (1.0 - shot.get('vignette', 0.22) * r ** 2.4)[..., None]
    return out


def save_display(rgb, path_png, path_jpg, scene, quality=95):
    H, W = rgb.shape[:2]
    img = bpy.data.images.new('post', W, H, alpha=False, float_buffer=True)
    rgba = np.dstack([rgb, np.ones((H, W, 1), np.float32)])
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1], dtype=np.float32).reshape(-1))  # EXR rows top-first
    st = scene.render.image_settings
    st.media_type = 'IMAGE'
    st.file_format = 'PNG'
    st.color_mode = 'RGB'
    st.color_depth = '8'
    img.save_render(path_png, scene=scene)
    bpy.data.images.remove(img)
    if path_jpg:
        from PIL import Image
        Image.open(path_png).convert('RGB').save(path_jpg, quality=quality, subsampling=0, optimize=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', default=os.path.join(HERE, '..', 'model', 'qingyun_airport.blend'))
    ap.add_argument('--shots', default='all')
    ap.add_argument('--res', default='3840x2160')
    ap.add_argument('--samples', type=int, default=192)
    ap.add_argument('--threshold', type=float, default=0.015)
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'renders'))
    ap.add_argument('--tmp', default=None)
    ap.add_argument('--raw', action='store_true', help='skip post, save direct PNG')
    ap.add_argument('--jpg', action='store_true')
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(args.blend))
    addon_utils.enable('cycles', default_set=True)
    from qy import cameras, world
    sc = bpy.context.scene
    W, H = (int(v) for v in args.res.split('x'))
    world.render_settings(samples=args.samples, res=(W, H), threshold=args.threshold)
    print('[colour]', sc.view_settings.view_transform, '|', sc.view_settings.look, flush=True)
    if args.shots == 'all':
        shots = [k for k, v in cameras.SHOTS.items() if not v.get('pano')]
    elif args.shots == 'panos':
        shots = list(cameras.PANOS)
    else:
        shots = args.shots.split(',')
    os.makedirs(args.out, exist_ok=True)
    tmp = args.tmp or args.out
    for name in shots:
        t0 = time.time()
        shot = cameras.apply_shot(name)
        if 'samples' in shot:
            sc.cycles.samples = shot['samples']
        if args.raw:
            sc.render.image_settings.media_type = 'IMAGE'
            sc.render.image_settings.file_format = 'PNG'
            sc.render.image_settings.color_depth = '8'
            sc.render.filepath = os.path.join(args.out, name + '.png')
            bpy.ops.render.render(write_still=True)
        else:
            exr = os.path.join(tmp, name + '.exr')
            st = sc.render.image_settings
            st.media_type = 'MULTI_LAYER_IMAGE'
            st.file_format = 'OPEN_EXR_MULTILAYER'
            st.color_depth = '32'
            st.exr_codec = 'ZIP'
            sc.render.filepath = exr
            bpy.ops.render.render(write_still=True)
            rgb, mist = read_exr(exr)
            out = post(rgb, mist, shot)
            png = os.path.join(args.out, name + '.png')
            jpg = os.path.join(args.out, name + '.jpg') if args.jpg else None
            save_display(out, png, jpg, sc)
        print(f'[render] {name} {W}x{H} {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    main(argv)
