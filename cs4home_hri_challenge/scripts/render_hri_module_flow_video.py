#!/usr/bin/env python3
"""Render a minimal HRI Challenge cognitive-module flow animation."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION_SECONDS = 15
MODULES = [
    "Greeting Guest",
    "Introduce Guest",
    "Find Seat",
    "Grab Bag",
    "Transport Bag",
]
RECOVERY_MODULE = "Recovery"
MODULE_IO = {
    "Greeting Guest": {
        "afferent": "start\nperson\nspeech",
        "efferent": "done\nstatus",
    },
    "Introduce Guest": {
        "afferent": "start\nguest\ninfo",
        "efferent": "done\nstatus",
    },
    "Find Seat": {
        "afferent": "start\nseat\nmap",
        "efferent": "done\nstatus",
    },
    "Grab Bag": {
        "afferent": "start\nbag\ndetect",
        "efferent": "done\nstatus",
    },
    "Transport Bag": {
        "afferent": "start\nfollow\ntarget",
        "efferent": "done\nstatus",
    },
    "Recovery": {
        "afferent": "failure\nevent",
        "efferent": "restart\nresume",
    },
}

BACKGROUND = (255, 255, 255)
INK = (15, 23, 42)
MUTED = (100, 116, 139)
BOX_FILL = (255, 255, 255)
BOX_EDGE = (55, 65, 81)
ACTIVE = (255, 146, 39)
ACTIVE_FILL = (255, 247, 237)
DONE = (34, 197, 94)
LINE_BASE = (203, 213, 225)
FAILURE = (239, 68, 68)
FAILURE_FILL = (254, 226, 226)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in [
        Path("/usr/share/fonts/truetype/dejavu") / name,
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ]:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


TITLE_FONT = font(52, True)
SUBTITLE_FONT = font(26)
LABEL_FONT = font(22, True)
PART_FONT = font(17, True)
PART_VALUE_FONT = font(15)
IO_FONT = font(12)
SMALL_FONT = font(20)


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def rounded_box(draw: ImageDraw.ImageDraw, rect, radius, fill, outline, width):
    draw.rounded_rectangle(rect, radius=radius, fill=fill, outline=outline, width=width)


def text_center(draw: ImageDraw.ImageDraw, xy, text: str, font_obj, fill):
    lines = text.split("\n")
    line_boxes = [draw.textbbox((0, 0), line, font=font_obj) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    total_height = sum(line_heights) + 10 * (len(lines) - 1)
    y = xy[1] - total_height / 2
    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        draw.text((xy[0] - line_width / 2, y), line, font=font_obj, fill=fill)
        y += line_height + 10


def text_box(draw: ImageDraw.ImageDraw, rect, text: str, font_obj, fill):
    if not text:
        return
    x0, y0, x1, y1 = rect
    lines = text.split("\n")
    line_boxes = [draw.textbbox((0, 0), line, font=font_obj) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    total_height = sum(line_heights) + 4 * (len(lines) - 1)
    y = y0 + (y1 - y0 - total_height) / 2
    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        draw.text((x0 + (x1 - x0 - line_width) / 2, y), line, font=font_obj, fill=fill)
        y += line_height + 4


def line_point(a, b, progress: float):
    progress = max(0.0, min(1.0, progress))
    return (a[0] + (b[0] - a[0]) * progress, a[1] + (b[1] - a[1]) * progress)


def draw_dashed_polyline(draw: ImageDraw.ImageDraw, points, fill, width, dash=12, gap=8):
    for start, end in zip(points, points[1:]):
        draw_dashed_line(draw, start, end, fill, width, dash, gap)


def rounded_rect_path(rect, radius, samples=14):
    x0, y0, x1, y1 = rect
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    points = []
    points.extend([(x, y0) for x in np.linspace(x0 + r, x1 - r, samples)])
    for angle in np.linspace(-90, 0, samples):
        rad = math.radians(angle)
        points.append((x1 - r + r * math.cos(rad), y0 + r + r * math.sin(rad)))
    points.extend([(x1, y) for y in np.linspace(y0 + r, y1 - r, samples)])
    for angle in np.linspace(0, 90, samples):
        rad = math.radians(angle)
        points.append((x1 - r + r * math.cos(rad), y1 - r + r * math.sin(rad)))
    points.extend([(x, y1) for x in np.linspace(x1 - r, x0 + r, samples)])
    for angle in np.linspace(90, 180, samples):
        rad = math.radians(angle)
        points.append((x0 + r + r * math.cos(rad), y1 - r + r * math.sin(rad)))
    points.extend([(x0, y) for y in np.linspace(y1 - r, y0 + r, samples)])
    for angle in np.linspace(180, 270, samples):
        rad = math.radians(angle)
        points.append((x0 + r + r * math.cos(rad), y0 + r + r * math.sin(rad)))
    points.append(points[0])
    return points


def draw_dashed_rounded_rect(draw, rect, radius, fill, outline, width):
    draw.rounded_rectangle(rect, radius=radius, fill=fill)
    draw_dashed_polyline(draw, rounded_rect_path(rect, radius), outline, width, dash=8, gap=7)


def draw_dashed_line(draw: ImageDraw.ImageDraw, a, b, fill, width, dash=18, gap=12):
    length = math.dist(a, b)
    if length == 0:
        return
    dx = (b[0] - a[0]) / length
    dy = (b[1] - a[1]) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        draw.line(
            [(a[0] + dx * pos, a[1] + dy * pos), (a[0] + dx * end, a[1] + dy * end)],
            fill=fill,
            width=width,
        )
        pos += dash + gap


def bezier(points, steps=90):
    curve = []
    n = len(points) - 1
    for i in range(steps + 1):
        t = i / steps
        x = 0.0
        y = 0.0
        for k, point in enumerate(points):
            coeff = math.comb(n, k) * ((1 - t) ** (n - k)) * (t ** k)
            x += coeff * point[0]
            y += coeff * point[1]
        curve.append((x, y))
    return curve


def straight(a, b, steps=40):
    return [line_point(a, b, i / steps) for i in range(steps + 1)]


def path_until(points, progress: float):
    lengths = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(lengths)
    remaining = max(0.0, min(1.0, progress)) * total
    drawn = [points[0]]
    for idx, segment_length in enumerate(lengths):
        start = points[idx]
        end = points[idx + 1]
        if remaining >= segment_length:
            drawn.append(end)
            remaining -= segment_length
        else:
            if remaining > 0:
                drawn.append(line_point(start, end, remaining / segment_length))
            break
    return drawn


def draw_module(draw, rect, title, index, state, recovery=False):
    active = state == "active"
    done = state == "done"
    fill = FAILURE_FILL if recovery and active else ACTIVE_FILL if active else BOX_FILL
    outline = FAILURE if recovery and active else ACTIVE if active else DONE if done else BOX_EDGE
    width = 4 if active else 3

    x0, y0, x1, y1 = rect
    draw_dashed_rounded_rect(draw, rect, 26, fill, outline, width)

    title_fill = MUTED if state == "idle" else INK
    draw.text((x0 + 22, y0 + 18), title, font=LABEL_FONT, fill=title_fill)

    margin = 18
    meta = (x0 + margin, y0 + 58, x1 - margin, y0 + 92)
    core = (x0 + margin, y0 + 106, x1 - margin, y0 + 188)
    coupling = (x0 + margin, y1 - 50, x1 - margin, y1 - 16)
    for section, label in [(meta, "Meta"), (core, "Core"), (coupling, "Coupling")]:
        rounded_box(draw, section, 8, BOX_FILL, BOX_EDGE, 2)
        text_center(draw, ((section[0] + section[2]) / 2, (section[1] + section[3]) / 2), label, PART_FONT, MUTED if label != "Core" else INK)

    aff = (x0 + 2, core[1] + 22, x0 + 84, core[1] + 58)
    eff = (x1 - 84, core[1] + 22, x1 - 2, core[1] + 58)
    aff_content = MODULE_IO.get(title, {}).get("afferent", "")
    eff_content = MODULE_IO.get(title, {}).get("efferent", "")
    rounded_box(draw, aff, 6, BOX_FILL, BOX_EDGE, 2)
    rounded_box(draw, eff, 6, BOX_FILL, BOX_EDGE, 2)
    text_box(draw, aff, aff_content or "afferent", IO_FONT, INK)
    text_box(draw, eff, eff_content or "efferent", IO_FONT, INK)
    cy = (aff[1] + aff[3]) / 2
    draw.line([(aff[2], cy), (core[0] + 58, cy)], fill=BOX_EDGE, width=2)
    draw.polygon([(core[0] + 58, cy), (core[0] + 49, cy - 5), (core[0] + 49, cy + 5)], fill=BOX_EDGE)
    draw.line([(core[2] - 58, cy), (eff[0], cy)], fill=BOX_EDGE, width=2)
    draw.polygon([(eff[0], cy), (eff[0] - 9, cy - 5), (eff[0] - 9, cy + 5)], fill=BOX_EDGE)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data" / "hri_module_flow_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_video = out_dir / "hri_cognitive_module_flow_raw.mp4"
    final_video = out_dir / "hri_cognitive_module_flow.mp4"

    centers = [(250, 405), (745, 405), (1240, 405), (640, 735), (1135, 735)]
    box_w, box_h = 430, 230
    recovery_center = (1635, 735)
    recovery_rect = (
        recovery_center[0] - 215,
        recovery_center[1] - 115,
        recovery_center[0] + 215,
        recovery_center[1] + 115,
    )
    flow_points = []
    for segment in [
        straight((20, 350), (1240, 350), steps=130),
        bezier([(1240, 350), (1480, 470), (1030, 675), (640, 675)], steps=90),
        straight((640, 675), (1135, 675), steps=60),
    ]:
        flow_points.extend(segment if not flow_points else segment[1:])
    module_flow_positions = [0.08, 0.29, 0.50, 0.78, 0.93]
    failure_module_index = 4
    failure_points = bezier([(1135, 675), (1300, 570), (1490, 610), (1545, 625)], steps=80)
    total_frames = FPS * DURATION_SECONDS
    writer = cv2.VideoWriter(str(raw_video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))

    for frame in range(total_frames):
        progress = ease_in_out(frame / (total_frames - 1))
        intro_progress = max(0.0, (progress - 0.12) / 0.88)
        active_flow = path_until(flow_points, intro_progress)
        cursor = active_flow[-1]
        reached_index = -1
        for idx, module_progress in enumerate(module_flow_positions):
            if intro_progress >= module_progress:
                reached_index = idx
        recovery_progress = 0.0
        if intro_progress >= module_flow_positions[failure_module_index]:
            recovery_progress = ease_in_out(
                (intro_progress - module_flow_positions[failure_module_index]) /
                (1.0 - module_flow_positions[failure_module_index])
            )
        recovery_active = recovery_progress > 0.45

        image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        draw = ImageDraw.Draw(image)

        draw.text((110, 80), "HRI Challenge Cognitive Modules", font=TITLE_FONT, fill=INK)
        draw.text(
            (112, 149),
            "Modular architecture with recovery supervision",
            font=SUBTITLE_FONT,
            fill=MUTED,
        )

        show_architecture = progress > 0.1

        if show_architecture:
            for idx, (label, center) in enumerate(zip(MODULES, centers)):
                x, y = center
                rect = (x - box_w / 2, y - box_h / 2, x + box_w / 2, y + box_h / 2)
                state = "active" if idx == reached_index else "done" if module_flow_positions[idx] < intro_progress else "idle"
                draw_module(draw, rect, label, idx, state)

            draw_module(draw, recovery_rect, RECOVERY_MODULE, 0, "active" if recovery_active else "idle", recovery=True)

            if len(active_flow) > 1:
                draw.line(active_flow, fill=ACTIVE, width=9)
            pulse = 10 + 5 * math.sin(frame * 0.24)
            draw.ellipse((cursor[0] - pulse, cursor[1] - pulse, cursor[0] + pulse, cursor[1] + pulse), fill=ACTIVE)

            if recovery_progress > 0:
                failure_active = path_until(failure_points, recovery_progress)
                draw.line(failure_active, fill=FAILURE, width=7)
                branch_cursor = failure_active[-1]
                draw.ellipse((branch_cursor[0] - 9, branch_cursor[1] - 9, branch_cursor[0] + 9, branch_cursor[1] + 9), fill=FAILURE)
        frame_bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)

    writer.release()

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_video),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(final_video),
        ],
        check=True,
    )
    raw_video.unlink(missing_ok=True)
    print(final_video)


if __name__ == "__main__":
    main()
