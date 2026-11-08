"""Master plan constants for Qingyun Shanshui International Airport (concept).

Units: metres.  +X = east, +Y = north, Z = up.  Apron level is z = 0.
The hub sits at the origin; the landside "mountain" faces south (traditional
south-facing axis); five piers radiate at 60 degree spacing.
"""
import math

import numpy as np

D2R = math.pi / 180.0

# ---- vertical datum ------------------------------------------------------
Z_RAIL = -22.0        # B2  : maglev / HSR / metro platforms under the Sky Well
Z_GROUND = 0.0        # L0  : apron, landside garden hall, arrivals
Z_DEP = 12.0          # L2  : departures / airside "Lotus Hall"
Z_PIER = 6.0          # pier gate-lounge floor (boarding-bridge sill ~ 5-6 m)

# ---- hub ("Lotus") -------------------------------------------------------
LANDSIDE_DIR = -90.0                          # deg, south
PIER_DIRS = [-30.0, 30.0, 90.0, 150.0, 210.0]  # deg
LOBE_DIRS = [LANDSIDE_DIR] + PIER_DIRS
R_OCULUS = 16.0       # oculus radius  (32 m opening)
Z_OCULUS = 36.0       # oculus rim (the LOW point of the inverted-lotus roof)
R_NOTCH = 232.0       # eave radius between lobes
R_LOBE = 282.0        # eave radius at lobe tips
OVERHANG = 16.0       # roof overhang beyond facade
R_SKYWELL = 60.0      # void radius at departure level
R_POOL = 26.0         # vortex pool radius at B2
N_SKY_TERRACES = 9


def lobe(theta):
    """0..1 lobe weight, 1 on a pier / landside axis (6-fold symmetry)."""
    return (0.5 + 0.5 * np.cos(6.0 * (theta - LANDSIDE_DIR * D2R))) ** 3


def r_eave(theta):
    return R_NOTCH + (R_LOBE - R_NOTCH) * lobe(theta)


def r_facade(theta):
    return r_eave(theta) - OVERHANG


def roof_z(r, theta):
    """Inverted-lotus roof: low at the oculus (rain funnels to the centre),
    cresting at ~half radius, then curling down to the eave like a leaf margin."""
    lb = lobe(theta)
    R = r_eave(theta)
    u = np.clip((r - R_OCULUS) / (R - R_OCULUS), 0.0, 1.0)
    cu = 0.50
    z_crest = 53.0 + 5.0 * lb
    z_eave = 27.0 + 4.0 * lb
    t1 = np.clip(u / cu, 0, 1)
    inner = Z_OCULUS + (z_crest - Z_OCULUS) * (1.0 - (1.0 - t1) ** 2.3)
    t2 = np.clip((u - cu) / (1 - cu), 0, 1)
    outer = z_crest - (z_crest - z_eave) * t2 ** 1.7
    return np.where(u < cu, inner, outer)


# ---- piers ---------------------------------------------------------------
PIER_START = 250.0    # radius where the pier body begins (under the hub eave)
PIER_LEN = 545.0
PIER_HW0 = 27.0       # half width at root
PIER_HW1 = 19.0       # half width near tip
PIER_EAVE = 14.5
PIER_RIDGE0 = 25.0
PIER_RIDGE1 = 20.0
GATES_PER_SIDE = 7
GATE_T0 = 62.0
GATE_PITCH = 70.0


def pier_hw(t):
    """Leaf-shaped plan: tapering, then a rounded tip."""
    t = np.asarray(t, dtype=float)
    base = PIER_HW0 + (PIER_HW1 - PIER_HW0) * np.clip(t / PIER_LEN, 0, 1) ** 1.3
    tip0 = PIER_LEN - 46.0
    k = np.clip((t - tip0) / (PIER_LEN - tip0), 0, 1)
    return base * np.sqrt(np.clip(1 - k ** 2.2, 0, 1))


# ---- airfield ------------------------------------------------------------
RUNWAYS = [  # (x centre, y0, y1, width) -- pairs 780 m apart: >= 760 m allows
    (-2340.0, -1750.0, 2050.0, 60.0),       # segregated parallel operations (ICAO);
    (-1560.0, -1450.0, 2350.0, 60.0),       # the two pairs are 3.1 km apart, i.e.
    (1560.0, -1450.0, 2350.0, 60.0),        # fully independent.
    (2340.0, -1750.0, 2050.0, 60.0),
]
APRON_R = 975.0
RING_TAXI_R = (1015.0, 1080.0)

# ---- landside -------------------------------------------------------------
CANYON_HALF = 62.0          # half width of the landside canyon at grade
TERRACE_R0 = 268.0          # terraces start (meet roof eave)
TERRACE_R1 = 560.0          # terraces reach grade
TERRACE_HALF_ANGLE = 34.0   # deg either side of south axis
LAKE_C = (0.0, -1280.0)
LAKE_R = (980.0, 430.0)

TOWER_POS = (-370.0, -475.0)
TOWER_H = 118.0


def polar(r, theta_deg):
    a = theta_deg * D2R
    return (r * math.cos(a), r * math.sin(a))
