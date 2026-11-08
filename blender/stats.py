"""Measure the built model so the design numbers in DESIGN.md are traceable.

    python blender/stats.py --blend model/qingyun_airport.blend > docs/model_stats.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy  # noqa: E402


def area(obj, mat_names=None, mask=None):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    tot = 0.0
    names = [m.name if m else '' for m in me.materials]
    for p in me.polygons:
        if mat_names is not None and names[p.material_index] not in mat_names:
            continue
        if mask is not None and not mask(p):
            continue
        tot += p.area
    ev.to_mesh_clear()
    return tot


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', default=os.path.join(HERE, '..', 'model', 'qingyun_airport.blend'))
    a = ap.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
    from qy import params as P
    O = bpy.data.objects
    s = {}
    s['hub_roof_area_m2'] = area(O['Roof_Panels'])
    s['hub_roof_bipv_m2'] = area(O['Roof_Panels'], {'pv_bipv'})
    s['hub_roof_clear_glass_m2'] = area(O['Roof_Panels'], {'glass_lowiron'})
    me = O['Roof_Panels'].data
    s['gridshell_nodes'] = len(me.vertices)
    s['gridshell_members'] = len(me.edges)
    s['gridshell_panels'] = len(me.polygons)
    pier_roofs = [o for o in O if o.name.startswith('Pier') and o.name.endswith('_Roof')]
    s['pier_roof_area_m2'] = sum(area(o, {'pv_pier'}) for o in pier_roofs)
    s['pier_count'] = len(pier_roofs)
    s['aircraft_at_contact_stands'] = len([o for o in O if o.name.startswith('AC_') and '_' in o.name[3:]])
    s['contact_stands'] = len(P.PIER_DIRS) * (2 * P.GATES_PER_SIDE + 1)
    s['pv_field_panel_area_m2'] = area(O['PV_Fields'])
    s['floating_pv_panel_area_m2'] = area(O['FloatPV_Panels'])
    s['floating_pv_islands'] = len(O['FloatPV_Floats'].data.polygons) // 6
    s['lake_area_m2'] = area(O['Lake_Water'])
    s['terrace_tread_area_m2_incl_hidden'] = area(O['Terrace_Beds'])
    # visible terrace (green-roof) footprint ~ union of layer 1 footprint
    import qy.landscape as LS
    s['terrace_footprint_m2'] = 2 * 0.5 * (LS.R_k(1) ** 2 - 260.0 ** 2) * LS.PHI_k(1)
    s['skywell_drop_m'] = P.Z_OCULUS - P.Z_RAIL
    s['oculus_diameter_m'] = 2 * P.R_OCULUS
    s['hub_diameter_m'] = [2 * P.R_NOTCH, 2 * P.R_LOBE]
    s['farthest_gate_from_hub_centre_m'] = P.PIER_START + P.PIER_LEN + 12.0
    s['runways'] = [{'x': r[0], 'length_m': r[2] - r[1], 'width_m': r[3]} for r in P.RUNWAYS]
    trees = 0
    for o in O:
        if o.name.startswith('Trees_'):
            trees += len(o.data.vertices)
    s['trees_and_shrubs_instanced'] = trees
    print(json.dumps({k: (round(v, 1) if isinstance(v, float) else v) for k, v in s.items()}, indent=2))


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    main(argv)
