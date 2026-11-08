"""Physical sky, sun, procedural cloud deck and render settings."""
import math

import bpy

from .materials import G


def sun_vector(az_deg, el_deg):
    """Direction TOWARDS the sun. Azimuth: 0 = north (+Y), 90 = east (+X)."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return (math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el))


def build_world():
    w = bpy.data.worlds.get('Sky') or bpy.data.worlds.new('Sky')
    if w.node_tree is None:
        w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)

    class _W:  # reuse the G helpers on a world tree
        pass
    g = G.__new__(G)
    g.mat = w
    g.nt = nt
    g._tc = None

    sky = g.node('ShaderNodeTexSky', sky_type='MULTIPLE_SCATTERING')
    sky.name = 'SKY'
    sky.sun_disc = True
    sky.sun_size = math.radians(0.545)
    sky.sun_intensity = 0.0          # the visible disc comes from the sun lamp
    sky.altitude = 150.0
    sky.air_density = 1.0
    sky.aerosol_density = 1.6
    sky.ozone_density = 1.0

    # --- cloud deck: planar projection of the view direction ----------------
    d = g.tc.outputs['Generated']
    dx, dy, dz = g.sep(d)
    dzc = g.m('MAXIMUM', dz, 0.035)
    px = g.m('DIVIDE', dx, dzc)
    py = g.m('DIVIDE', dy, dzc)
    p = g.comb(px, py, 0.0)
    warp = g.noise(p, 0.35, 3)
    p2 = g.vm('ADD', p, g.vm('SCALE', warp.outputs['Color'], scale=0.6))
    c1 = g.noise(g.vm('MULTIPLY', p2, (1.0, 1.8, 1.0)), 1.1, 9, 0.62)
    c1.name = 'CLOUD_NOISE'
    cov = g.node('ShaderNodeMapRange', {'From Min': 0.52, 'From Max': 0.74, 'To Min': 0.0, 'To Max': 1.0})
    cov.name = 'CLOUD_COVER'
    g.link(c1.outputs['Fac'], cov.inputs['Value'])
    # fade the deck near the horizon (perspective aliasing) and below it
    hz = g.node('ShaderNodeMapRange', {'From Min': 0.02, 'From Max': 0.16, 'To Min': 0.0, 'To Max': 1.0})
    g.link(dz, hz.inputs['Value'])
    mask = g.m('MULTIPLY', cov.outputs['Result'], hz.outputs['Result'])
    dens = g.node('ShaderNodeMath', operation='MULTIPLY')
    dens.name = 'CLOUD_AMOUNT'
    dens.inputs[1].default_value = 0.85
    g.link(mask, dens.inputs[0])
    # lit / shaded cloud colour (set per lighting preset)
    lit = g.node('ShaderNodeRGB')
    lit.name = 'CLOUD_LIT'
    shd = g.node('ShaderNodeRGB')
    shd.name = 'CLOUD_SHADE'
    thick = g.ramp(c1.outputs['Fac'], [(0.55, (0, 0, 0)), (0.85, (1, 1, 1))])
    ccol = g.mixc(g.sep(thick)[0], lit.outputs[0], shd.outputs[0])
    skyc = g.mixc(dens.outputs[0], sky.outputs['Color'], ccol)

    bg = g.node('ShaderNodeBackground', {'Strength': 1.0})
    bg.name = 'BG'
    g.link(skyc, bg.inputs['Color'])
    out = g.node('ShaderNodeOutputWorld')
    g.link(bg.outputs[0], out.inputs['Surface'])
    bpy.context.scene.world = w

    # --- sun lamp -------------------------------------------------------------
    sd = bpy.data.lights.get('Sun') or bpy.data.lights.new('Sun', 'SUN')
    sd.angle = math.radians(0.55)
    sun = bpy.data.objects.get('Sun') or bpy.data.objects.new('Sun', sd)
    if sun.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(sun)
    return w, sun


def set_sky(az, el, sun_color, sun_strength, sky_strength=0.09, clouds=0.85,
            cloud_lit=(11.0, 8.5, 6.5), cloud_shade=(3.6, 4.0, 4.8), cloud_cover=(0.52, 0.74),
            aerosol=1.6):
    w = bpy.context.scene.world
    nt = w.node_tree
    sky = nt.nodes['SKY']
    sky.sun_elevation = math.radians(el)
    # verified: sky sun_rotation == compass azimuth (0 = +Y north, 90 = +X east)
    sky.sun_rotation = math.radians(az)
    sky.aerosol_density = aerosol
    nt.nodes['BG'].inputs['Strength'].default_value = sky_strength
    nt.nodes['CLOUD_AMOUNT'].inputs[1].default_value = clouds
    nt.nodes['CLOUD_LIT'].outputs[0].default_value = tuple(cloud_lit) + (1,)
    nt.nodes['CLOUD_SHADE'].outputs[0].default_value = tuple(cloud_shade) + (1,)
    nt.nodes['CLOUD_COVER'].inputs['From Min'].default_value = cloud_cover[0]
    nt.nodes['CLOUD_COVER'].inputs['From Max'].default_value = cloud_cover[1]

    sun = bpy.data.objects['Sun']
    v = sun_vector(az, el)
    from mathutils import Vector
    sun.rotation_euler = Vector(v).to_track_quat('Z', 'Y').to_euler()
    sun.data.color = sun_color
    sun.data.energy = sun_strength
    sun.hide_render = el < -0.5


def render_settings(samples=128, res=(3840, 2160), threshold=0.02):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    c = sc.cycles
    c.device = 'CPU'
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = threshold
    c.adaptive_min_samples = 16
    c.use_denoising = True
    c.denoiser = 'OPENIMAGEDENOISE'
    c.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
    c.denoising_prefilter = 'ACCURATE'
    try:
        c.denoising_quality = 'HIGH'
    except Exception:
        pass
    c.max_bounces = 10
    c.diffuse_bounces = 3
    c.glossy_bounces = 3
    c.transmission_bounces = 8
    c.transparent_max_bounces = 24
    c.volume_bounces = 1
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.blur_glossy = 1.0
    c.sample_clamp_indirect = 8.0
    c.use_light_tree = True
    c.pixel_filter_type = 'BLACKMAN_HARRIS'
    c.filter_width = 1.5
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.use_persistent_data = True
    vs = sc.view_settings
    vs.view_transform = 'AgX'
    try:
        vs.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    vs.exposure = 0.0
    vs.gamma = 1.0
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_depth = '16'
    vl = sc.view_layers[0]
    vl.use_pass_mist = True
    w = sc.world
    w.mist_settings.start = 0.0
    w.mist_settings.depth = 60000.0
    w.mist_settings.falloff = 'LINEAR'
