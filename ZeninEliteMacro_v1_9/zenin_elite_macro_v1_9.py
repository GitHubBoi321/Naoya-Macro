import os
import time
import threading
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import pydirectinput
import keyboard

try:
    import pygetwindow as gw
except Exception:
    gw = None

VERSION = "Zen'in Elite Macro v1.9"
ROOT = Path(__file__).resolve().parent

# ---------- Controls ----------
# F6 = start / pause
# F7 = emergency stop
# F8 = restart macro from the beginning
# F9 = print mouse position

active = threading.Event()
shutdown = threading.Event()
restart_requested = threading.Event()


class RestartCycle(Exception):
    """Raised cooperatively when F8 requests an immediate cycle restart."""
    pass


def check_restart():
    if restart_requested.is_set():
        raise RestartCycle

# Timing can be adjusted here if needed.
READY_LOAD_TIMEOUT = 45.0
PHASE_TIMEOUT = 180.0
RESULT_TIMEOUT = 60.0
SKILL_INTERVAL = 0.11
START_SEQUENCE_GAP = 0.35

TEMPLATES = {}
for filename in (
    "ready_button.png",
    "boss_bar.png",
    "catch_up.png",
    "chase_too_long.png",
    "next_button.png",
    "close_button.png",
    "retry_button.png",
    "failure_summary.png",
):
    path = ROOT / filename
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Missing template: {path}")
    TEMPLATES[filename] = img


def focus_roblox():
    if gw is None:
        return
    try:
        wins = [w for w in gw.getWindowsWithTitle("Roblox") if w.width > 300 and w.height > 300]
        if wins:
            w = wins[0]
            try:
                if w.isMinimized:
                    w.restore()
            except Exception:
                pass
            try:
                w.activate()
            except Exception:
                pass
            time.sleep(0.20)
    except Exception:
        pass


def roblox_move_mouse(x, y):
    """
    Move the in-game mouse using DirectInput rather than PyAutoGUI.

    Roblox can visually show a Windows cursor moved by PyAutoGUI without its
    UI receiving the corresponding in-game mouse-motion/hover event. Send the
    absolute movement through PyDirectInput, then a tiny relative wiggle at the
    destination to force Roblox to refresh its internal pointer/hover state.
    """
    check_restart()
    x, y = int(x), int(y)

    # Absolute DirectInput movement.
    pydirectinput.moveTo(x, y)
    time.sleep(0.18)

    # Tiny real movement events around the target. End exactly back at target.
    pydirectinput.moveRel(3, 0)
    time.sleep(0.06)
    pydirectinput.moveRel(-3, 0)
    time.sleep(0.12)

    # Confirm the Windows cursor is also at the expected location.
    mx, my = pyautogui.position()
    return abs(mx - x) <= 8 and abs(my - y) <= 8


def roblox_click_current():
    """Click only after DirectInput movement/hover has settled."""
    time.sleep(0.12)
    pydirectinput.mouseDown()
    time.sleep(0.11)
    pydirectinput.mouseUp()
    time.sleep(0.20)


def screenshot_gray():
    shot = pyautogui.screenshot()
    arr = np.array(shot)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def best_match(template_name, threshold=0.72, region=None,
               scales=(0.72, 0.82, 0.90, 1.0, 1.08, 1.18, 1.30)):
    """Return (cx, cy, score) for a multiscale template match."""
    screen = screenshot_gray()
    sh, sw = screen.shape[:2]

    ox = oy = 0
    search = screen
    if region is not None:
        x1, y1, x2, y2 = region
        x1 = max(0, min(sw, int(x1)))
        x2 = max(0, min(sw, int(x2)))
        y1 = max(0, min(sh, int(y1)))
        y2 = max(0, min(sh, int(y2)))
        if x2 <= x1 or y2 <= y1:
            return None
        search = screen[y1:y2, x1:x2]
        ox, oy = x1, y1

    template = TEMPLATES[template_name]
    best = None

    for scale in scales:
        tw = max(8, int(template.shape[1] * scale))
        th = max(8, int(template.shape[0] * scale))
        if tw >= search.shape[1] or th >= search.shape[0]:
            continue

        resized = cv2.resize(template, (tw, th), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(search, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)

        if best is None or score > best[2]:
            best = (ox + loc[0] + tw // 2, oy + loc[1] + th // 2, float(score))

    if best and best[2] >= threshold:
        return best
    return None


def click_match(template_name, threshold, region, timeout):
    remaining = float(timeout)
    last = time.monotonic()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return False
            last = time.monotonic()
            continue

        now = time.monotonic()
        remaining -= now - last
        last = now

        hit = best_match(template_name, threshold=threshold, region=region)
        if hit:
            x, y, score = hit
            print(f"[UI] {template_name} found at ({x},{y}) score={score:.3f}")
            focus_roblox()

            if not roblox_move_mouse(x, y):
                print(
                    f"[UI] DirectInput cursor move did not settle on "
                    f"{template_name}; reacquiring."
                )
                continue

            print(
                f"[UI] DirectInput cursor settled on {template_name}; "
                "sending click."
            )
            roblox_click_current()
            return True

        if not pause_aware_sleep(0.15):
            return False

    return False



def click_ready_verified(timeout=45.0):
    """
    Ready needs a deliberately slow hover/click sequence.

    Detect Ready, move the cursor onto its centre, hold it there long enough
    for Roblox to register the hover, click, then verify that Ready disappears.
    If it is still present, reacquire it and retry instead of continuing.
    """
    remaining = float(timeout)
    last = time.monotonic()
    attempt = 0

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return False
            last = time.monotonic()
            continue

        now = time.monotonic()
        remaining -= now - last
        last = now

        sw, sh = pyautogui.size()
        hit = best_match(
            "ready_button.png",
            threshold=0.66,
            region=(int(sw * 0.28), 0, int(sw * 0.72), int(sh * 0.25)),
            scales=(0.72, 0.82, 0.90, 1.0, 1.08, 1.18, 1.30),
        )

        if hit is None:
            time.sleep(0.12)
            continue

        x, y, score = hit
        attempt += 1
        print(
            f"[READY] Found at ({x},{y}) score={score:.3f}; "
            f"verified click attempt {attempt}."
        )

        focus_roblox()

        # Movement itself must use DirectInput. A PyAutoGUI move can update
        # the visible cursor without updating Roblox's internal hover target.
        if not roblox_move_mouse(x, y):
            print("[READY] DirectInput cursor move did not reach Ready; reacquiring.")
            continue

        print("[READY] DirectInput cursor is on Ready; hovering before click...")
        time.sleep(0.45)
        roblox_click_current()
        time.sleep(0.40)

        # Success is not assumed from the click. Verify Ready is gone.
        still_there = best_match(
            "ready_button.png",
            threshold=0.66,
            region=(int(sw * 0.28), 0, int(sw * 0.72), int(sh * 0.25)),
            scales=(0.72, 0.82, 0.90, 1.0, 1.08, 1.18, 1.30),
        )

        if still_there is None:
            print("[READY] Ready disappeared: click CONFIRMED.")
            return True

        print("[READY] Ready is still visible; click did not register. Retrying.")
        time.sleep(0.35)

    return False


def wait_match(template_name, threshold, region, timeout):
    remaining = float(timeout)
    last = time.monotonic()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return False
            last = time.monotonic()
            continue

        now = time.monotonic()
        remaining -= now - last
        last = now

        hit = best_match(template_name, threshold=threshold, region=region)
        if hit:
            print(f"[DETECT] {template_name} score={hit[2]:.3f}")
            return True

        if not pause_aware_sleep(0.12):
            return False

    return False


def wait_until_active():
    """
    Cooperative pause point.

    Clearing `active` pauses in-place; setting it again resumes the same
    function/phase instead of returning False and restarting the raid cycle.
    """
    check_restart()
    while not active.is_set() and not shutdown.is_set():
        check_restart()
        time.sleep(0.05)
    return not shutdown.is_set()


def pause_aware_sleep(seconds):
    """
    Sleep for ACTIVE runtime only. Time spent paused does not consume the
    requested delay, so resuming continues where the macro left off.
    """
    remaining = float(seconds)
    last = time.monotonic()
    check_restart()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return False
            last = time.monotonic()
            continue

        now = time.monotonic()
        remaining -= now - last
        last = now
        if remaining > 0:
            time.sleep(min(0.03, remaining))

    return not shutdown.is_set()


def deadline_remaining(active_seconds):
    """Create a pause-aware countdown value."""
    return float(active_seconds)


def press_key(key, presses=1, gap=0.10):
    for _ in range(presses):
        if shutdown.is_set():
            return False
        if not wait_until_active():
            return False
        pydirectinput.press(key)
        if not pause_aware_sleep(gap):
            return False
    return True


def combat_start_sequence():
    """Required phase opener: 2 -> Z -> 1."""
    focus_roblox()
    print("[COMBAT] Pressing 2 -> Z -> 1")
    press_key("2")
    pause_aware_sleep(START_SEQUENCE_GAP)
    press_key("z")
    pause_aware_sleep(START_SEQUENCE_GAP)
    press_key("1")
    pause_aware_sleep(0.25)


def catchup_visible():
    """
    Detect the actual centered "Catch up with Zen'in Elite" objective using
    the user's newer reference screenshot.

    Search only the narrow center band where the objective appears. This avoids
    matching the boss name/health bar or other Zen'in Elite text elsewhere.
    """
    sw, sh = pyautogui.size()
    hit = best_match(
        "catch_up.png",
        threshold=0.72,
        region=(
            int(sw * 0.30),
            int(sh * 0.20),
            int(sw * 0.70),
            int(sh * 0.38),
        ),
        scales=(0.72, 0.82, 0.90, 0.96, 1.00, 1.04, 1.10, 1.18, 1.28),
    )

    if hit:
        x, y, score = hit

        # Extra positional guard: the real objective is near horizontal centre
        # and well below the boss health bar.
        if abs(x - sw / 2) <= sw * 0.16 and sh * 0.22 <= y <= sh * 0.36:
            print(f"[CHASE] TRUE catch-up candidate at ({x},{y}) score={score:.3f}")
            return True

    return False


def raid_result_visible():
    """Check for death/results while abilities are actively being spammed."""
    check_restart()
    sw, sh = pyautogui.size()

    # Check the explicit Failure detector first.
    if failure_summary_visible():
        return "failure"

    # Shared result-screen fallback: the Next button.
    if best_match(
        "next_button.png",
        threshold=0.66,
        region=(int(sw * 0.28), int(sh * 0.55),
                int(sw * 0.72), int(sh * 0.88)),
        scales=(0.78, 0.88, 0.96, 1.0, 1.05, 1.12, 1.22),
    ):
        return "result"
    return None


def phase1_spam_until_catchup():
    """Spam abilities while continuously watching for death and catch-up."""
    print("[PHASE 1] Spamming R/F/C/X; monitoring death + catch-up.")
    remaining=float(PHASE_TIMEOUT)
    last_tick=time.monotonic()
    catch_hits=0

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active(): return None
            last_tick=time.monotonic()
            continue

        now=time.monotonic()
        remaining -= now-last_tick
        last_tick=now

        for key in ("r","f","c","x"):
            check_restart()
            if shutdown.is_set() or not wait_until_active(): return None

            # Critical: death can happen here, so inspect BEFORE every ability.
            result=raid_result_visible()
            if result:
                release_keys()
                print(f"[PHASE 1] Raid-ending screen detected during spam: {result}")
                return result

            if catchup_visible():
                catch_hits += 1
                print(f"[CHASE] Catch-up confirmation {catch_hits}/3")
                if catch_hits >= 3:
                    release_keys()
                    return "catchup"
                pause_aware_sleep(0.07)
                continue
            else:
                catch_hits=0

            pydirectinput.press(key)
            if not pause_aware_sleep(SKILL_INTERVAL): return None

    return None


def wait_for_chase_failure():
    """Wait for the black 'Chase took too long...' screen."""
    print("[CHASE] Waiting for black chase-failure screen...")
    return wait_match(
        "chase_too_long.png",
        threshold=0.68,
        region=(0, int(pyautogui.size().height * 0.30),
                pyautogui.size().width, int(pyautogui.size().height * 0.72)),
        timeout=PHASE_TIMEOUT,
    )


def failure_summary_visible():
    """
    Detect the death/failure result screen two ways:
      1) tight template match around the Raid Summary: Failure heading
      2) red-pixel signature in the heading area as a fallback

    This avoids depending on one large screenshot/template match.
    """
    sw, sh = pyautogui.size()

    hit = best_match(
        "failure_summary.png",
        threshold=0.54,
        region=(int(sw * 0.34), int(sh * 0.30),
                int(sw * 0.66), int(sh * 0.47)),
        scales=(0.62, 0.72, 0.82, 0.90, 0.96, 1.0, 1.04, 1.10, 1.18, 1.28, 1.40),
    )
    if hit:
        print(f"[RESULT] Failure heading template score={hit[2]:.3f}")
        return True

    # Fallback: the word "Failure" is bright red while the surrounding heading
    # is otherwise white/gray. Count saturated red pixels only in that heading band.
    shot = np.array(pyautogui.screenshot())
    hsv = cv2.cvtColor(shot, cv2.COLOR_RGB2HSV)
    x1, x2 = int(sw * 0.38), int(sw * 0.62)
    y1, y2 = int(sh * 0.32), int(sh * 0.45)
    roi = hsv[y1:y2, x1:x2]

    red1 = cv2.inRange(roi, np.array([0, 135, 145], dtype=np.uint8),
                      np.array([10, 255, 255], dtype=np.uint8))
    red2 = cv2.inRange(roi, np.array([170, 135, 145], dtype=np.uint8),
                      np.array([179, 255, 255], dtype=np.uint8))
    red_pixels = int(cv2.countNonZero(cv2.bitwise_or(red1, red2)))

    if red_pixels >= 35:
        print(f"[RESULT] Failure red-text signature detected ({red_pixels} px).")
        return True

    return False


def phase2_spam_until_results():
    """Second ability-spam phase, with death/result checks before every skill."""
    combat_start_sequence()
    print("[PHASE 2] Spamming R/F/C/X; monitoring death/results.")
    remaining=float(PHASE_TIMEOUT)
    last_tick=time.monotonic()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active(): return None
            last_tick=time.monotonic()
            continue

        now=time.monotonic()
        remaining -= now-last_tick
        last_tick=now

        for key in ("r","f","c","x"):
            check_restart()
            if shutdown.is_set() or not wait_until_active(): return None

            # Critical: inspect while the player is actually vulnerable/spamming.
            detected=raid_result_visible()
            if detected:
                release_keys()
                print(f"[PHASE 2] Raid-ending screen detected during spam: {detected}")
                return "failure" if detected=="failure" else "success"

            pydirectinput.press(key)
            if not pause_aware_sleep(SKILL_INTERVAL): return None
    return None


def click_retry_verified(timeout=RESULT_TIMEOUT):
    """
    Detect/click the actual top-centre Retry (0/1) button.

    The failure flow can take a moment after Next before this screen becomes
    interactive, so keep reacquiring Retry and verify that it disappears after
    the click. Uses the Roblox DirectInput mouse movement/wiggle.
    """
    remaining = float(timeout)
    last = time.monotonic()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return False
            last = time.monotonic()
            continue

        now = time.monotonic()
        remaining -= now - last
        last = now

        sw, sh = pyautogui.size()
        hit = best_match(
            "retry_button.png",
            threshold=0.58,
            region=(int(sw * 0.18), 0, int(sw * 0.70), int(sh * 0.18)),
            scales=(0.60, 0.70, 0.80, 0.88, 0.94, 1.0, 1.06, 1.14, 1.24, 1.36),
        )

        if hit:
            x, y, score = hit
            print(f"[RETRY] Found Retry at ({x},{y}) score={score:.3f}")
            focus_roblox()

            if not roblox_move_mouse(x, y):
                print("[RETRY] Mouse did not settle; reacquiring Retry.")
                pause_aware_sleep(0.15)
                continue

            # Give this screen extra hover time because it appears immediately
            # after closing the failure summary.
            pause_aware_sleep(0.40)
            roblox_click_current()
            pause_aware_sleep(0.65)

            # Confirm Retry is no longer present before starting another cycle.
            still_there = best_match(
                "retry_button.png",
                threshold=0.58,
                region=(int(sw * 0.18), 0, int(sw * 0.70), int(sh * 0.18)),
                scales=(0.60, 0.70, 0.80, 0.88, 0.94, 1.0, 1.06, 1.14, 1.24, 1.36),
            )
            if still_there is None:
                print("[RETRY] Retry click CONFIRMED.")
                return True

            print("[RETRY] Retry is still visible; clicking again.")
        else:
            pause_aware_sleep(0.15)

    return False


def run_raid_cycle():
    focus_roblox()

    # 1) Ready screen
    print("\n[CYCLE] Waiting for Ready...")
    if not click_ready_verified(timeout=READY_LOAD_TIMEOUT):
        print("[CYCLE] Ready could not be clicked/verified.")
        return False

    # Recenter/shift-lock exactly as requested after Ready.
    print("[CYCLE] Ready clicked. Pressing CTRL twice to recenter.")
    time.sleep(0.25)
    press_key("ctrl")
    time.sleep(0.18)
    press_key("ctrl")
    time.sleep(0.35)

    # 2) Wait for boss arena before sending combat inputs.
    print("[CYCLE] Waiting for Zen'in Elite arena...")
    if not wait_match(
        "boss_bar.png",
        threshold=0.58,
        region=(int(pyautogui.size().width * 0.18), 0,
                int(pyautogui.size().width * 0.82), int(pyautogui.size().height * 0.28)),
        timeout=READY_LOAD_TIMEOUT,
    ):
        print("[CYCLE] Boss arena not detected.")
        return False

    # First combat phase.
    combat_start_sequence()
    phase1_result = phase1_spam_until_catchup()
    if phase1_result is None:
        return False

    if phase1_result == "failure":
        # Death occurred during the first vulnerable/ability-spam phase.
        result = "failure"
    elif phase1_result == "result":
        # Generic result screen appeared during phase 1.
        result = "success"
    else:
        # Normal chase path.
        if not wait_for_chase_failure():
            print("[CYCLE] Chase failure screen not detected.")
            return False

        pause_aware_sleep(1.70)
        result = phase2_spam_until_results()
        if result is None:
            return False

    # Both success and death/failure show Next.
    if not click_match(
        "next_button.png",
        threshold=0.70,
        region=(int(pyautogui.size().width * 0.30),
                int(pyautogui.size().height * 0.55),
                int(pyautogui.size().width * 0.70),
                int(pyautogui.size().height * 0.88)),
        timeout=RESULT_TIMEOUT,
    ):
        print("[RESULT] Next button not found.")
        return False

    if result == "success":
        # Successful raids have the rewards page, so click Close first.
        if not click_match(
            "close_button.png",
            threshold=0.70,
            region=(int(pyautogui.size().width * 0.30),
                    int(pyautogui.size().height * 0.55),
                    int(pyautogui.size().width * 0.70),
                    int(pyautogui.size().height * 0.88)),
            timeout=RESULT_TIMEOUT,
        ):
            print("[RESULT] Close button not found.")
            return False
    else:
        print("[RESULT] Failure path: Next closed the failure popup; waiting for Retry screen.")
        pause_aware_sleep(1.00)

    # Retry uses its own detector because the actual button is the long
    # top-centre "Retry (0/1)" control shown in the supplied screenshot.
    if not click_retry_verified(timeout=RESULT_TIMEOUT):
        print("[RESULT] Retry button not found/clicked.")
        return False

    print("[CYCLE] Retry clicked. Starting next cycle.")
    pause_aware_sleep(1.0)
    return True


def release_keys():
    for key in ("w", "a", "s", "d", "r", "f", "c", "x", "z", "1", "2"):
        try:
            pydirectinput.keyUp(key)
        except Exception:
            pass


def toggle_active():
    if active.is_set():
        active.clear()
        release_keys()
        print("[HOTKEY] PAUSED in place — F6 resumes this same step.")
    else:
        focus_roblox()
        active.set()
        print("[HOTKEY] RESUMED from current step.")



def restart_from_beginning():
    """
    F8 abandons the current phase and starts a fresh raid cycle from Ready.
    It also unpauses the macro if necessary.
    """
    release_keys()
    restart_requested.set()
    active.set()
    print("[HOTKEY] RESTART requested — returning to the beginning (Ready).")


def emergency_stop():
    active.clear()
    shutdown.set()
    release_keys()
    print("[HOTKEY] EMERGENCY STOP")


def print_mouse():
    print("[MOUSE]", pyautogui.position())


def console_clearer():
    """Clear the console display every 10 minutes without changing macro state."""
    while not shutdown.wait(600.0):
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 62)
        print(VERSION)
        print("[LOG] Console automatically cleared after 10 minutes.")
        print("F6 Start/Pause | F7 Emergency Stop | F8 Restart | F9 Mouse coordinates")
        print("=" * 62)


def controller():
    print("=" * 62)
    print(VERSION)
    print("F6 Start/Pause | F7 Emergency Stop | F8 Restart | F9 Mouse coordinates")
    print("=" * 62)

    while not shutdown.is_set():
        if not active.is_set():
            time.sleep(0.10)
            continue

        try:
            ok = run_raid_cycle()
            release_keys()
        except RestartCycle:
            release_keys()
            restart_requested.clear()
            print("[HOTKEY] Restart accepted. Beginning again from Ready.")
            continue

        if shutdown.is_set():
            break

        if not ok:
            print("[CYCLE] Detection failed. Macro PAUSED for safety. Press F6 to retry or F8 to restart.")
            active.clear()
        else:
            try:
                pause_aware_sleep(0.5)
            except RestartCycle:
                release_keys()
                restart_requested.clear()
                print("[HOTKEY] Restart accepted. Beginning again from Ready.")
                continue

    release_keys()
    print("Macro stopped.")


def main():
    pyautogui.PAUSE = 0.02
    pydirectinput.PAUSE = 0.02

    keyboard.add_hotkey("f6", toggle_active)
    keyboard.add_hotkey("f7", emergency_stop)
    keyboard.add_hotkey("f8", restart_from_beginning)
    keyboard.add_hotkey("f9", print_mouse)

    # Independent log cleaner: does not pause/restart the raid state.
    threading.Thread(target=console_clearer, daemon=True).start()

    t = threading.Thread(target=controller, daemon=False)
    t.start()

    try:
        while t.is_alive():
            t.join(timeout=0.25)
    except KeyboardInterrupt:
        emergency_stop()


if __name__ == "__main__":
    main()
