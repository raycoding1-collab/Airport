"""Build the complete Qingyun Shanshui International Airport scene.

    python blender/build.py [--out model/qingyun_airport.blend]

Requires the `bpy` module (pip install bpy==5.2.*) or run inside Blender:
    blender --background --python blender/build.py -- --out ...
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402  (must be imported before addon_utils)
import addon_utils  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'model', 'qingyun_airport.blend'))
    ap.add_argument('--no-forest', action='store_true')
    args = ap.parse_args(argv)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable('cycles', default_set=True)
    from qy import (airfield, cameras, landscape, materials, params as P, piers, planting, terminal, world)
    import math

    t0 = time.time()
    root = bpy.context.scene.collection
    M = materials.build_library()
    world.build_world()
    world.render_settings()
    log = lambda s: print(f'[{time.time() - t0:7.1f}s] {s}', flush=True)
    hub = terminal.build(M, root)
    log('hub')
    airfield.build(M, root)
    log('airfield')
    piers.build(M, root)
    log('piers + aircraft')
    land = landscape.build(M, root)
    log('landscape')
    y_hub = -float(P.r_facade(-math.pi / 2))
    if args.no_forest:
        planting.forests = lambda rs: (__import__('numpy').zeros((0, 3)), [], [])
    counts = planting.build(root, hub, land, y_hub)
    log(f'planting {counts}')
    cameras.build_cameras()
    log('cameras')
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    log(f'saved {out}')


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    main(argv)
