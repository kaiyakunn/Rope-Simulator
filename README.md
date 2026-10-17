# Rope Drape – Grasshopper script

A Grasshopper Python component that models a soft rope **draped over another rope**, inspired by
a large stone/rope sculpture where one tube crosses over another and sags under gravity.

You draw two curves. The script builds both ropes as **SubD tubes** exactly on your curves, lifts the
top rope just enough to rest on the bottom one, lets it droop under gravity, and squashes both ropes
where they press together.

<!-- Add a screenshot: put an image in docs/images/ and uncomment the line below -->
<!-- ![preview](docs/images/preview.png) -->

## Features

- **Choose which rope is on top** – a separate input for top and bottom curves.
- **Rope diameter** – separate diameters for the top and bottom rope.
- **Sag control** – one slider from stiff (long, gentle ramp, round rope) to limp (hugs the other rope, drops quickly, squashes).
- **Deformation** – cross-sections flatten and bulge where the ropes press together (`Squash`).
- **Gravity droop** – the top rope hangs below its input curve beside the crossing (`Droop`), with an optional floor (`Ground`).
- **Follows your curves in 3D** – ropes sit on the input curves at their real height; edit the Z of a curve and the ropes follow.
- **SubD output** with an editable quad control cage.

## Requirements

- Rhino 7 or newer (SubD support). Rhino 8 recommended for SubD preview inside Grasshopper.
- Grasshopper with the **GhPython** (Rhino 7) or **Script** (Rhino 8) component.

## Setup

1. Add a Python / Script component to the canvas and paste in [`src/rope_drape_gh.py`](src/rope_drape_gh.py).
2. Create the inputs and outputs below. Names must match exactly.
3. Set `TopCrvs` and `BotCrvs` to **List Access** and **Type hint → Curve**.

### Inputs

| Name | Type | Access | Description |
|------|------|--------|-------------|
| `TopCrvs` | Curve | List | Rope(s) that sit **on top** |
| `BotCrvs` | Curve | List | Rope(s) that lie **underneath** |
| `Diameter` | float | Item | Diameter of the top rope |
| `BotDiameter` | float | Item | *(optional)* Diameter of the bottom rope (default = `Diameter`) |
| `Sag` | float | Item | 0 = stiff, 1 = limp & soft (also drives squashing) |
| `Squash` | float | Item | *(optional)* Max flattening at `Sag = 1`, 0–0.6, default 0.35 |
| `Droop` | float | Item | *(optional)* Gravity sag in rope diameters, default 0.5 |
| `Ground` | float | Item | *(optional)* Floor Z; the top rope never sinks below it |
| `Res` | float | Item | *(optional)* Sampling step, default `Diameter / 3` |
| `Seg` | int | Item | *(optional)* Segments around the cross-section, default 12 |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `TopRopes` | SubD | Top rope(s) |
| `BotRopes` | SubD | Bottom rope(s) |
| `Cages` | Mesh | Quad control cages used to build the SubDs |
| `Centers` | Curve | 3D centre-lines of the ropes |
| `Info` | str | Summary, including `min gap` (≈ 0 = resting on the other rope, clearly negative = overlap) |

## Usage tips

- The two curves must **cross when viewed from above** (Top viewport). If `Info` says no crossing was found, extend a curve.
- Check units: with millimetres a `Diameter` of 300 is sensible; with metres use ~0.3.
- A soft, heavy rope like the reference photo: `Sag ≈ 0.8`, `Squash ≈ 0.4`, `Droop ≈ 1`, and set `Ground` to the floor height.
- If the ropes overlap slightly (negative `min gap`), lower `Res` or `Squash`.
- To get NURBS geometry, use the Grasshopper **SubD → Brep** component, or bake the SubDs.

## How it works

1. Both input curves are used at their true 3D position; a plan-view copy is used to find crossings.
2. For each sample on the top rope, the minimum height needed to rest on the bottom rope is computed from the contact geometry of two cylinders.
3. That lift is spread along the rope with a smooth ramp whose length depends on `Sag`, then a gravity `Droop` is applied beside the crossing.
4. A quad cage is built around each centre-line (rotation-minimising frames, rounded ends) and converted to a SubD. Cage rings are squashed according to their distance to the other rope.

## Limitations

- Crossing detection assumes the bottom rope is fairly flat near the crossing.
- This is a geometric approximation of draping, not a physics simulation. For true physics use Kangaroo.
- The sideways bulge of squashed ropes is only approximated in the contact calculation.

## Contributing

Issues and pull requests are welcome.

## License

[MIT](LICENSE)
