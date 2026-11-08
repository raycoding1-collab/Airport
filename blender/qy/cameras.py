"""Camera shots + per-shot lighting presets."""

import bpy
from mathutils import Vector

from . import materials, world

NIGHT_COLLS = ['Night_Hub', 'Night_Piers', 'Night_Airfield', 'Night_Street']

GOLDEN = dict(az=256.0, el=7.5, sun_color=(1.0, 0.60, 0.33), sun=7.5, sky=0.05, clouds=0.95,
              cloud_lit=(18.0, 10.0, 5.5), cloud_shade=(2.6, 2.6, 3.3), cloud_cover=(0.46, 0.70), mode='day',
              aerosol=2.2)

SHOTS = {
    '01_aerial_golden_hour': dict(loc=(-560.0, -1780.0, 400.0), tgt=(40.0, 260.0, 0.0), lens=30.0,
                                  light=GOLDEN, haze=(0.80, 0.80, 0.90), haze_k=0.9),
    '02_blue_hour': dict(loc=(1750.0, 1450.0, 640.0), tgt=(-40.0, -160.0, 0.0), lens=30.0,
                         light=dict(az=252.0, el=-3.5, sun_color=(1, 0.5, 0.3), sun=0.0, sky=1.6, clouds=0.55,
                                    cloud_lit=(2.4, 1.2, 0.9), cloud_shade=(0.5, 0.55, 0.8),
                                    cloud_cover=(0.52, 0.8), mode='night', aerosol=1.5),
                         haze=(0.25, 0.3, 0.5), haze_k=0.35),
    '03_gorge_gateway': dict(loc=(0.0, -610.0, 6.5), tgt=(0.0, -282.0, 15.0), lens=27.0,
                             light=dict(GOLDEN, az=262.0, el=11.0, sun=5.5), haze=(1.0, 0.75, 0.55), haze_k=0.25),
    '04_sky_well_interior': dict(loc=(-15.75, -58.6, 13.7), tgt=(0.0, 0.0, 1.5), lens=13.0, exposure=0.35,
                                 light=dict(az=212.0, el=40.0, sun_color=(1.0, 0.86, 0.70), sun=6.0, sky=0.06,
                                            clouds=0.5, cloud_lit=(13.0, 11.0, 9.0), cloud_shade=(4, 4.4, 5.2),
                                            cloud_cover=(0.55, 0.8), mode='day', aerosol=1.2),
                                 haze=(1, 1, 1), haze_k=0.0),
    '05_pier_apron': dict(loc=(-128.0, 338.0, 17.0), tgt=(-30.0, 430.0, 8.0), lens=26.0,
                          light=dict(GOLDEN, az=258.0, el=9.0, sun=6.0), haze=(1.0, 0.74, 0.55), haze_k=0.35),
    '06_masterplan': dict(loc=(0.0, -280.0, 6000.0), tgt=(0.0, -280.0, 0.0), ortho=5900.0,
                          light=dict(az=215.0, el=38.0, sun_color=(1.0, 0.9, 0.78), sun=6.0, sky=0.06, clouds=0.0,
                                     cloud_lit=(1, 1, 1), cloud_shade=(1, 1, 1), cloud_cover=(0.5, 0.7),
                                     mode='day', aerosol=1.2),
                          haze=(1, 1, 1), haze_k=0.0),
    '07_oculus_vortex': dict(loc=(-110.0, -165.0, 150.0), tgt=(0.0, 0.0, 12.0), lens=27.0,
                             light=dict(az=236.0, el=22.0, sun_color=(1.0, 0.78, 0.55), sun=6.0, sky=0.06,
                                        clouds=0.7, cloud_lit=(15, 11, 8), cloud_shade=(3, 3.3, 4),
                                        cloud_cover=(0.52, 0.78), mode='day', aerosol=1.6),
                             haze=(1.0, 0.8, 0.65), haze_k=0.2),
}


def build_cameras():
    sc = bpy.context.scene
    for name, s in SHOTS.items():
        cd = bpy.data.cameras.new('CAM_' + name)
        ob = bpy.data.objects.new('CAM_' + name, cd)
        sc.collection.objects.link(ob)
        _pose(ob, s)
    sc.camera = bpy.data.objects['CAM_01_aerial_golden_hour']


def _pose(ob, s):
    cd = ob.data
    ob.location = s['loc']
    d = Vector(s['tgt']) - Vector(s['loc'])
    if d.length < 1e-6:
        d = Vector((0, 0, -1))
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cd.sensor_width = 36.0
    cd.clip_start = 0.5
    cd.clip_end = 40000.0
    if 'ortho' in s:
        cd.type = 'ORTHO'
        cd.ortho_scale = s['ortho']
        ob.rotation_euler = (0, 0, 0)
    else:
        cd.type = 'PERSP'
        cd.lens = s['lens']
    if 'shift' in s:
        cd.shift_x, cd.shift_y = s['shift']


def apply_shot(name):
    s = SHOTS[name]
    sc = bpy.context.scene
    ob = bpy.data.objects['CAM_' + name]
    _pose(ob, s)
    sc.camera = ob
    L = s['light']
    world.set_sky(L['az'], L['el'], L['sun_color'], L['sun'], sky_strength=L['sky'], clouds=L['clouds'],
                  cloud_lit=L['cloud_lit'], cloud_shade=L['cloud_shade'], cloud_cover=L['cloud_cover'],
                  aerosol=L.get('aerosol', 1.6))
    night = L['mode'] == 'night'
    materials.set_lighting_mode('night' if night else 'day')
    sc.view_settings.exposure = s.get('exposure', 0.0)
    for cn in NIGHT_COLLS:
        c = bpy.data.collections.get(cn)
        if c is not None:
            c.hide_render = not night
    return s
