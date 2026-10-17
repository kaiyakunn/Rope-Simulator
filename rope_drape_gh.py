"""
ROPE DRAPE - Grasshopper Python script (Rhino 7+ GhPython or Rhino 8 Script component)

The ropes are modelled ON your input curves, at their real position and height.
The BOTTOM rope (green) uses its input curve as its centre-line, unchanged.
The TOP rope (yellow) follows its own input curve, including its Z, and is lifted only
where it crosses a bottom rope, just enough to sit on it, then droops back toward its own curve.
Change the Z of either input curve and the ropes follow.

SAG also DEFORMS the rope: where the two ropes press together, both cross-sections are
squashed (flattened vertically, bulging sideways). Higher Sag = softer rope = more squash.

INPUTS (name them exactly like this; set TopCrvs and BotCrvs to List access)
  TopCrvs      Curve   the rope(s) that must sit ON TOP  (yellow)
  BotCrvs      Curve   the rope(s) that lie UNDERNEATH   (green)
  Diameter     float   diameter of the top rope
  BotDiameter  float   (optional) diameter of the bottom rope, default = Diameter
  Sag          float   0 = stiff rope: long gentle ramp, no squashing
                       1 = limp soft rope: hugs the other rope, drops quickly, squashes most
  Squash       float   (optional) max flattening at Sag = 1, as a fraction of the rope
                       thickness. Default 0.35 (35 %), allowed 0 - 0.6. Squash = 0 turns
                       the deformation off.
  Droop        float   (optional) extra gravity sag of the top rope, in rope diameters.
                       0 = none, 0.5 = default, 1-2 = very saggy.
  Ground       float   (optional) Z of the floor. The top rope will never sink below it
                       (its centre stays at Ground + radius). Leave empty for no floor.
  Res          float   (optional) sampling step, default = Diameter / 3
  Seg          int     (optional) segments around the rope cross-section, default 12

OUTPUTS
  TopRopes     SubD    top rope SubD tubes     (colour them yellow)
  BotRopes     SubD    bottom rope SubD tubes  (colour them green)
  Cages        Mesh    the quad control cages the SubDs were built from
  Centers      Curve   3D centre-lines
  Info         str     summary. 'min gap' close to 0 = rope sits exactly on the other one
                       (measured against the squashed thickness); clearly negative =
                       penetration (try a smaller Res)

NOTE: the curves need to cross when seen from ABOVE (Top viewport). Their Z values are used
as they are. Crossing detection assumes the bottom rope is fairly flat near the crossing.
"""
import math
import Rhino.Geometry as rg
import scriptcontext as sc

tol = sc.doc.ModelAbsoluteTolerance
atol = sc.doc.ModelAngleToleranceRadians


def as_list(x):
    """accept None, a single item, or a list"""
    if x is None:
        return []
    if isinstance(x, rg.GeometryBase):
        return [x]
    if isinstance(x, (int, float, str)):
        return [x]
    try:
        return list(x)
    except TypeError:
        return [x]


def to_curve(x):
    """turn a Guid (referenced Rhino object), curve or GH wrapper into a Rhino Curve"""
    if x is None:
        return None
    if isinstance(x, rg.Curve):
        return x
    try:
        import rhinoscriptsyntax as rs
        c = rs.coercecurve(x)
        if c is not None:
            return c
    except Exception:
        pass
    try:
        import System
        if isinstance(x, System.Guid):
            obj = sc.doc.Objects.FindId(x)
            if obj is not None and isinstance(obj.Geometry, rg.Curve):
                return obj.Geometry
    except Exception:
        pass
    if hasattr(x, "Value") and isinstance(x.Value, rg.Curve):
        return x.Value
    return None


def flatten(c):
    """plan-view copy of a curve with the SAME parameterisation (parameters map back to the 3D curve)"""
    n = c.ToNurbsCurve()
    n.Transform(rg.Transform.PlanarProjection(rg.Plane.WorldXY))
    return n


def make_wfun(others, d_full, d_none):
    """squash weight 0..1 for a point: 1 when it touches another rope, fading to 0 at d_none"""
    def w(P):
        best = None
        for g in others:
            ok, t = g.ClosestPoint(P)
            if ok:
                d = g.PointAt(t).DistanceTo(P)
                if best is None or d < best:
                    best = d
        if best is None:
            return 0.0
        u = (d_none - best) / (d_none - d_full)
        u = min(max(u, 0.0), 1.0)
        return u * u * (3.0 - 2.0 * u)
    return w


def make_subd(curve, radius, seg, cage_step, wfun=None, Q=0.0):
    """SubD tube around a centre-line, optionally squashed where wfun > 0.
    Returns (SubD or None, cage Mesh or None)."""
    n = max(int(curve.GetLength() / cage_step), 4)
    ts = curve.DivideByCount(n, True)
    if not ts:
        return None, None
    frames = curve.GetPerpendicularFrames(ts)
    if not frames or len(frames) != len(ts):
        return None, None

    # a cage circle shrinks when smoothed; inflate it so the limit surface keeps the true radius
    f = (4.0 + 2.0 * math.cos(2.0 * math.pi / seg)) / 6.0
    r = radius / f

    zaxis = rg.Vector3d.ZAxis
    fr = []  # per frame: origin, tangent, 'up' axis, 'side' axis, radius along up, radius along side
    for pl in frames:
        T = pl.ZAxis
        up = zaxis - T * rg.Vector3d.Multiply(zaxis, T)
        if up.Length < 1e-6:
            up = pl.YAxis
        else:
            up.Unitize()
        side = rg.Vector3d.CrossProduct(T, up)
        w = wfun(pl.Origin) if (wfun is not None and Q > 0.0) else 0.0
        fr.append((pl.Origin, T, up, side, r * (1.0 - Q * w), r * (1.0 + 0.8 * Q * w)))

    rows = []  # (origin, axisA, axisB, radiusA, radiusB)

    def add_row(F, off, scale):
        o, T, ua, ub, ra, rb = F
        rows.append((o + T * off, ua, ub, ra * scale, rb * scale))

    caps = [math.radians(70.0), math.radians(35.0)]
    for t in caps:                                   # rounded start cap
        add_row(fr[0], -r * math.sin(t), math.cos(t))
    for F in fr:
        add_row(F, 0.0, 1.0)
    for t in reversed(caps):                         # rounded end cap
        add_row(fr[-1], r * math.sin(t), math.cos(t))

    mesh = rg.Mesh()
    for (o, ua, ub, ra, rb) in rows:
        for j in range(seg):
            a = 2.0 * math.pi * j / seg
            mesh.Vertices.Add(o + ua * (ra * math.cos(a)) + ub * (rb * math.sin(a)))
    a0 = mesh.Vertices.Add(fr[0][0] - fr[0][1] * r)
    a1 = mesh.Vertices.Add(fr[-1][0] + fr[-1][1] * r)

    def vi(i, j):
        return i * seg + (j % seg)

    nr = len(rows)
    for i in range(nr - 1):
        for j in range(seg):
            mesh.Faces.AddFace(vi(i, j), vi(i, j + 1), vi(i + 1, j + 1), vi(i + 1, j))
    for j in range(seg):
        mesh.Faces.AddFace(a0, vi(0, j + 1), vi(0, j))
        mesh.Faces.AddFace(vi(nr - 1, j), vi(nr - 1, j + 1), a1)

    mesh.Normals.ComputeNormals()
    mesh.Compact()
    try:                                             # make sure normals point outward
        vol = rg.VolumeMassProperties.Compute(mesh)
        if vol is not None and vol.Volume < 0:
            mesh.Flip(True, True, True)
    except Exception:
        pass

    try:
        sd = rg.SubD.CreateFromMesh(mesh)
    except Exception:
        sd = None
    return sd, mesh


# ---------- inputs ----------
tops = [c for c in (to_curve(i) for i in as_list(TopCrvs)) if c is not None]
bots = [c for c in (to_curve(i) for i in as_list(BotCrvs)) if c is not None]

Dt = float(Diameter) if Diameter else 100.0
Db = float(BotDiameter) if BotDiameter else Dt
Rt, Rb = Dt * 0.5, Db * 0.5
s = 0.5 if Sag is None else min(max(float(Sag), 0.0), 1.0)
step = float(Res) if Res else Dt / 3.0
seg = max(int(Seg), 6) if Seg else 12             # segments around the rope cross-section
cage_step = max(Dt * 0.6, step)                   # spacing of cage rings along the rope
droop = 0.5 if Droop is None else max(float(Droop), 0.0)   # hang below the input curve, in rope diameters
ground = None if Ground is None else float(Ground)         # optional floor
sq_max = 0.35 if Squash is None else min(max(float(Squash), 0.0), 0.6)
Q = sq_max * s                                    # actual flattening fraction (0 = round rope)

clear = Rt + Rb                                   # centre distance of two touching round ropes
clear_eff = clear * (1.0 - Q)                     # centre distance when both are squashed
span = Dt * (1.0 + 12.0 * (1.0 - s))              # length over which the top rope ramps down

TopRopes, BotRopes, Centers, Cages = [], [], [], []

# ---------- bottom ropes: centre-lines are the input curves ----------
bot_centers = [c.ToNurbsCurve() for c in bots]
bots_flat = [flatten(c) for c in bots]
for g in bot_centers:
    Centers.append(g)

# ---------- top ropes: drape over the bottom ropes ----------
top_centers = []
min_gap = None
wfun_top = make_wfun(bot_centers, clear_eff * 1.05, clear * 1.7) if Q > 0.0 else None

for c in tops:
    c3 = c.ToNurbsCurve()
    total = c3.GetLength()
    count = max(int(total / step), 8)
    ts = c3.DivideByCount(count, True)
    if not ts:
        continue
    pts3 = [c3.PointAt(t) for t in ts]                    # the rope's own 3D path
    pts = [rg.Point3d(p.X, p.Y, 0.0) for p in pts3]       # plan-view positions

    # arc length along the rope at every sample
    lens = [0.0]
    for k in range(1, len(pts3)):
        lens.append(lens[-1] + pts3[k].DistanceTo(pts3[k - 1]))

    # 1) minimum extra lift each sample needs so it does not penetrate a bottom rope
    hmin = []
    for k, p in enumerate(pts):
        h = 0.0
        for bi, bf in enumerate(bots_flat):
            ok, tb = bf.ClosestPoint(p)
            if ok:
                x = bf.PointAt(tb).DistanceTo(p)
                if x < clear_eff:
                    zb = bot_centers[bi].PointAt(tb).Z           # actual height of the bottom rope here
                    zmin = zb + math.sqrt(clear_eff * clear_eff - x * x)
                    h = max(h, zmin - pts3[k].Z)                 # extra lift above the top curve's own Z
        hmin.append(h)

    # 2) sag: spread that lift along the rope with a smooth ramp, then let it hang (droop)
    contact = [k for k in range(len(pts)) if hmin[k] > 1e-9]
    droop_len = Dt * (3.0 + 5.0 * s)                 # length over which the rope hangs down beside the crossing
    cpts = []
    for k in range(len(pts)):
        h = 0.0
        dc = None                                     # arc distance to the nearest supported (contact) point
        for m in contact:
            d = abs(lens[k] - lens[m])
            if dc is None or d < dc:
                dc = d
            if d < span:
                v = hmin[m] * 0.5 * (1.0 + math.cos(math.pi * d / span))
                if v > h:
                    h = v
        dip = 0.0
        if dc is not None and 0.0 < dc < droop_len:
            dip = droop * Dt * math.sin(math.pi * dc / droop_len) ** 2
        z = pts3[k].Z + h - dip
        if ground is not None:
            z = max(z, ground + Rt)
        cpts.append(rg.Point3d(pts3[k].X, pts3[k].Y, z))

    cl = rg.Curve.CreateInterpolatedCurve(cpts, 3)
    if cl is None:
        continue
    top_centers.append(cl)
    Centers.append(cl)

    sd, cage = make_subd(cl, Rt, seg, cage_step, wfun_top, Q)
    if sd is not None:
        TopRopes.append(sd)
    if cage is not None:
        Cages.append(cage)

    # 3) clearance check
    for P in cpts:
        for g in bot_centers:
            ok, tb = g.ClosestPoint(P)
            if ok:
                gap = g.PointAt(tb).DistanceTo(P) - clear_eff
                min_gap = gap if min_gap is None else min(min_gap, gap)

# ---------- bottom rope SubDs (squashed where the top ropes press on them) ----------
wfun_bot = make_wfun(top_centers, clear_eff * 1.05, clear * 1.7) if (Q > 0.0 and top_centers) else None
for g in bot_centers:
    sd, cage = make_subd(g, Rb, seg, cage_step, wfun_bot, Q)
    if sd is not None:
        BotRopes.append(sd)
    if cage is not None:
        Cages.append(cage)

Info = "{} top / {} bottom rope(s) | D={:.1f}  sag={:.2f}  squash={:.0f}%  droop={:.2f}  ramp span={:.1f} | min gap = {}".format(
    len(tops), len(bots), Dt, s, Q * 100.0, droop, span,
    "n/a (no crossing found)" if min_gap is None else "{:.2f}".format(min_gap))
