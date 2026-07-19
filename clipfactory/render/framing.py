"""Podcast-aware vertical reframing.

Single-speaker mode keeps a smooth face crop with snap cooldown.
Two-speaker interview layouts (faces clustered left/right) use a stacked
9:16 split so both people stay fully framed instead of ping-pong cropping
half-faces or the table.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..ffmpeg_bin import ffmpeg_bin


def cut_segment(source: Path, start: float, end: float, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{max(0.1, end - start):.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(target),
        ],
        check=True,
    )


def _detect_layout(cut_path: Path) -> tuple[str, tuple[float, float] | None]:
    """Return ('dual'|'single'|'center', optional (left_x_ratio, right_x_ratio))."""
    import cv2

    cap = cv2.VideoCapture(str(cut_path))
    if not cap.isOpened():
        return "center", None
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or 1
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    left_xs: list[float] = []
    right_xs: list[float] = []
    samples = 0
    dual_frames = 0
    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # Sample ~3 fps equivalent for speed.
        if frame_index % 10 != 0:
            frame_index += 1
            continue
        frame_index += 1
        samples += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        if len(faces) == 0:
            continue
        centers = sorted(((x + w / 2) / width, w * h) for x, y, w, h in faces)
        if len(centers) >= 2:
            # Keep two largest faces.
            top = sorted(centers, key=lambda item: item[1], reverse=True)[:2]
            top = sorted(top, key=lambda item: item[0])
            if top[1][0] - top[0][0] >= 0.18:
                dual_frames += 1
                left_xs.append(top[0][0])
                right_xs.append(top[1][0])
        else:
            # Track which half the solo face lives in for later.
            pass
    cap.release()
    if samples == 0:
        return "center", None
    if dual_frames / samples >= 0.35 and left_xs and right_xs:
        return "dual", (sum(left_xs) / len(left_xs), sum(right_xs) / len(right_xs))
    return "single", None


def _render_dual_stack(cut_path: Path, left_x: float, right_x: float, out_path: Path) -> None:
    """Stack left-speaker crop on top and right-speaker crop on bottom → 1080x1920."""
    # Each panel is 1080x960. Crop a 9:8 window around each speaker x, then scale.
    filter_complex = (
        f"[0:v]split=2[left][right];"
        f"[left]crop=w='min(iw\\,ih*9/8)':h='min(ih\\,iw*8/9)':"
        f"x='max(0\\,min(iw-ow\\,{left_x}*iw-ow/2))':y='(ih-oh)/2',"
        f"scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top];"
        f"[right]crop=w='min(iw\\,ih*9/8)':h='min(ih\\,iw*8/9)':"
        f"x='max(0\\,min(iw-ow\\,{right_x}*iw-ow/2))':y='(ih-oh)/2',"
        f"scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bot];"
        f"[top][bot]vstack=inputs=2,format=yuv420p[v]"
    )
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(cut_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ],
        check=True,
    )


def _render_single_tracked(cut_path: Path, out_path: Path) -> None:
    """OpenCV face track with snap cooldown — avoids thrashing between host/guest."""
    import cv2

    cap = cv2.VideoCapture(str(cut_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open {cut_path}")
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    target_ratio = 9 / 16
    if target_ratio < src_w / max(src_h, 1):
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    silent = str(out_path) + ".silent.mp4"
    writer = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), fps, (crop_w, crop_h))

    center_x = src_w / 2
    smoothing = 0.12
    snap_cooldown = 0
    locked_side: str | None = None  # 'left' | 'right' | None

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = list(cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)))
        if faces and snap_cooldown <= 0:
            # Prefer the largest face, but avoid jumping across the frame unless
            # the new face is substantially larger for a sustained switch.
            faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
            best = faces_sorted[0]
            bx, by, bw, bh = best
            bcx = bx + bw / 2
            side = "left" if bcx < src_w / 2 else "right"
            if locked_side is None:
                locked_side = side
                center_x = bcx
            elif side == locked_side:
                center_x = center_x * (1 - smoothing) + bcx * smoothing
            else:
                # Only switch sides if the challenger is clearly the active speaker.
                if bw * bh >= 1.35 * (faces_sorted[1][2] * faces_sorted[1][3] if len(faces_sorted) > 1 else 0) or bw * bh > (src_w * src_h) * 0.04:
                    locked_side = side
                    center_x = bcx
                    snap_cooldown = int(fps * 0.7)  # hold ~0.7s after a switch
        elif faces and snap_cooldown > 0:
            # During cooldown, only update if face is on the locked side.
            same_side = [f for f in faces if (("left" if (f[0] + f[2] / 2) < src_w / 2 else "right") == locked_side)]
            if same_side:
                x, y, w, h = max(same_side, key=lambda f: f[2] * f[3])
                center_x = center_x * (1 - smoothing) + (x + w / 2) * smoothing
        if snap_cooldown > 0:
            snap_cooldown -= 1

        x0 = int(max(0, min(src_w - crop_w, center_x - crop_w / 2)))
        y0 = int(max(0, min(src_h - crop_h, (src_h - crop_h) / 2)))
        writer.write(frame[y0 : y0 + crop_h, x0 : x0 + crop_w])

    cap.release()
    writer.release()
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            silent,
            "-i",
            str(cut_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-shortest",
            str(out_path),
        ],
        check=True,
    )
    os.remove(silent)


def reframe_podcast_clip(source: Path, start: float, end: float, output: Path) -> str:
    """Cut + reframe. Returns layout mode used: dual|single|center."""
    output.parent.mkdir(parents=True, exist_ok=True)
    cut = output.with_suffix(".cut.mp4")
    try:
        cut_segment(source, start, end, cut)
        mode, anchors = _detect_layout(cut)
        if mode == "dual" and anchors:
            _render_dual_stack(cut, anchors[0], anchors[1], output)
            return "dual"
        if mode == "single":
            _render_single_tracked(cut, output)
            # Normalize to exact 1080x1920
            normalized = output.with_suffix(".norm.mp4")
            subprocess.run(
                [
                    ffmpeg_bin(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(output),
                    "-vf",
                    "scale=1080:1920",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(normalized),
                ],
                check=True,
            )
            normalized.replace(output)
            return "single"
        # Center crop fallback via ffmpeg
        vf = (
            "crop='if(gte(iw/ih,9/16),ih*9/16,iw)':'if(gte(iw/ih,9/16),ih,iw*16/9)':"
            "(iw-ow)/2:(ih-oh)/2,scale=1080:1920"
        )
        subprocess.run(
            [
                ffmpeg_bin(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(cut),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(output),
            ],
            check=True,
        )
        return "center"
    finally:
        cut.unlink(missing_ok=True)
