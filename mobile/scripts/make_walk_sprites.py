#!/usr/bin/env python3
"""Build the logo's sprite sheets from the app icon.

the cloud and the top of the trunk come straight from the artwork, and only the
legs are redrawn, as thick round strokes in the logo's green. frames sit side by
side in one png per move, like the resume site's player sheet, and the app steps
through them the way css steps() does.

- walk-sheet.png: side view walking right (the intro walk-in)
- walk-back.png: walking up the screen, back to you (no glasses, legs stepping away)
- walk-front.png: walking down the screen, facing you, feet stepping toward you
- jump-front.png / jump-back.png: stand, crouch, deep crouch, spring, tuck. played
  forward to jump out of the screen and backward to land back in

    python mobile/scripts/make_walk_sprites.py
"""
from math import cos, pi, radians, sin
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parents[1]
ICON = HERE / "assets" / "icon.png"
BRAND = HERE / "src" / "brand"
OUT = BRAND / "walk-sheet.png"
FRAMES = 8
FRAME = 400  # px per frame in the sheet
WORK = 960  # frames are drawn at this size and scaled down, for smooth edges
# same framing as src/brand/logo.png (measured from the ink of both), so a frame
# can stand in for the logo exactly
CROP = (61.3, 47.0, 967.1, 952.8)
GREEN = (13, 72, 49, 255)
# leg geometry in WORK pixels, measured off the logo: the trunk is about 70 px
# wide and the legs split around y 660, with the feet near the bottom edge
HIP = (472, 662)
THIGH, SHIN, FOOT, WIDTH = 128, 118, 80, 70
CUT_Y = 600  # cut inside the straight part of the trunk, above where the old legs start


def body(back: bool = False) -> Image.Image:
    im = Image.open(ICON).convert("RGB").crop(tuple(round(v) for v in CROP)).resize((WORK, WORK), Image.LANCZOS)
    a = np.asarray(im).astype(int)
    light = a.min(axis=2) > 200
    # the background is the white touching the border; the white glasses stay
    lab, _ = ndimage.label(light)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(border))
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    edge = ndimage.binary_dilation(bg, iterations=2) & ~bg
    alpha[edge] = np.clip((255 - a.min(axis=2)[edge]) * 2.2, 0, 255).astype(np.uint8)
    alpha[CUT_Y:] = 0
    rgb = a.astype(np.uint8)
    if back:
        # from behind there are no glasses: the light pixels that aren't
        # background are the lenses, so they're painted over in the cloud's green
        lenses = light & ~bg
        lenses = ndimage.binary_dilation(lenses, iterations=3) & ~bg
        rgb = rgb.copy()
        rgb[lenses] = GREEN[:3]
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def point(origin, angle_deg, length):
    # angles are from straight down, positive toward the front (right, the way he faces)
    return origin[0] + sin(radians(angle_deg)) * length, origin[1] + cos(radians(angle_deg)) * length


def stroke(draw, points):
    draw.line(points, fill=GREEN, width=WIDTH, joint="curve")
    r = WIDTH / 2
    # a disc on every joint too, otherwise the knee and ankle show thin seams once scaled down
    for x, y in points:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=GREEN)


def leg(draw, hip, phase):
    # the thigh swings back and forth; while the leg swings forward (cos > 0)
    # the knee folds so the foot clears the ground, which is what makes it read
    # as a step instead of a pendulum
    thigh = 30 * sin(phase)
    fold = 55 * max(0.0, cos(phase)) ** 1.4
    knee = point(hip, thigh, THIGH)
    shin = thigh - fold
    ankle = point(knee, shin, SHIN)
    # the foot points forward like in the logo, tipping up a little on the front leg
    toe = point(ankle, shin + 100 - 12 * max(0.0, sin(phase)), FOOT)
    stroke(draw, [hip, knee, ankle, toe])


def frame(base: Image.Image, i: int) -> Image.Image:
    phase = 2 * pi * i / FRAMES
    # he rises a little as each leg passes under him, twice per cycle
    bob = round(-10 * cos(2 * phase) - 10)
    canvas = Image.new("RGBA", (WORK, WORK), (0, 0, 0, 0))
    legs = Image.new("RGBA", (WORK, WORK), (0, 0, 0, 0))
    draw = ImageDraw.Draw(legs)
    hip = (HIP[0], HIP[1] + bob)
    # the far leg first, so the near one is drawn over it
    leg(draw, hip, phase + pi)
    leg(draw, hip, phase)
    # a short trunk piece joins the cut body to the hip whatever the bob
    draw.line([(HIP[0], CUT_Y - 40 + bob), hip], fill=GREEN, width=WIDTH)
    canvas.alpha_composite(legs)
    canvas.alpha_composite(base, (0, bob))
    return canvas.resize((FRAME, FRAME), Image.LANCZOS)


# front and back views: the legs hang side by side under the trunk instead of one
# in front of the other. PELVIS is where the trunk ends and they split.
PELVIS_Y = 700
# each hip is this far either side of the trunk. closer than this and the two
# legs merged into what looked like one hollow outline
LEG_GAP = 64
GROUND = PELVIS_Y + 212  # feet end just above the frame edge instead of being clipped by it


def foot(draw, x, y, scale):
    # seen from the front or back a foot is a short flat stroke across the leg's end
    half = 30 * scale
    r = WIDTH / 2 * (0.85 + 0.15 * scale)
    draw.line([(x - half, y), (x + half, y)], fill=GREEN, width=round(r * 2))
    for fx in (x - half, x + half):
        draw.ellipse((fx - r, y - r, fx + r, y + r), fill=GREEN)


def pose(base: Image.Image, *, dy=0.0, dx=0.0, squash=(1.0, 1.0), legs=()) -> Image.Image:
    """One front or back frame: the cloud moved and squashed, then the legs.

    each leg is (side, knee_out, knee_up, foot_up, foot_scale): side is -1 or 1,
    knee_out pushes the knee sideways (a crouch bends the knees out), knee_up and
    foot_up lift them (a step), foot_scale grows or shrinks the foot (a foot
    coming toward you looks bigger)."""
    sx, sy = squash
    canvas = Image.new("RGBA", (WORK, WORK), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    pelvis = (HIP[0] + dx, PELVIS_Y + dy)
    for side, knee_out, knee_up, foot_up, foot_scale in legs:
        hip = (pelvis[0] + side * LEG_GAP, pelvis[1])
        ground = GROUND - foot_up
        knee = (hip[0] + side * (8 + knee_out), (hip[1] + ground) / 2 - knee_up)
        ankle = (hip[0] + side * 12, ground)
        stroke(draw, [hip, knee, ankle])
        foot(draw, ankle[0], ankle[1], foot_scale)
    # the trunk from the cut body down to the pelvis, then the body on top
    draw.line([(HIP[0] + dx, CUT_Y * sy + (1 - sy) * CUT_Y - 40 + dy), pelvis], fill=GREEN, width=WIDTH)
    draw.line([(pelvis[0] - LEG_GAP, pelvis[1]), (pelvis[0] + LEG_GAP, pelvis[1])], fill=GREEN, width=WIDTH)
    w, h = round(WORK * sx), round(WORK * sy)
    squashed = base.resize((w, h), Image.LANCZOS)
    # squashing keeps the trunk's cut line where it was, so the body sits on its legs
    canvas.alpha_composite(squashed, (round((WORK - w) / 2 + dx), round(CUT_Y - CUT_Y * sy + dy)))
    return canvas.resize((FRAME, FRAME), Image.LANCZOS)


def walk_toward(base: Image.Image, i: int, toward_you: bool) -> Image.Image:
    phase = 2 * pi * i / FRAMES
    legs = []
    for side, offset in ((-1, 0.0), (1, pi)):
        lift = max(0.0, sin(phase + offset))
        # a foot swinging toward you grows a little; one swinging away shrinks
        scale = 1 + (0.3 if toward_you else -0.3) * lift
        legs.append((side, 20 * lift, 44 * lift, 100 * lift, scale))
    # he sways over whichever foot is planted and bobs as each one passes
    return pose(base, dx=10 * sin(phase), dy=-10 * cos(2 * phase) - 6, legs=legs)


JUMP = [
    # stand, crouch, deep crouch, spring (stretched, toes down), tuck (in the air)
    # the actual height of the hop comes from the app moving him, so these only
    # shift him a little (more and the cloud ran off the top of the frame)
    dict(dy=0, squash=(1.0, 1.0), knees=(0, 0, 0, 1.0)),
    dict(dy=36, squash=(1.04, 0.95), knees=(40, 0, 0, 1.05)),
    dict(dy=72, squash=(1.08, 0.89), knees=(72, 0, 0, 1.1)),
    dict(dy=-4, squash=(0.96, 1.02), knees=(0, -10, -6, 0.7)),
    dict(dy=-16, squash=(1.0, 1.0), knees=(30, 34, 80, 0.9)),
]


def jump(base: Image.Image, i: int) -> Image.Image:
    f = JUMP[i]
    knee_out, knee_up, foot_up, scale = f["knees"]
    # feet stay planted while he crouches, so the legs fold rather than shorten
    legs = [(side, knee_out, knee_up, foot_up, scale) for side in (-1, 1)]
    return pose(base, dy=f["dy"], squash=f["squash"], legs=legs)


def write(name: str, frames: list[Image.Image]):
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, im in enumerate(frames):
        sheet.alpha_composite(im, (i * FRAME, 0))
    sheet.save(BRAND / name)
    print(f"wrote {name} ({len(frames)} frames of {FRAME} px)")


def main():
    front, back = body(), body(back=True)
    write("walk-sheet.png", [frame(front, i) for i in range(FRAMES)])
    write("walk-front.png", [walk_toward(front, i, True) for i in range(FRAMES)])
    write("walk-back.png", [walk_toward(back, i, False) for i in range(FRAMES)])
    write("jump-front.png", [jump(front, i) for i in range(len(JUMP))])
    write("jump-back.png", [jump(back, i) for i in range(len(JUMP))])


if __name__ == "__main__":
    main()
