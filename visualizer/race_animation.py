"""
F1 race spaghetti-chart animation.

X axis design
─────────────
  x_min = 0 always (race origin, fixed left edge)
  x_max = leader's total_distance, smoothed (grows from 0 → finish_distance)
  scale = NON-LINEAR power transform so the near-leader zone is visually
          expanded; leader alone is at far right, and every other car is
          pulled measurably away from it.

  bar_frac = 1 – (gap_frac) ^ X_POWER   where gap_frac = 1 – dist/x_max

History lines
─────────────
  Each car accumulates (total_distance, y_pixel) points.  At render time
  total_distance is re-projected through the current x scale, so as x_max
  grows the older history naturally compresses toward the left.

Lap markers + finish flag
─────────────────────────
  Leader's lap transitions are detected online; the total_distance at each
  lap boundary is recorded and drawn as a thin vertical line with a label.
  The checkered finish flag uses the same sliding-in mechanic: only visible
  once x_max has grown past finish_distance.

Outro (end sequence)
─────────────────────
  After live data ends, all cars move at the same constant speed toward
  finish_distance, so cars that were further ahead arrive first.  History
  trails extend frame-by-frame so there is no visual break.

Output: mp4 via ffmpeg subprocess (ffmpeg must be on PATH).
"""
import os
import subprocess
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# ── team palette ─────────────────────────────────────────────────────────────

TEAM_COLOURS: Dict[int, tuple] = {
    0: (0, 210, 190),    # Mercedes
    1: (220, 0, 0),      # Ferrari
    2: (54, 113, 198),   # Red Bull
    3: (0, 90, 255),     # Williams
    4: (0, 111, 98),     # Aston Martin
    5: (255, 135, 188),  # Alpine
    6: (100, 146, 255),  # Racing Bulls
    7: (182, 186, 189),  # Haas
    8: (255, 128, 0),    # McLaren
    9: (0, 207, 70),     # Kick Sauber
}
DEFAULT_COLOUR = (150, 150, 150)

TEAM_NAMES: Dict[int, str] = {
    0: "Mercedes",    1: "Ferrari",   2: "Red Bull", 3: "Williams",
    4: "Aston Martin",5: "Alpine",    6: "RB",       7: "Haas",
    8: "McLaren",     9: "Kick Sauber",
}

# ── canvas ───────────────────────────────────────────────────────────────────

W, H = 1280, 720
FPS = 30
TARGET_FRAMES = FPS * 20          # 600 frames ≈ 20 s

HEADER_H   = 72
FOOTER_H   = 44
LEFT_W     = 178                  # team name column
LINE_AREA  = 840                  # x-axis pixel width
ICON_SIZE  = 28

X_POWER = 0.40

ALPHA_X    = 0.08
ALPHA_Y    = 0.18
ALPHA_DIST = 0.15

OUTRO_S = 3

# Colours
BG        = (10, 10, 22)
STRIPE    = (16, 16, 32)
TEXT      = (238, 238, 255)
DIM       = (95, 95, 122)
GOLD      = (255, 200, 50)
SC_COL    = (255, 210, 0)
GRID      = (28, 28, 50)
LAP_LINE  = (40, 40, 65)
WARN_COL  = (255, 200, 0)
PEN_COL   = (220, 60, 60)
PIT_COL   = (0, 180, 255)
HIST_DIM  = 0.60

SC_LABELS = {1: "SAFETY CAR", 2: "VIRTUAL SC", 3: "SC ENDING"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _dim(c: tuple, f: float) -> tuple:
    return tuple(int(x * f) for x in c)


def _blend(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _draw_checkered_flag(draw: ImageDraw.Draw,
                         x: int, y_top: int, y_bottom: int,
                         sq: int = 7, cols: int = 2) -> None:
    n_rows = (y_bottom - y_top) // sq
    for row in range(n_rows):
        for col in range(cols):
            black = (row + col) % 2 == 0
            fill = (0, 0, 0) if black else (240, 240, 240)
            x0 = x + col * sq
            y0 = y_top + row * sq
            draw.rectangle([x0, y0, x0 + sq - 1, y0 + sq - 1], fill=fill)


def _dist_to_x(dist: float, x_max: float) -> float:
    if x_max <= 0:
        return float(LEFT_W)
    rel = max(0.0, min(1.0, dist / x_max))
    gap = 1.0 - rel
    return LEFT_W + (1.0 - gap ** X_POWER) * LINE_AREA


def _fmt_gap(ms: int) -> str:
    s = ms / 1000.0
    if s < 60:
        return f"+{s:.1f}s"
    return f"+{int(s // 60)}:{s % 60:04.1f}s"


def _lookup_sc(sc_timeline: List[Tuple[float, int]], t: float) -> int:
    """Return the most recent safety_car_status at or before time t."""
    status = 0
    for ts, st in sc_timeline:
        if ts <= t:
            status = st
        else:
            break
    return status


# ── car icon ─────────────────────────────────────────────────────────────────

def _draw_car_icon(
    draw: ImageDraw.Draw,
    x_tip: float,
    yc: float,
    colour: tuple,
    size: int = 28,
) -> None:
    s = size
    x0 = x_tip - s
    bw, bh = s * 0.68, s * 0.27
    bx0, bx1 = x0 + s * 0.06, x0 + s * 0.06 + bw

    draw.rounded_rectangle([bx0, yc - bh/2, bx1, yc + bh/2],
                            radius=int(bh * 0.45), fill=colour)
    draw.polygon([(bx1, yc - bh*0.42), (bx1, yc + bh*0.42), (x_tip, yc)],
                 fill=colour)

    wing = _blend(colour, (255, 255, 255), 0.35)
    fw_x = bx1 - s * 0.05
    draw.rectangle([fw_x, yc - s*0.29, fw_x + 2, yc + s*0.29], fill=wing)
    rw_x = bx0 + s * 0.04
    draw.rectangle([rw_x - 2, yc - s*0.35, rw_x + 2, yc + s*0.35], fill=wing)

    wc = (18, 18, 18)
    ww, wh = s*0.11, s*0.21
    for wx_frac in (0.62, 0.24):
        wx = x0 + wx_frac * s
        for sign in (-1.0, 1.0):
            wy = yc + sign * (bh/2 + wh*0.25)
            draw.ellipse([wx - ww/2, wy - wh/2, wx + ww/2, wy + wh/2], fill=wc)

    halo = _blend(colour, (50, 50, 70), 0.55)
    draw.arc([bx0 + bw*0.18, yc - bh*0.5 + 2, bx0 + bw*0.72, yc + bh*0.5 - 2],
             start=185, end=355, fill=halo, width=2)


# ── frame renderer ────────────────────────────────────────────────────────────

def _render_frame(
    cars: List[Dict],
    y_pos: Dict[int, float],
    history: Dict[int, List[Tuple[float, float]]],
    car_meta: Dict[int, Dict],
    lap_boundary_dists: Dict[int, float],
    finish_distance: float,
    x_max: float,
    lap: int,
    total_laps: int,
    race_time: float,
    fonts: tuple,
    sc_status: int,   # 0=none 1=SC 2=VSC 3=SC ending
    n_cars: int,
    frame_idx: int,
    pit_markers: Dict[int, List[Tuple[float, float]]] = None,
) -> Image.Image:
    font_hd, font_md, font_sm, font_xs = fonts

    # Safety car: flash header background on even blink ticks
    sc_blink = sc_status > 0 and (frame_idx // 12) % 2 == 0

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    content_h = H - HEADER_H - FOOTER_H
    row_h = content_h / max(n_cars, 1)
    icon_sz = max(16, min(ICON_SIZE, int(row_h * 0.70)))

    # Alternating row stripes
    for i in range(n_cars):
        if i % 2 == 1:
            ry = HEADER_H + i * row_h
            draw.rectangle([0, ry, W, ry + row_h], fill=STRIPE)

    # Lap boundary markers
    for lap_n, lap_dist in lap_boundary_dists.items():
        if lap_n < 1 or lap_dist <= 0:
            continue
        lx = int(_dist_to_x(lap_dist, x_max))
        if LEFT_W < lx < LEFT_W + LINE_AREA:
            draw.line([(lx, HEADER_H), (lx, H - FOOTER_H)], fill=LAP_LINE, width=1)
            draw.text((lx, H - FOOTER_H + 4), f"L{lap_n}",
                      fill=DIM, font=font_xs, anchor="mt")

    draw.line([(0, HEADER_H - 1), (W, HEADER_H - 1)], fill=GRID, width=2)
    draw.line([(0, H - FOOTER_H), (W, H - FOOTER_H)], fill=GRID, width=1)

    # Checkered finish flag — slides in from right like lap markers
    if x_max > 0 and finish_distance > 0 and finish_distance <= x_max:
        flag_x = int(_dist_to_x(finish_distance, x_max))
        if LEFT_W <= flag_x <= LEFT_W + LINE_AREA:
            _draw_checkered_flag(draw, flag_x, HEADER_H, H - FOOTER_H)

    # History polylines
    for idx, hist in history.items():
        if len(hist) < 2:
            continue
        colour = car_meta.get(idx, {}).get("colour", DEFAULT_COLOUR)
        hc = _dim(colour, HIST_DIM)
        step = max(1, len(hist) // 300)
        pts_raw = hist[::step]
        if pts_raw[-1] != hist[-1]:
            pts_raw = pts_raw + [hist[-1]]
        pts = [(int(_dist_to_x(d, x_max)), int(y)) for d, y in pts_raw]
        draw.line(pts, fill=hc, width=2)

    # Pit history markers — small blue circle with "P" on the trail
    if pit_markers:
        for idx, marks in pit_markers.items():
            for dist, y in marks:
                mx = int(_dist_to_x(dist, x_max))
                if LEFT_W <= mx <= LEFT_W + LINE_AREA:
                    r = 6
                    draw.ellipse([mx - r, int(y) - r, mx + r, int(y) + r],
                                 fill=PIT_COL, outline=(200, 240, 255))
                    draw.text((mx, y), "P", fill=(10, 10, 22),
                              font=fonts[3], anchor="mm")

    # Car icons + labels
    for car in cars:
        idx = car["car_index"]
        yc = y_pos.get(idx)
        if yc is None:
            continue

        meta    = car_meta.get(idx, {})
        colour  = meta.get("colour", DEFAULT_COLOUR)
        name    = meta.get("name", "???")
        team_id = meta.get("team_id", -1)

        cx       = _dist_to_x(car["total_distance"], x_max)
        icon_tip = cx + icon_sz

        # ── pit status indicator (left of car) ────────────────────────────
        pit = car.get("pit_status", 0)
        if pit > 0:
            pit_label = "PIT" if pit == 1 else "BOX"
            pw = int(font_xs.getlength(pit_label)) + 6
            px0 = int(cx) - pw - 2
            if px0 > LEFT_W:
                draw.rectangle([px0, int(yc) - 8, px0 + pw, int(yc) + 8],
                                fill=PIT_COL, outline=PIT_COL)
                draw.text((px0 + 3, yc), pit_label,
                          fill=(10, 10, 22), font=font_xs, anchor="lm")

        # ── warning / penalty indicator (left of car, replaces pit if both) ─
        warnings = car.get("warnings", 0)
        penalties = car.get("penalties", 0)

        if penalties > 0:
            pen_label = f"{penalties}s"
            pw = int(font_xs.getlength(pen_label)) + 6
            px0 = int(cx) - pw - 2
            if px0 > LEFT_W:
                draw.rectangle([px0, int(yc) - 8, px0 + pw, int(yc) + 8],
                                fill=PEN_COL, outline=PEN_COL)
                draw.text((px0 + 3, yc), pen_label,
                          fill=(255, 255, 255), font=font_xs, anchor="lm")
        elif warnings > 0 and pit == 0:
            warn_label = "!"
            pw = int(font_xs.getlength(warn_label)) + 10
            px0 = int(cx) - pw - 2
            if px0 > LEFT_W:
                draw.rectangle([px0, int(yc) - 8, px0 + pw, int(yc) + 8],
                                fill=WARN_COL, outline=WARN_COL)
                draw.text((px0 + pw // 2, yc), warn_label,
                          fill=(10, 10, 22), font=font_md, anchor="mm")

        _draw_car_icon(draw, icon_tip, yc, colour, size=icon_sz)

        # Driver name
        text_x = icon_tip + 5
        if text_x < W - 20:
            draw.text((text_x, yc), name[:14], fill=TEXT, font=font_md, anchor="lm")

            # Gap to leader (non-P1 only)
            if car.get("car_position", 1) > 1:
                delta_ms = car.get("delta_to_leader_ms", 0)
                if delta_ms > 0:
                    gap_str = _fmt_gap(delta_ms)
                    name_w = int(font_md.getlength(name[:14]))
                    draw.text((text_x + name_w + 6, yc), gap_str,
                              fill=DIM, font=font_xs, anchor="lm")

        # Left column: rank + team name
        team_str = TEAM_NAMES.get(team_id, "???")
        draw.text((6, yc), f"P{car['car_position']}", fill=DIM, font=font_xs, anchor="lm")
        draw.text((38, yc), team_str[:12], fill=TEXT, font=font_sm, anchor="lm")

    # ── header ────────────────────────────────────────────────────────────────
    if sc_blink:
        draw.rectangle([0, 0, W, HEADER_H - 2], fill=(55, 44, 0))
    mins, secs = divmod(int(race_time), 60)
    draw.text((W // 2, HEADER_H // 2),
              f"LAP {lap} / {total_laps}    {mins}:{secs:02d}",
              fill=TEXT, font=font_hd, anchor="mm")
    if sc_status > 0:
        label = SC_LABELS.get(sc_status, "SAFETY CAR")
        draw.text((W - 14, HEADER_H // 2),
                  f"SC: {label}", fill=SC_COL, font=font_md, anchor="rm")

    # ── footer ────────────────────────────────────────────────────────────────
    draw.text((LEFT_W + LINE_AREA // 2, H - FOOTER_H // 2 + 8),
              f"← {x_max / 1000:.1f} km (non-linear scale) →",
              fill=DIM, font=font_xs, anchor="mm")

    return img


# ── ffmpeg ───────────────────────────────────────────────────────────────────

def _open_ffmpeg(out_path: str) -> subprocess.Popen:
    return subprocess.Popen(
        ["ffmpeg", "-y",
         "-f", "rawvideo", "-vcodec", "rawvideo",
         "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
         "-r", str(FPS), "-i", "pipe:0",
         "-vcodec", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "22", "-preset", "fast", "-movflags", "+faststart",
         out_path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


# ── public API ────────────────────────────────────────────────────────────────

def build_mp4(
    snapshots: List[Any],
    out_path: str,
    total_laps: int = 0,
    sc_timeline: Optional[List[Tuple[float, int]]] = None,
) -> None:
    """
    snapshots: list of dicts with at minimum:
        session_time, car_index, car_position, current_lap,
        total_distance, pit_status, name, team_id
    Optional per-car fields (added by recorder v2+):
        delta_to_leader_ms, warnings, penalties
    sc_timeline: sorted list of (session_time, safety_car_status) from
        Session packets (packet_id=1).  sc_status: 0=none 1=SC 2=VSC 3=ending
    """
    if not snapshots:
        raise ValueError("No snapshots to animate")

    by_time: Dict[float, Dict[int, Dict]] = defaultdict(dict)
    for s in snapshots:
        entry = dict(s) if not isinstance(s, dict) else s
        by_time[entry["session_time"]][entry["car_index"]] = entry

    times = sorted(by_time.keys())
    step = max(1, len(times) // TARGET_FRAMES)
    times = times[::step]
    if times[-1] != sorted(by_time.keys())[-1]:
        times.append(sorted(by_time.keys())[-1])

    sc_tl: List[Tuple[float, int]] = sorted(sc_timeline) if sc_timeline else []

    fonts = (_load_font(24), _load_font(14), _load_font(13), _load_font(11))

    n_cars = 0
    for t0 in times:
        bucket = list(by_time[t0].values())
        if bucket:
            n_cars = len(bucket)
            break

    content_h = H - HEADER_H - FOOTER_H
    row_h = content_h / max(n_cars, 1)

    def _target_y(rank: int) -> float:
        return HEADER_H + (rank + 0.5) * row_h

    # Pre-scan: lap boundaries + finish_distance
    lap_boundary_dists: Dict[int, float] = {}
    finish_distance: float = 0.0
    prev_lap = None
    for t in times:
        bucket = list(by_time[t].values())
        if not bucket:
            continue
        for car in bucket:
            d = float(car.get("total_distance", 0))
            if d > finish_distance:
                finish_distance = d
        leader = max(bucket, key=lambda c: c["total_distance"])
        lap_n = int(leader.get("current_lap", 1))
        if prev_lap is not None and lap_n != prev_lap and lap_n not in lap_boundary_dists:
            lap_boundary_dists[lap_n] = leader["total_distance"]
        prev_lap = lap_n

    y_pos:        Dict[int, float] = {}
    smooth_dist:  Dict[int, float] = {}
    x_max_cur:    Optional[float] = None
    history:      Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    pit_markers:  Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    prev_pit:     Dict[int, int] = {}
    car_meta:     Dict[int, Dict] = {}
    max_laps = total_laps
    last_cars: List[Dict] = []

    proc = _open_ffmpeg(out_path)
    frame_count = 0

    try:
        for t in times:
            cars_raw = list(by_time[t].values())
            if not cars_raw:
                continue

            cars = sorted(cars_raw, key=lambda c: c["total_distance"], reverse=True)
            last_cars = cars

            for car in cars:
                idx = car["car_index"]
                if idx not in car_meta:
                    car_meta[idx] = {
                        "colour":  TEAM_COLOURS.get(car.get("team_id", -1), DEFAULT_COLOUR),
                        "name":    car.get("name", "???"),
                        "team_id": car.get("team_id", -1),
                    }

            for rank, car in enumerate(cars):
                idx = car["car_index"]
                target = _target_y(rank)
                if idx not in y_pos:
                    y_pos[idx] = target
                else:
                    y_pos[idx] += ALPHA_Y * (target - y_pos[idx])

            for car in cars:
                idx = car["car_index"]
                raw = car["total_distance"]
                if idx not in smooth_dist:
                    smooth_dist[idx] = raw
                else:
                    smooth_dist[idx] += ALPHA_DIST * (raw - smooth_dist[idx])

            leader_dist = cars[0]["total_distance"]
            if x_max_cur is None:
                x_max_cur = leader_dist
            else:
                target_xmax = leader_dist * 1.015
                if target_xmax > x_max_cur:
                    x_max_cur += ALPHA_X * (target_xmax - x_max_cur)
                x_max_cur = max(x_max_cur, leader_dist)
            if finish_distance > 0:
                x_max_cur = min(x_max_cur, finish_distance)

            for car in cars:
                idx = car["car_index"]
                history[idx].append((smooth_dist[idx], y_pos[idx]))
                # Detect pit entry (pit_status 0 → 1) and record trail marker
                cur_pit = car.get("pit_status", 0)
                if prev_pit.get(idx, 0) == 0 and cur_pit == 1:
                    pit_markers[idx].append((smooth_dist[idx], y_pos[idx]))
                prev_pit[idx] = cur_pit

            lap = max((c["current_lap"] for c in cars), default=1)
            max_laps = max(max_laps, lap)

            cars_display = [dict(c, total_distance=smooth_dist.get(c["car_index"],
                                                                    c["total_distance"]))
                            for c in cars]

            img = _render_frame(
                cars_display, y_pos, history, car_meta,
                lap_boundary_dists, finish_distance, x_max_cur,
                lap, max_laps, t,
                fonts,
                sc_status=_lookup_sc(sc_tl, t),
                n_cars=n_cars,
                frame_idx=frame_count,
                pit_markers=pit_markers,
            )
            proc.stdin.write(img.tobytes())
            frame_count += 1

        # Outro: uniform speed toward finish_distance
        if x_max_cur is not None and last_cars:
            outro_smooth = dict(smooth_dist)
            outro_ypos   = dict(y_pos)
            outro_history: Dict[int, List[Tuple[float, float]]] = {
                idx: list(pts) for idx, pts in history.items()
            }

            max_gap = max(
                (finish_distance - d for d in outro_smooth.values()),
                default=0.0,
            )
            speed = max_gap / (FPS * OUTRO_S) if max_gap > 0 else 0.0

            for _fi in range(FPS * OUTRO_S):
                for idx in list(outro_smooth):
                    outro_smooth[idx] = min(outro_smooth[idx] + speed, finish_distance)

                outro_cars = sorted(
                    [dict(c, total_distance=outro_smooth.get(c["car_index"],
                                                              c["total_distance"]))
                     for c in last_cars],
                    key=lambda c: c["total_distance"], reverse=True,
                )

                for rank, car in enumerate(outro_cars):
                    idx = car["car_index"]
                    outro_ypos[idx] += ALPHA_Y * (_target_y(rank) - outro_ypos[idx])

                for car in outro_cars:
                    idx = car["car_index"]
                    outro_history[idx].append((outro_smooth[idx], outro_ypos[idx]))

                img = _render_frame(
                    outro_cars, outro_ypos, outro_history, car_meta,
                    lap_boundary_dists, finish_distance, finish_distance,
                    max_laps, max_laps, times[-1],
                    fonts, sc_status=0, n_cars=n_cars, frame_idx=frame_count,
                    pit_markers=pit_markers,
                )
                proc.stdin.write(img.tobytes())
                frame_count += 1

    finally:
        proc.stdin.close()
        proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exited with code {proc.returncode}. "
            "Is ffmpeg installed and on PATH?"
        )

    size_kb = os.path.getsize(out_path) // 1024
    print(f"[visualizer] mp4 saved: {out_path} ({frame_count} frames, {size_kb} KB)")


def build_gif(
    snapshots: List[Any],
    out_path: str,
    total_laps: int = 0,
    sc_timeline: Optional[List[Tuple[float, int]]] = None,
) -> None:
    mp4 = out_path.replace(".gif", ".mp4") if out_path.endswith(".gif") else out_path + ".mp4"
    print(f"[visualizer] → {mp4}")
    build_mp4(snapshots, mp4, total_laps=total_laps, sc_timeline=sc_timeline)
