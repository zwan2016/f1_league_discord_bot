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
  With X_POWER ≈ 0.40 a car 0.5% behind the leader (≈5 s gap) appears at
  ~65% of bar width instead of 99.5%.

History lines
─────────────
  Each car accumulates (total_distance, y_pixel) points.  At render time
  total_distance is re-projected through the current x scale, so as x_max
  grows the older history naturally compresses toward the left.

Lap markers + finish flag
─────────────────────────
  Leader's lap transitions are detected online; the total_distance at each
  lap boundary is recorded and drawn as a thin vertical line with a label.
  The checkered finish flag uses the same sliding-in mechanic: it is drawn
  at _dist_to_x(finish_distance, x_max) and only becomes visible once x_max
  has grown past finish_distance (i.e. the leader crosses the line).

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
FOOTER_H   = 44                   # taller – lap labels live here
LEFT_W     = 178                  # team name column
LINE_AREA  = 840                  # x-axis pixel width  (LEFT_W + LINE_AREA = 1018)
ICON_SIZE  = 28                   # half-length of car icon

# Non-linear x scale: gap_frac^X_POWER.  0.40 gives clear visual separation
# without the extreme sensitivity of 0.20 that caused P1-P2 twitching.
X_POWER = 0.40

# Smoothing
ALPHA_X    = 0.08   # x_max camera follows leader distance
ALPHA_Y    = 0.18   # y rank transitions
ALPHA_DIST = 0.15   # per-car total_distance smoothing (stabilises x position)

OUTRO_S = 3         # seconds of end sequence (cars race to the finish line)

# Colours
BG        = (10, 10, 22)
STRIPE    = (16, 16, 32)
TEXT      = (238, 238, 255)
DIM       = (95, 95, 122)
GOLD      = (255, 200, 50)
RED_PEN   = (255, 80, 80)
SC_COL    = (255, 210, 0)
GRID      = (28, 28, 50)
LAP_LINE  = (40, 40, 65)
HIST_DIM  = 0.60  # history line brightness vs solid colour


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
    """Draw a vertical black-and-white checkered flag strip at pixel x."""
    n_rows = (y_bottom - y_top) // sq
    for row in range(n_rows):
        for col in range(cols):
            black = (row + col) % 2 == 0
            fill = (0, 0, 0) if black else (240, 240, 240)
            x0 = x + col * sq
            y0 = y_top + row * sq
            draw.rectangle([x0, y0, x0 + sq - 1, y0 + sq - 1], fill=fill)


def _dist_to_x(dist: float, x_max: float) -> float:
    """Map total_distance → screen x using non-linear power scale.
    x_min is always 0 (race origin); x_max is the leader's current distance.
    gap_frac^X_POWER expands the near-leader zone so cars don't cluster at right.
    """
    if x_max <= 0:
        return float(LEFT_W)
    rel = max(0.0, min(1.0, dist / x_max))
    gap = 1.0 - rel                          # 0 = leader, 1 = completely behind
    return LEFT_W + (1.0 - gap ** X_POWER) * LINE_AREA


# ── car icon ─────────────────────────────────────────────────────────────────

def _draw_car_icon(
    draw: ImageDraw.Draw,
    x_tip: float,   # nose (rightmost point)
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
    sc_active: bool,
    n_cars: int,
) -> Image.Image:
    font_hd, font_md, font_sm, font_xs = fonts

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

    # ── lap boundary markers ──────────────────────────────────────────────────
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

    # ── checkered finish flag — slides in from right like lap markers ─────────
    # Only visible once x_max has grown to reach finish_distance.
    if x_max > 0 and finish_distance > 0 and finish_distance <= x_max:
        flag_x = int(_dist_to_x(finish_distance, x_max))
        if LEFT_W <= flag_x <= LEFT_W + LINE_AREA:
            _draw_checkered_flag(draw, flag_x, HEADER_H, H - FOOTER_H)

    # ── history polylines (drawn below icons) ─────────────────────────────────
    for idx, hist in history.items():
        if len(hist) < 2:
            continue
        colour = car_meta.get(idx, {}).get("colour", DEFAULT_COLOUR)
        hc = _dim(colour, HIST_DIM)
        # Subsample for speed; always keep newest point
        step = max(1, len(hist) // 300)
        pts_raw = hist[::step]
        if pts_raw[-1] != hist[-1]:
            pts_raw = pts_raw + [hist[-1]]
        pts = [(int(_dist_to_x(d, x_max)), int(y)) for d, y in pts_raw]
        draw.line(pts, fill=hc, width=2)

    # ── car icons + labels ────────────────────────────────────────────────────
    for car in cars:
        idx = car["car_index"]
        yc = y_pos.get(idx)
        if yc is None:
            continue

        meta    = car_meta.get(idx, {})
        colour  = meta.get("colour", DEFAULT_COLOUR)
        name    = meta.get("name", "???")
        team_id = meta.get("team_id", -1)

        cx = _dist_to_x(car["total_distance"], x_max)
        icon_tip = cx + icon_sz
        _draw_car_icon(draw, icon_tip, yc, colour, size=icon_sz)

        # driver name after icon
        if icon_tip + 6 < W - 20:
            draw.text((icon_tip + 5, yc), name[:14], fill=TEXT, font=font_md, anchor="lm")

        # PIT indicator
        if car.get("pit_status", 0) > 0:
            draw.text((cx + 3, yc), "PIT", fill=GOLD, font=font_xs, anchor="lm")

        # left column: rank + team name (at animated y position)
        team_str = TEAM_NAMES.get(team_id, "???")
        draw.text((6, yc), f"P{car['car_position']}", fill=DIM, font=font_xs, anchor="lm")
        draw.text((38, yc), team_str[:12], fill=TEXT, font=font_sm, anchor="lm")

    # ── header ────────────────────────────────────────────────────────────────
    mins, secs = divmod(int(race_time), 60)
    draw.text((W // 2, HEADER_H // 2),
              f"LAP {lap} / {total_laps}    {mins}:{secs:02d}",
              fill=TEXT, font=font_hd, anchor="mm")
    if sc_active:
        draw.text((W - 14, HEADER_H // 2), "⚠ SAFETY CAR",
                  fill=SC_COL, font=font_md, anchor="rm")

    # ── footer: x-axis label ──────────────────────────────────────────────────
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
    sc_events: Optional[List[Dict]] = None,
) -> None:
    if not snapshots:
        raise ValueError("No snapshots to animate")

    # Deduplicate: multiple UDP packets can share the same session_time float.
    by_time: Dict[float, Dict[int, Dict]] = defaultdict(dict)
    for s in snapshots:
        entry = dict(s) if not isinstance(s, dict) else s
        by_time[entry["session_time"]][entry["car_index"]] = entry

    times = sorted(by_time.keys())
    step = max(1, len(times) // TARGET_FRAMES)
    times = times[::step]
    # Always keep the very last time point so the finish is never cut off
    if times[-1] != sorted(by_time.keys())[-1]:
        times.append(sorted(by_time.keys())[-1])

    # Safety car ranges
    sc_ranges: List[tuple] = []
    if sc_events:
        sc_start = None
        for ev in sorted(sc_events, key=lambda e: e["session_time"]):
            if ev.get("event_code") == "SCAR":
                if sc_start is None:
                    sc_start = ev["session_time"]
                else:
                    sc_ranges.append((sc_start, ev["session_time"]))
                    sc_start = None

    def _sc_active(t: float) -> bool:
        return any(a <= t <= b for a, b in sc_ranges)

    fonts = (_load_font(24), _load_font(14), _load_font(13), _load_font(11))

    # Determine stable n_cars
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

    # Pre-scan: detect lap boundary distances + compute finish_distance
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

    # Animation state
    y_pos:       Dict[int, float] = {}
    smooth_dist: Dict[int, float] = {}   # per-car smoothed total_distance
    x_max_cur:   Optional[float] = None
    history:     Dict[int, List[Tuple[float, float]]] = defaultdict(list)
    car_meta:    Dict[int, Dict] = {}
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

            # Cache car metadata on first sight
            for car in cars:
                idx = car["car_index"]
                if idx not in car_meta:
                    car_meta[idx] = {
                        "colour":  TEAM_COLOURS.get(car.get("team_id", -1), DEFAULT_COLOUR),
                        "name":    car.get("name", "???"),
                        "team_id": car.get("team_id", -1),
                    }

            # Smooth y positions
            for rank, car in enumerate(cars):
                idx = car["car_index"]
                target = _target_y(rank)
                if idx not in y_pos:
                    y_pos[idx] = target
                else:
                    y_pos[idx] += ALPHA_Y * (target - y_pos[idx])

            # Smooth per-car total_distance to damp telemetry noise.
            for car in cars:
                idx = car["car_index"]
                raw = car["total_distance"]
                if idx not in smooth_dist:
                    smooth_dist[idx] = raw
                else:
                    smooth_dist[idx] += ALPHA_DIST * (raw - smooth_dist[idx])

            # x_max tracks leader distance, capped at finish_distance.
            # Never grows past finish_distance so the flag stays at the right edge.
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

            # Record history using smoothed distance for visual consistency
            for car in cars:
                idx = car["car_index"]
                history[idx].append((smooth_dist[idx], y_pos[idx]))

            lap = max((c["current_lap"] for c in cars), default=1)
            max_laps = max(max_laps, lap)

            # Pass smoothed distances so the renderer uses stable x positions
            cars_display = [dict(c, total_distance=smooth_dist.get(c["car_index"],
                                                                    c["total_distance"]))
                            for c in cars]

            img = _render_frame(
                cars_display, y_pos, history, car_meta,
                lap_boundary_dists, finish_distance, x_max_cur,
                lap, max_laps, t,
                fonts, sc_active=_sc_active(t), n_cars=n_cars,
            )
            proc.stdin.write(img.tobytes())
            frame_count += 1

        # ── Outro: each car moves at uniform speed toward finish_distance ─────
        # All cars share the same speed; the car furthest from finish arrives
        # last (at exactly OUTRO_S seconds).  History extends each frame so
        # trails never break.
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

            for _frame_i in range(FPS * OUTRO_S):
                # Advance every car by the same speed, stop at finish
                for idx in list(outro_smooth):
                    outro_smooth[idx] = min(outro_smooth[idx] + speed, finish_distance)

                # Re-sort by current distance
                outro_cars = sorted(
                    [dict(c, total_distance=outro_smooth.get(c["car_index"],
                                                              c["total_distance"]))
                     for c in last_cars],
                    key=lambda c: c["total_distance"], reverse=True,
                )

                # Smooth y positions to reflect updated ranking
                for rank, car in enumerate(outro_cars):
                    idx = car["car_index"]
                    target = _target_y(rank)
                    outro_ypos[idx] += ALPHA_Y * (target - outro_ypos[idx])

                # Extend history so trails continue through the outro
                for car in outro_cars:
                    idx = car["car_index"]
                    outro_history[idx].append((outro_smooth[idx], outro_ypos[idx]))

                img = _render_frame(
                    outro_cars, outro_ypos, outro_history, car_meta,
                    lap_boundary_dists, finish_distance, finish_distance,
                    max_laps, max_laps, times[-1],
                    fonts, sc_active=False, n_cars=n_cars,
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
    sc_events: Optional[List[Dict]] = None,
) -> None:
    mp4 = out_path.replace(".gif", ".mp4") if out_path.endswith(".gif") else out_path + ".mp4"
    print(f"[visualizer] → {mp4}")
    build_mp4(snapshots, mp4, total_laps=total_laps, sc_events=sc_events)
