"""Planting plan: generates instance point sets for trees and shrubs across the Sky Well, Lotus Hall, terraced hills, gorge,
causeway, lake shore and the surrounding forest belts."""
import math

import numpy as np
from mathutils.noise import noise as pnoise
from mathutils import Vector

from . import params as P
from .util import TAU, collection
from . import vegetation as V

# variant indices (alphabetical names in LIB_trees)
CAMPHOR_A, CAMPHOR_B, GINKGO_A, GINKGO_B, MAPLE, BLOSSOM, WILLOW, PINE, BAMBOO, SHRUB_A, SHRUB_B, SHRUB_C = range(12)


def _pick(rs, table, n):
    ids, w = zip(*table)
    w = np.asarray(w, float)
    return rs.choice(ids, size=n, p=w / w.sum())


def skywell(info, rs):
    pts, vid, sc = [], [], []
    terr = info['skywell_terraces']
    dr = (P.R_SKYWELL - P.R_POOL) / P.N_SKY_TERRACES
    for i, (z, rin) in enumerate(terr[:-1]):
        n = len(rin)
        rout = P.R_SKYWELL - i * dr
        for q in range(170):
            k = rs.randint(n)
            th = k / n * TAU
            # keep the foreground of the interior camera (az -105 deg) open
            if i <= 2 and abs(((th - math.radians(-105.0)) + math.pi) % TAU - math.pi) < math.radians(24):
                continue
            r = rin[k] + rs.uniform(1.6, max(1.8, rout - rin[k] + 1.2))
            pts.append((r * math.cos(th), r * math.sin(th), z + 0.3))
            vid.append(_pick(rs, [(SHRUB_A, 3), (SHRUB_B, 3), (SHRUB_C, 2.5), (BAMBOO, 1.0), (BLOSSOM, 1.2),
                                  (MAPLE, 1.0), (CAMPHOR_B, 0.6), (GINKGO_B, 0.8)], 1)[0])
            sc.append(rs.uniform(0.55, 0.95) if vid[-1] < SHRUB_A else rs.uniform(0.8, 1.3))
    return pts, vid, sc


def hall(info, rs):
    pts, vid, sc = [], [], []
    for (x, y, z) in info['planters']:
        pts.append((x, y, z))
        vid.append(rs.choice([CAMPHOR_A, GINKGO_A, CAMPHOR_B, MAPLE]))
        sc.append(rs.uniform(0.75, 1.0))
        for q in range(6):
            a = q / 6 * TAU + rs.uniform(-0.3, 0.3)
            pts.append((x + 3.0 * math.cos(a), y + 3.0 * math.sin(a), z))
            vid.append(rs.choice([SHRUB_A, SHRUB_B, SHRUB_C]))
            sc.append(rs.uniform(0.5, 0.8))
    return pts, vid, sc


def _bilerp(G, s, t):
    ns, nt = G.shape[:2]
    fi, fj = s * (ns - 1), t * (nt - 1)
    i0, j0 = min(int(fi), ns - 2), min(int(fj), nt - 2)
    a, b = fi - i0, fj - j0
    return (G[i0, j0] * (1 - a) * (1 - b) + G[i0 + 1, j0] * a * (1 - b) + G[i0, j0 + 1] * (1 - a) * b +
            G[i0 + 1, j0 + 1] * a * b)


def _level_of(x, y):
    """Highest terrace level whose footprint contains (x, y) (0 = none)."""
    from . import landscape as LS
    r = math.hypot(x, y)
    phi = math.atan2(abs(x), -y)
    best = 0
    for k in range(1, LS.NL + 1):
        if abs(x) >= LS.X_k(k) and phi <= LS.PHI_k(k) and LS.r_in(phi) <= r <= LS.R_k(k):
            best = k
    return best


def terraces(tread_grids, rs):
    from . import landscape as LS
    pts, vid, sc = [], [], []
    for k in range(1, LS.NL + 1):
        z = k * LS.DZ + 0.3
        r_hi = LS.R_k(k)
        r_lo = LS.R_k(k + 1) if k < LS.NL else 230.0
        row_kind = [GINKGO_B, MAPLE, GINKGO_A, CAMPHOR_B][k % 4]
        for side in (-1, 1):
            # tree ribbon along the outer lip of the visible tread
            rr = r_hi - 4.0
            for phi in np.arange(0.0, LS.PHI_k(k), 8.5 / rr):
                x, y = side * rr * math.sin(phi), -rr * math.cos(phi)
                if _level_of(x, y) != k:
                    continue
                pts.append((x, y, z))
                vid.append(row_kind if rs.rand() > 0.12 else BLOSSOM)
                sc.append(rs.uniform(0.8, 1.15))
            # interior clusters + shrubs on the visible band
            area = 0.5 * (r_hi ** 2 - r_lo ** 2) * LS.PHI_k(k)
            n = int(area / 75.0)
            for q in range(n):
                rr = math.sqrt(rs.uniform(r_lo ** 2, (r_hi - 7.0) ** 2))
                phi = rs.uniform(0, LS.PHI_k(k))
                x, y = side * rr * math.sin(phi), -rr * math.cos(phi)
                if _level_of(x, y) != k:
                    continue
                pts.append((x, y, z))
                if rs.rand() < 0.14:
                    vid.append(_pick(rs, [(CAMPHOR_A, 2), (CAMPHOR_B, 2), (BLOSSOM, 1), (PINE, 0.6), (BAMBOO, 0.8)], 1)[0])
                    sc.append(rs.uniform(0.75, 1.1))
                else:
                    vid.append(rs.choice([SHRUB_A, SHRUB_B, SHRUB_C]))
                    sc.append(rs.uniform(0.7, 1.4))
    return pts, vid, sc


def gorge_and_causeway(rs, y_hub):
    pts, vid, sc = [], [], []
    for s in (-1, 1):
        # causeway (over the lake): willows + camphor avenues
        for x0, kinds in ((40.0, [(WILLOW, 2), (CAMPHOR_A, 1)]), (56.0, [(GINKGO_A, 2), (CAMPHOR_A, 1), (MAPLE, 1)])):
            y = -1860.0
            while y < -700.0:
                pts.append((s * x0 + rs.normal(0, 0.6), y, 0.1))
                vid.append(_pick(rs, kinds, 1)[0])
                sc.append(rs.uniform(0.85, 1.15))
                y += rs.uniform(11, 15)
        # gorge: a light single avenue so the terraced walls stay visible
        y = -690.0
        while y < y_hub - 50:
            pts.append((s * 44.0 + rs.normal(0, 0.4), y, 0.12))
            vid.append(_pick(rs, [(GINKGO_B, 3), (MAPLE, 1), (BLOSSOM, 1)], 1)[0])
            sc.append(rs.uniform(0.8, 1.0))
            y += rs.uniform(17, 22)
        # willows on the river banks
        y = -720.0
        while y < y_hub - 60:
            pts.append((s * 11.0, y, 0.05))
            vid.append(WILLOW if rs.rand() < 0.5 else BLOSSOM)
            sc.append(rs.uniform(0.6, 0.8))
            y += rs.uniform(30, 45)
    # forecourt plaza trees
    for q in range(26):
        x = rs.uniform(-58, 58)
        if abs(x) < 8:
            continue
        pts.append((x, y_hub - 35 + rs.uniform(-3, 3), 0.14))
        vid.append(rs.choice([GINKGO_B, BLOSSOM, MAPLE]))
        sc.append(rs.uniform(0.7, 1.0))
    return pts, vid, sc


def lake_shore(shore, rs):
    pts, vid, sc = [], [], []
    shore = np.asarray(shore)
    cx, cy = P.LAKE_C
    n = len(shore)
    for i in range(0, n, 1):
        p = shore[i]
        d = p - np.array([cx, cy])
        d /= np.linalg.norm(d)
        for band, kinds in ((rs.uniform(6, 12), [(WILLOW, 3), (BLOSSOM, 0.6)]),
                            (rs.uniform(18, 40), [(CAMPHOR_A, 2), (GINKGO_A, 1), (MAPLE, 1), (PINE, 1)])):
            q = p + d * band
            if abs(q[0]) < 70:
                continue
            if rs.rand() < 0.75:
                pts.append((q[0] + rs.normal(0, 2), q[1] + rs.normal(0, 2), 0.0))
                vid.append(_pick(rs, kinds, 1)[0])
                sc.append(rs.uniform(0.8, 1.25))
    return pts, vid, sc


def _forest_region(rs, x0, x1, y0, y1, spacing, thresh, exclude):
    xs = np.arange(x0, x1, spacing)
    ys = np.arange(y0, y1, spacing)
    X, Y = np.meshgrid(xs, ys)
    X = X.ravel() + rs.uniform(-spacing * 0.45, spacing * 0.45, X.size)
    Y = Y.ravel() + rs.uniform(-spacing * 0.45, spacing * 0.45, Y.size)
    keep = np.ones(X.size, bool)
    for i in range(X.size):
        nv = pnoise(Vector((X[i] / 520.0, Y[i] / 520.0, 1.7))) + 0.5 * pnoise(Vector((X[i] / 140.0, Y[i] / 140.0, 4.2)))
        if nv < thresh:
            keep[i] = False
    for f in exclude:
        keep &= ~f(X, Y)
    return X[keep], Y[keep]


def forests(rs):
    def rw_corr(X, Y):
        m = np.zeros(X.size, bool)
        for (x, y0, y1, w) in P.RUNWAYS:
            m |= np.abs(X - x) < 300
        return m

    def roads(X, Y):
        return np.abs(X) < 85

    def lake(X, Y):
        cx, cy = P.LAKE_C
        ax, ay = P.LAKE_R
        return ((X - cx) / (ax * 1.12)) ** 2 + ((Y - cy) / (ay * 1.18)) ** 2 < 1

    def airside(X, Y):
        return (np.abs(X) < 3670) & (Y > -2620) & (Y < 3120) & ~((Y < -620) & (np.abs(X) < 1380))

    regions = [
        (-4200, 4200, -3600, -1750, 11.0, -0.05),
        (-1380, 1380, -1750, -620, 13.0, 0.05),
        (3700, 5200, -3600, 4300, 16.0, -0.1),
        (-5200, -3700, -3600, 4300, 16.0, -0.1),
        (-3700, 3700, 3150, 4600, 16.0, -0.1),
    ]
    PX, PY = [], []
    for (x0, x1, y0, y1, sp, th) in regions:
        X, Y = _forest_region(rs, x0, x1, y0, y1, sp, th, [rw_corr, roads, lake, airside])
        PX.append(X)
        PY.append(Y)
    X = np.concatenate(PX)
    Y = np.concatenate(PY)
    n = X.size
    vid = _pick(rs, [(CAMPHOR_A, 3), (CAMPHOR_B, 3), (PINE, 3), (GINKGO_A, 1.2), (GINKGO_B, 1),
                     (MAPLE, 1.2), (BLOSSOM, 0.2), (BAMBOO, 0.5)], n)
    sc = rs.uniform(0.8, 1.35, n)
    pts = np.stack([X, Y, np.full(n, -0.4)], 1)
    return pts, vid, sc


def build(root, hub_info, land_info, y_hub):
    tree_objs, tlib = V.build_variants()
    coll = collection('Vegetation', root)
    rs = np.random.RandomState(42)
    sets = {
        'Trees_SkyWell': skywell(hub_info, rs),
        'Trees_Hall': hall(hub_info, rs),
        'Trees_Terraces': terraces(land_info['terraces'], rs),
        'Trees_Gorge': gorge_and_causeway(rs, y_hub),
        'Trees_Lake': lake_shore(land_info['shore'], rs),
    }
    for name, (p, v, s) in sets.items():
        V.scatter(name, coll, tlib, p, v, s, rs)
    fp, fv, fs = forests(rs)
    V.scatter('Trees_Forest', coll, tlib, fp, fv, fs, rs)
    counts = {k: len(v[0]) for k, v in sets.items()}
    counts['Trees_Forest'] = len(fp)
    return counts
