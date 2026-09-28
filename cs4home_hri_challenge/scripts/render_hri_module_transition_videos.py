#!/usr/bin/env python3
"""Render short per-module transition clips from the HRI cognitive-module diagram."""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from render_hri_module_flow_video import (
    ACTIVE,
    BACKGROUND,
    FAILURE,
    FPS,
    HEIGHT,
    INK,
    MODULES,
    MUTED,
    RECOVERY_MODULE,
    SUBTITLE_FONT,
    TITLE_FONT,
    WIDTH,
    bezier,
    draw_module,
    ease_in_out,
    path_until,
    straight,
)


DURATION_SECONDS = 4
BOX_W = 430
BOX_H = 230
MODULE_CENTERS = [(250, 405), (745, 405), (1240, 405), (640, 735), (1135, 735)]
RECOVERY_CENTER = (1635, 735)
OUTPUTS = {
    "Greeting Guest": "hri_transition_greeting_guest.mp4",
    "Find Seat": "hri_transition_find_seat.mp4",
    "Grab Bag": "hri_transition_grab_bag.mp4",
    "Recovery": "hri_transition_recovery.mp4",
}


def module_rect(center):
    x, y = center
    return (x - BOX_W / 2, y - BOX_H / 2, x + BOX_W / 2, y + BOX_H / 2)


def rgba(color, alpha):
    return (*color, int(max(0, min(255, alpha))))


def draw_polyline_alpha(image: Image.Image, points, color, width, alpha):
    layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(layer)
    draw.line(points, fill=rgba(color, alpha), width=width)
    image.alpha_composite(layer)


def draw_base(image: Image.Image, selected: str, pulse: float):
    draw = ImageDraw.Draw(image)

    draw.text((110, 80), "HRI Challenge Cognitive Modules", font=TITLE_FONT, fill=INK)
    draw.text(
        (112, 149),
        "Modular architecture with recovery supervision",
        font=SUBTITLE_FONT,
        fill=MUTED,
    )

    flow_points = []
    for segment in [
        straight((20, 350), (1240, 350), steps=130),
        bezier([(1240, 350), (1480, 470), (1030, 675), (640, 675)], steps=90),
        straight((640, 675), (1135, 675), steps=60),
    ]:
        flow_points.extend(segment if not flow_points else segment[1:])

    failure_points = bezier([(1135, 675), (1300, 570), (1490, 610), (1545, 625)], steps=80)
    if selected == RECOVERY_MODULE:
        draw_polyline_alpha(image, flow_points, ACTIVE, 7, 80)
        draw_polyline_alpha(image, failure_points, FAILURE, 9, int(145 + 90 * pulse))
    elif selected == "Grab Bag":
        grab_bag_arrival = 0.78
        draw_polyline_alpha(image, flow_points, ACTIVE, 6, 55)
        draw_polyline_alpha(image, path_until(flow_points, grab_bag_arrival * pulse), ACTIVE, 9, 185)
        draw_polyline_alpha(image, failure_points, FAILURE, 6, 35)
    else:
        draw_polyline_alpha(image, flow_points, ACTIVE, 8, 115)
        draw_polyline_alpha(image, failure_points, FAILURE, 6, 45)

    draw = ImageDraw.Draw(image)
    for label, center in zip(MODULES, MODULE_CENTERS):
        draw_module(draw, module_rect(center), label, 0, "idle")
    draw_module(draw, module_rect(RECOVERY_CENTER), RECOVERY_MODULE, 0, "idle", recovery=True)


def draw_dim_overlay(image: Image.Image, selected: str):
    layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(layer)
    for label, center in [*zip(MODULES, MODULE_CENTERS), (RECOVERY_MODULE, RECOVERY_CENTER)]:
        if label == selected:
            continue
        x0, y0, x1, y1 = module_rect(center)
        draw.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y1 + 5), radius=30, fill=(255, 255, 255, 118))
    image.alpha_composite(layer)


def draw_highlight(image: Image.Image, selected: str, pulse: float):
    layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(layer)
    rect = module_rect(RECOVERY_CENTER if selected == RECOVERY_MODULE else MODULE_CENTERS[MODULES.index(selected)])
    draw_module(draw, rect, selected, 0, "active", recovery=selected == RECOVERY_MODULE)
    opacity = (80 + 175 * pulse) / 255.0
    alpha = layer.getchannel("A").point(lambda value: int(value * opacity))
    layer.putalpha(alpha)
    image.alpha_composite(layer)


def render_video(selected: str, out_path: Path):
    raw_path = out_path.with_name(out_path.stem + "_raw.mp4")
    total_frames = FPS * DURATION_SECONDS
    writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))

    for frame in range(total_frames):
        progress = frame / (total_frames - 1)
        pulse = ease_in_out(progress)
        shimmer = 0.5 + 0.5 * np.sin(progress * np.pi * 2.0)
        emphasis = max(pulse, 0.72 + 0.18 * shimmer)

        image = Image.new("RGBA", (WIDTH, HEIGHT), (*BACKGROUND, 255))
        draw_base(image, selected, emphasis)
        draw_dim_overlay(image, selected)
        draw_highlight(image, selected, emphasis)

        frame_bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
        writer.write(frame_bgr)

    writer.release()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out_path),
        ],
        check=True,
    )
    raw_path.unlink(missing_ok=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data" / "hri_module_flow_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    for selected, filename in OUTPUTS.items():
        render_video(selected, out_dir / filename)
        print(out_dir / filename)


if __name__ == "__main__":
    main()
