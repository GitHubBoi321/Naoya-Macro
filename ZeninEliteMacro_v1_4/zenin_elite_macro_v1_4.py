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

VERSION = "Zen'in Elite Macro v1.4"
ROOT = Path(__file__).resolve().parent

# ---------- Controls ----------
# F6 = start / pause
# F7 = emergency stop
# F9 = print mouse position

active = threading.Event()
shutdown = threading.Event()

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
    end = time.time() + timeout
    while time.time() < end and not shutdown.is_set():
        if not active.is_set():
            time.sleep(0.10)
            continue

        hit = best_match(template_name, threshold=threshold, region=region)
        if hit:
            x, y, score = hit
            print(f"[UI] {template_name} found at ({x},{y}) score={score:.3f}")
            focus_roblox()

            # IMPORTANT: move through DirectInput as well as click through
            # DirectInput. PyAutoGUI movement can move the visible Windows
            # cursor without Roblox updating its internal UI hover position.
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

        time.sleep(0.15)
    return False


def click_ready_verified(timeout=45.0):
    """
    Ready needs a deliberately slow hover/click sequence.

    Detect Ready, move the cursor onto its centre, hold it there long enough
    for Roblox to register the hover, click, then verify that Ready disappears.
    If it is still present, reacquire it and retry instead of continuing.
    """
    end = time.time() + timeout
    attempt = 0

    while time.time() < end and not shutdown.is_set():
        if not active.is_set():
            time.sleep(0.10)
            continue

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
    end = time.time() + timeout
    while time.time() < end and not shutdown.is_set():
        if not active.is_set():
            time.sleep(0.10)
            continue
        hit = best_match(template_name, threshold=threshold, region=region)
        if hit:
            print(f"[DETECT] {template_name} score={hit[2]:.3f}")
            return True
        time.sleep(0.12)
    return False


def press_key(key, presses=1, gap=0.10):
    for _ in range(presses):
        if shutdown.is_set() or not active.is_set():
            return
        pydirectinput.press(key)
        time.sleep(gap)


def combat_start_sequence():
    """Required phase opener: 2 -> Z -> 1."""
    focus_roblox()
    print("[COMBAT] Pressing 2 -> Z -> 1")
    press_key("2")
    time.sleep(START_SEQUENCE_GAP)
    press_key("z")
    time.sleep(START_SEQUENCE_GAP)
    press_key("1")
    time.sleep(0.25)


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


def phase1_spam_until_catchup():
    """Spam R/F/C/X until the catch-up objective is stably detected."""
    print("[PHASE 1] Spamming R/F/C/X until catch-up message.")
    end = time.time() + PHASE_TIMEOUT
    last_detect = 0.0
    catch_hits = 0

    while time.time() < end and active.is_set() and not shutdown.is_set():
        # Check much more frequently than v1.0 because the objective message
        # can appear while combat inputs are still being sent.
        if time.time() - last_detect >= 0.12:
            last_detect = time.time()

            if catchup_visible():
                catch_hits += 1
                print(f"[CHASE] Catch-up confirmation {catch_hits}/3")

                if catch_hits >= 3:
                    release_keys()
                    print("[PHASE 1] Catch-up message CONFIRMED. Skills STOPPED.")
                    return True

                # Do not send another skill between confirmation frames.
                time.sleep(0.07)
                continue
            else:
                catch_hits = 0

        for key in ("r", "f", "c", "x"):
            if shutdown.is_set() or not active.is_set():
                return False

            # Check the banner before each skill as well, so we stop quickly.
            if catchup_visible():
                catch_hits += 1
                if catch_hits >= 3:
                    release_keys()
                    print("[PHASE 1] Catch-up message CONFIRMED. Skills STOPPED.")
                    return True
                time.sleep(0.07)
                continue

            pydirectinput.press(key)
            time.sleep(SKILL_INTERVAL)

    print("[PHASE 1] Timed out waiting for catch-up message.")
    return False


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


def phase2_spam_until_results():
    """
    After the black screen: press 2 -> Z -> 1 again, then spam R/F/C/X
    until the raid summary's Next button appears.
    """
    combat_start_sequence()
    print("[PHASE 2] Spamming R/F/C/X until raid results.")
    end = time.time() + PHASE_TIMEOUT
    last_detect = 0.0

    while time.time() < end and active.is_set() and not shutdown.is_set():
        if time.time() - last_detect >= 0.30:
            last_detect = time.time()
            if best_match(
                "next_button.png",
                threshold=0.70,
                region=(int(pyautogui.size().width * 0.30),
                        int(pyautogui.size().height * 0.55),
                        int(pyautogui.size().width * 0.70),
                        int(pyautogui.size().height * 0.88)),
            ):
                print("[RESULT] Raid summary detected. Skills STOPPED.")
                return True

        for key in ("r", "f", "c", "x"):
            if shutdown.is_set() or not active.is_set():
                return False
            pydirectinput.press(key)
            time.sleep(SKILL_INTERVAL)

    print("[PHASE 2] Timed out waiting for raid results.")
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
    if not phase1_spam_until_catchup():
        return False

    # Chase/cutscene: no skill spam here.
    if not wait_for_chase_failure():
        print("[CYCLE] Chase failure screen not detected.")
        return False

    # Give the transition extra time after "Chase took too long..." so
    # the next 2 -> Z -> 1 inputs are reliably registered.
    time.sleep(1.70)
    if not phase2_spam_until_results():
        return False

    # 7th image: Next
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

    # 5th image: Close
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

    # 6th image: Retry
    if not click_match(
        "retry_button.png",
        threshold=0.68,
        region=(int(pyautogui.size().width * 0.18), 0,
                int(pyautogui.size().width * 0.70), int(pyautogui.size().height * 0.20)),
        timeout=RESULT_TIMEOUT,
    ):
        print("[RESULT] Retry button not found.")
        return False

    print("[CYCLE] Retry clicked. Starting next cycle.")
    time.sleep(1.0)
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
        print("[HOTKEY] PAUSED")
    else:
        focus_roblox()
        active.set()
        print("[HOTKEY] STARTED")


def emergency_stop():
    active.clear()
    shutdown.set()
    release_keys()
    print("[HOTKEY] EMERGENCY STOP")


def print_mouse():
    print("[MOUSE]", pyautogui.position())


def controller():
    print("=" * 62)
    print(VERSION)
    print("F6 Start/Pause | F7 Emergency Stop | F9 Mouse coordinates")
    print("=" * 62)

    while not shutdown.is_set():
        if not active.is_set():
            time.sleep(0.10)
            continue

        ok = run_raid_cycle()
        release_keys()

        if shutdown.is_set():
            break

        if not ok:
            # Do not blindly press inputs after an unexpected screen.
            # Pause so the user can inspect what was missed.
            print("[CYCLE] Detection failed. Macro PAUSED for safety. Press F6 to retry.")
            active.clear()
        else:
            time.sleep(0.5)

    release_keys()
    print("Macro stopped.")


def main():
    pyautogui.PAUSE = 0.02
    pydirectinput.PAUSE = 0.02

    keyboard.add_hotkey("f6", toggle_active)
    keyboard.add_hotkey("f7", emergency_stop)
    keyboard.add_hotkey("f9", print_mouse)

    t = threading.Thread(target=controller, daemon=False)
    t.start()

    try:
        while t.is_alive():
            t.join(timeout=0.25)
    except KeyboardInterrupt:
        emergency_stop()


if __name__ == "__main__":
    main()
