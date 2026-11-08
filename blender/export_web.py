"""Export a web-ready version of the model for the three.js viewer.

    python blender/export_web.py --blend model/qingyun_airport.blend --out web/assets

Writes:
  qingyun.glb      geometry (meshopt-compressed via glTF-Transform), material names preserved
  trees.json       tree/shrub instances  {variant: [[x,y,z,rotY,scale], ...]}  (three.js Y-up)
  lights.json      night point lights    {group: [[x,y,z], ...]}
  leaf_*.png       procedural leaf atlases; apron_mask.png
The forest belt, distant mountains and 70 km ground are omitted (the viewer
synthesises sky, ground and haze itself).
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
import numpy as np  # noqa: E402


def to_three(p):
    return [round(float(p[0]), 2), round(float(p[2]), 2), round(float(-p[1]), 2)]


def bake_livery(ob, L, R, zc):
    """Vertex colours reproducing the procedural livery (jade sweep, belly)."""
    me = ob.data
    if 'Col' in me.color_attributes:
        return
    ca = me.color_attributes.new('Col', 'FLOAT_COLOR', 'POINT')
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    xn = -co[:, 0] / L
    z = co[:, 2] - zc
    sweep = xn + z / (L * 0.9)
    col = np.tile(np.array([0.86, 0.87, 0.88, 1.0], np.float32), (len(co), 1))
    col[z < -R * 0.55] = (0.62, 0.64, 0.66, 1.0)
    col[sweep > 0.86] = (0.0, 0.30, 0.25, 1.0)
    col[np.abs(sweep - 0.845) < 0.006] = (0.85, 0.62, 0.25, 1.0)
    ca.data.foreach_set('color', col.reshape(-1))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', default=os.path.join(HERE, '..', 'model', 'qingyun_airport.blend'))
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'web', 'assets'))
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
    from qy import aircraft

    sc = bpy.context.scene
    O = bpy.data.objects

    # ---- instance tables -----------------------------------------------------
    lib = bpy.data.collections['LIB_trees']
    names = sorted(o.name for o in lib.objects)
    trees = {n: [] for n in names}
    for ob in list(O):
        if not ob.name.startswith('Trees_') or ob.name == 'Trees_Forest':
            continue
        me = ob.data
        n = len(me.vertices)
        co = np.zeros(n * 3, np.float32)
        me.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        vid = np.zeros(n, np.int32)
        me.attributes['vid'].data.foreach_get('value', vid)
        rot = np.zeros(n * 3, np.float32)
        me.attributes['rot'].data.foreach_get('vector', rot)
        scl = np.zeros(n * 3, np.float32)
        me.attributes['scl'].data.foreach_get('vector', scl)
        rot = rot.reshape(-1, 3)
        scl = scl.reshape(-1, 3)
        for i in range(n):
            trees[names[vid[i]]].append(to_three(co[i]) + [round(float(rot[i, 2]), 3), round(float(scl[i, 0]), 3)])
    with open(os.path.join(out, 'trees.json'), 'w') as f:
        json.dump(trees, f, separators=(',', ':'))

    lights = {}
    for ob in O:
        if ob.name.startswith('Lights_'):
            co = np.zeros(len(ob.data.vertices) * 3, np.float32)
            ob.data.vertices.foreach_get('co', co)
            lights[ob.name[7:]] = [to_three(p) for p in co.reshape(-1, 3)]
    with open(os.path.join(out, 'lights.json'), 'w') as f:
        json.dump(lights, f, separators=(',', ':'))

    # ---- textures --------------------------------------------------------------
    for im in bpy.data.images:
        if im.name.startswith('leaf_') or im.name == 'apron_mask':
            im.filepath_raw = os.path.join(out, im.name + '.png')
            im.file_format = 'PNG'
            if im.name == 'apron_mask':
                # downsample for the web
                im.scale(2048, 2048)
            im.save()

    # ---- prune heavy / non-web objects -----------------------------------------
    drop_prefix = ('Trees_', 'Lights_', 'CAM_', 'Mountains', 'Ground_Far', 'Vortex_Mist', 'Sun',
                   'Street_')
    for ob in list(O):
        if ob.name.startswith(drop_prefix) or ob.type in ('LIGHT', 'CAMERA'):
            bpy.data.objects.remove(ob, do_unlink=True)
    for cn in ('Night_Hub', 'Night_Piers', 'Night_Airfield', 'Night_Street'):
        c = bpy.data.collections.get(cn)
        if c:
            for ob in list(c.objects):
                bpy.data.objects.remove(ob, do_unlink=True)

    # tree variants into the scene (viewer hides them and instances them)
    tl = bpy.data.collections.new('TREE_LIBRARY')
    sc.collection.children.link(tl)
    for o in lib.objects:
        tl.objects.link(o)

    # aircraft livery -> vertex colours
    for kind in ('wide', 'narrow'):
        L, R, span, zc = aircraft.TYPES[kind][:4]
        for ob in O:
            if ob.type == 'MESH' and ob.data.name == 'AC_' + kind:
                bake_livery(ob, L, R, zc)
                break

    glb = os.path.join(out, 'qingyun.glb')
    kw = dict(filepath=glb, export_format='GLB', export_apply=True, export_yup=True,
              export_cameras=False, export_lights=False, export_extras=False,
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
              export_draco_position_quantization=16, export_draco_normal_quantization=10,
              export_draco_texcoord_quantization=12, export_vertex_color='ACTIVE',
              export_image_format='NONE')
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError as e:
        print('retrying without optional args:', e)
        for k in ('export_vertex_color', 'export_image_format'):
            kw.pop(k, None)
        bpy.ops.export_scene.gltf(**kw)
    print('wrote', glb, os.path.getsize(glb) / 1e6, 'MB')
    # Blender's pip wheel ships without Draco, so compress with glTF-Transform (meshopt)
    import shutil
    import subprocess
    cli = os.environ.get('GLTF_TRANSFORM') or shutil.which('gltf-transform')
    cmd = [cli] if cli else (['npx', '--yes', '@gltf-transform/cli'] if shutil.which('npx') else None)
    if cmd:
        tmp = glb + '.tmp.glb'
        r = subprocess.run(cmd + ['meshopt', glb, tmp, '--level', 'medium'])
        if r.returncode == 0 and os.path.exists(tmp):
            os.replace(tmp, glb)
            print('meshopt-compressed ->', os.path.getsize(glb) / 1e6, 'MB')
    else:
        print('glTF-Transform not found: GLB left uncompressed (viewer still loads it)')
    print('trees', sum(len(v) for v in trees.values()), 'lights', sum(len(v) for v in lights.values()))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    main(argv)
