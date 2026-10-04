import os
import ctypes

# IMPORTANT: enable physical-pixel coordinates before importing mouse/screenshot
# libraries. Without this, Windows display scaling can make template coordinates
# and cursor coordinates use different coordinate systems.
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import time
import threading
from pathlib import Path

import cv2
import numpy as np
import mss
import math
import random
import pyautogui
import pydirectinput
import keyboard

try:
    import pygetwindow as gw
except Exception:
    gw = None

VERSION = "Zen'in Elite Macro v3.20"
ROOT = Path(__file__).resolve().parent

# ---------- Controls ----------
# F6 = start / pause
# F7 = emergency stop
# F8 = restart macro from the beginning
# F9 = print mouse position

active = threading.Event()
shutdown = threading.Event()
home_watchdog_suppress_until = 0.0
restart_requested = threading.Event()
recovery_in_progress = threading.Event()
last_connection_check = 0.0


class RestartCycle(Exception):
    """Raised cooperatively when F8 requests an immediate cycle restart."""
    pass


class ConnectionRecovery(Exception):
    """Raised when Roblox displays a disconnect/error dialog."""
    pass

class HomePageRecovery(Exception):
    """Raised when the Roblox experience/home page is detected directly."""
    pass



def raid_arena_visible():
    """Positive guard for the real post-Ready Zen'in Elite arena."""
    sw, sh = pyautogui.size()
    return best_match(
        "raid_arena_hud.png",
        threshold=0.70,
        region=(int(sw*0.18), 0, int(sw*0.82), int(sh*0.28)),
        scales=(0.82,0.88,0.94,1.0,1.06,1.12,1.18),
    ) is not None


def check_restart():
    global last_connection_check

    if restart_requested.is_set():
        raise RestartCycle

    # The normal raid code calls check_restart very frequently, making this a
    # lightweight watchdog without a second thread fighting over the mouse.
    if recovery_in_progress.is_set():
        return

    now = time.monotonic()
    if now - last_connection_check < 0.75:
        return
    last_connection_check = now

    try:
        sw, sh = pyautogui.size()
        hit = best_match(
            "disconnect_popup.png",
            threshold=0.70,
            region=(int(sw*0.25), int(sh*0.20), int(sw*0.75), int(sh*0.75)),
            scales=(0.72, 0.82, 0.90, 1.0, 1.10, 1.22, 1.35),
        )
        failed_hit = best_match(
            "connection_failed_popup.png",
            threshold=0.68,
            region=(int(sw*0.25), int(sh*0.20), int(sw*0.75), int(sh*0.75)),
            scales=(0.72, 0.82, 0.90, 1.0, 1.10, 1.22, 1.35),
        )
        if hit or failed_hit:
            raise ConnectionRecovery

        # Home-page detection comes AFTER Error 277/279. First positively rule
        # out live raid gameplay using the user's real post-Ready boss HUD.
        if raid_arena_visible():
            return

        # The clean Play icon is simple, so never search the whole game screen
        # at a permissive threshold. Require a strong, persistent match.
        home_hit = best_match(
            "play_button.png",
            threshold=0.90,
            scales=(0.88,0.94,1.0,1.06,1.12),
        )
        if home_hit:
            time.sleep(0.20)
            home_hit2 = best_match(
                "play_button.png",
                threshold=0.90,
                scales=(0.88,0.94,1.0,1.06,1.12),
            )
            if home_hit2:
                print(f"[WATCHDOG] Blue Play confirmed score={home_hit2[2]:.3f}.")
                raise HomePageRecovery
    except (ConnectionRecovery, HomePageRecovery):
        raise
    except Exception:
        # Connection monitoring must never break normal raid operation.
        return

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
    "success_summary.png",
    "raid_arena_hud.png",
    "disconnect_popup.png",
    "connection_failed_popup.png",
    "leave_button.png",
    "cancel_button.png",
    "play_button.png",
    "gamemodes_button.png",
    "raids_button.png",
    "create_tab.png",
    "projection_card.png",
    "calamity_button.png",
    "friends_only_button.png",
    "modifiers_button.png",
    "weaken_button.png",
    "hardcore_button.png",
    "create_raid_button.png",
    "lobby_start_button.png",
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



# ---------------------------------------------------------------------------
# v3.5: Calamity-Cleaver style screen + mouse engine
# MSS scans and SendInput absolute VIRTUALDESK mouse coordinates use the same
# physical desktop coordinate system, avoiding PyAutoGUI/DPI conversion drift.
# ---------------------------------------------------------------------------
_CC_COARSE_GATE = 0.55
_CC_SCALES = (1.0, 0.98, 1.02, 0.96, 1.04, 0.92, 1.08, 0.85, 1.15)

if os.name == "nt":
    from ctypes import wintypes
    _cc_user32 = ctypes.windll.user32
    _CC_ULONG_PTR = ctypes.c_size_t
    _CC_MOVE, _CC_LEFTDOWN, _CC_LEFTUP = 0x0001, 0x0002, 0x0004
    _CC_ABSOLUTE, _CC_VIRTUALDESK = 0x8000, 0x4000

    class _CC_MOUSEINPUT(ctypes.Structure):
        _fields_=[("dx",wintypes.LONG),("dy",wintypes.LONG),("mouseData",wintypes.DWORD),
                  ("dwFlags",wintypes.DWORD),("time",wintypes.DWORD),("dwExtraInfo",_CC_ULONG_PTR)]
    class _CC_INPUTUNION(ctypes.Union):
        _fields_=[("mi",_CC_MOUSEINPUT)]
    class _CC_INPUT(ctypes.Structure):
        _fields_=[("type",wintypes.DWORD),("u",_CC_INPUTUNION)]

def cc_virtual_screen():
    if os.name=="nt":
        return tuple(_cc_user32.GetSystemMetrics(i) for i in (76,77,78,79))
    w,h=pyautogui.size()
    return (0,0,w,h)

def cc_send_mouse(flags,dx=0,dy=0):
    if os.name!="nt":
        return
    inp=_CC_INPUT(0,_CC_INPUTUNION(mi=_CC_MOUSEINPUT(dx,dy,0,flags,0,0)))
    if _cc_user32.SendInput(1,ctypes.byref(inp),ctypes.sizeof(_CC_INPUT)) != 1:
        raise OSError("SendInput was blocked")

def cc_cursor_pos():
    if os.name=="nt":
        pt=wintypes.POINT()
        _cc_user32.GetCursorPos(ctypes.byref(pt))
        return pt.x,pt.y
    p=pyautogui.position()
    return p.x,p.y

def cc_move_abs(x,y,vs=None):
    """Move the real Windows cursor directly to physical desktop coordinates."""
    x,y=int(round(x)),int(round(y))
    if os.name=="nt":
        ctypes.windll.user32.SetCursorPos(x,y)
    else:
        pyautogui.moveTo(x,y)

def cc_glide_to(tx,ty):
    """
    Reliable v3.8 movement: interpolate with SetCursorPos, then generate small
    real relative mouse events so Roblox registers hover.
    """
    tx,ty=int(round(tx)),int(round(ty))
    sx,sy=cc_cursor_pos()
    dist=max(1.0,math.hypot(tx-sx,ty-sy))
    duration=min(0.9,0.20+dist/2200.0)
    steps=max(18,int(duration/0.012))

    for i in range(1,steps+1):
        if shutdown.is_set():
            return False
        if not active.is_set() and not recovery_pause_gate():
            return False
        u=i/steps
        # smoothstep
        e=u*u*(3.0-2.0*u)
        x=round(sx+(tx-sx)*e)
        y=round(sy+(ty-sy)*e)
        cc_move_abs(x,y)
        time.sleep(duration/steps)

    cc_move_abs(tx,ty)
    time.sleep(0.15)

    # Generate genuine relative movement events at the final location. These
    # return to the same coordinate and make hover-sensitive UI register.
    if os.name=="nt":
        ME_MOVE=0x0001
        for dx,dy in ((-4,0),(8,0),(-4,0),(0,-3),(0,6),(0,-3)):
            ctypes.windll.user32.mouse_event(ME_MOVE,dx,dy,0,0)
            time.sleep(0.045)
    else:
        for dx,dy in ((-4,0),(8,0),(-4,0),(0,-3),(0,6),(0,-3)):
            pyautogui.moveRel(dx,dy,duration=0.045)

    cc_move_abs(tx,ty)
    time.sleep(0.20)
    ax,ay=cc_cursor_pos()
    print(f"[RECOVERY/MOUSE] requested=({tx},{ty}) actual=({ax},{ay})")
    return abs(ax-tx)<=5 and abs(ay-ty)<=5

def cc_click(clicks=1):
    """Click the current physical cursor position without moving it."""
    for i in range(clicks):
        if not recovery_pause_gate():
            return False
        if os.name=="nt":
            ctypes.windll.user32.mouse_event(0x0002,0,0,0,0)
            time.sleep(0.10)
            ctypes.windll.user32.mouse_event(0x0004,0,0,0,0)
        else:
            pyautogui.mouseDown(button="left")
            time.sleep(0.10)
            pyautogui.mouseUp(button="left")
        if i+1<clicks:
            time.sleep(0.14)
    return True


def cc_match(template_name,threshold=0.70,region=None,scales=_CC_SCALES):
    """MSS two-stage match returning physical virtual-desktop x,y."""
    tmpl0 = TEMPLATES.get(template_name)
    if tmpl0 is None:
        print(f"[MSS] Missing loaded template: {template_name}")
        return None
    vx,vy,vw,vh=cc_virtual_screen()
    if region is None:
        left,top,right,bottom=vx,vy,vx+vw,vy+vh
    else:
        left,top,right,bottom=map(int,region)
    if right<=left or bottom<=top: return None
    with mss.MSS() as sct:
        shot=np.asarray(sct.grab({"left":left,"top":top,"width":right-left,"height":bottom-top}))
    gray=cv2.cvtColor(shot,cv2.COLOR_BGRA2GRAY)
    gh,gw=gray.shape
    gray_small=None
    best=None
    for sc in scales:
        tw=max(1,int(round(tmpl0.shape[1]*sc)))
        th=max(1,int(round(tmpl0.shape[0]*sc)))
        if tw>gw or th>gh: continue
        tmpl=cv2.resize(tmpl0,(tw,th),interpolation=cv2.INTER_AREA) if sc!=1.0 else tmpl0
        small=cv2.resize(tmpl,None,fx=0.5,fy=0.5,interpolation=cv2.INTER_AREA)
        if min(small.shape)>=8:
            if gray_small is None:
                gray_small=cv2.resize(gray,None,fx=0.5,fy=0.5,interpolation=cv2.INTER_AREA)
            res=np.nan_to_num(cv2.matchTemplate(gray_small,small,cv2.TM_CCOEFF_NORMED))
            _,coarse,_,loc=cv2.minMaxLoc(res)
            if coarse<_CC_COARSE_GATE: continue
            x0=max(loc[0]*2-6,0); y0=max(loc[1]*2-6,0)
            x1=min(x0+tw+12,gw); y1=min(y0+th+12,gh)
            win=gray[y0:y1,x0:x1]
            if win.shape[0]<th or win.shape[1]<tw: continue
            res=np.nan_to_num(cv2.matchTemplate(win,tmpl,cv2.TM_CCOEFF_NORMED))
            _,score,_,loc2=cv2.minMaxLoc(res)
            px=x0+loc2[0]; py=y0+loc2[1]
        else:
            res=np.nan_to_num(cv2.matchTemplate(gray,tmpl,cv2.TM_CCOEFF_NORMED))
            _,score,_,loc2=cv2.minMaxLoc(res)
            px,py=loc2
        if best is None or score>best[2]:
            best=(left+px+tw//2,top+py+th//2,float(score))
    return best if best and best[2]>=threshold else None

def cc_click_template(template_name,threshold=0.68,timeout=45.0,region=None,
                      next_template=None,next_threshold=0.62,settle=0.8,clicks=1):
    """Find -> glide -> click -> verify next screen/control before continuing."""
    end=time.monotonic()+timeout
    while time.monotonic()<end and not shutdown.is_set():
        if restart_requested.is_set(): raise RestartCycle
        if not recovery_pause_gate(): return False
        hit=cc_match(template_name,threshold,region)
        if not hit:
            time.sleep(0.15); continue
        time.sleep(0.20)
        hit2=cc_match(template_name,threshold,region)
        if not hit2: continue
        x,y,score=hit2
        print(f"[RECOVERY/MSS] {template_name} -> ({x},{y}) score={score:.3f}")
        if not cc_glide_to(x,y): return False
        if not cc_click(clicks): return False
        if not pause_aware_sleep(settle): return False
        if next_template:
            verify_end=min(end,time.monotonic()+15.0)
            while time.monotonic()<verify_end:
                if not recovery_pause_gate(): return False
                nxt=cc_match(next_template,next_threshold)
                if nxt:
                    time.sleep(0.20)
                    if cc_match(next_template,next_threshold):
                        print(f"[RECOVERY/MSS] confirmed next: {next_template}")
                        return True
                time.sleep(0.15)
            print(f"[RECOVERY/MSS] next control {next_template} not confirmed; retrying {template_name}")
        else:
            if cc_match(template_name,threshold,region) is None:
                return True
            print(f"[RECOVERY/MSS] {template_name} still visible; retrying.")
    return False


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
            global home_watchdog_suppress_until
            home_watchdog_suppress_until = time.monotonic() + 12.0
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
    Fast detector for the user's clean 518x50 "Catch up with Zen'in Elite" crop.
    This runs before result-screen scans so the short-lived objective is not missed.
    """
    sw, sh = pyautogui.size()
    hit = best_match(
        "catch_up.png",
        threshold=0.66,
        region=(int(sw*0.20), int(sh*0.16), int(sw*0.80), int(sh*0.40)),
        scales=(0.88,0.94,0.98,1.0,1.02,1.06,1.12),
    )
    if hit:
        x,y,score=hit
        print(f"[CHASE] Catch-up DETECTED at ({x},{y}) score={score:.3f}")
        return True
    return False



def raid_result_visible():
    """Check for the user's real failure/success raid-summary screens."""
    check_restart()

    if failure_summary_visible():
        return "failure"
    if success_summary_visible():
        return "success"

    # Keep Next only as a generic fallback; it no longer decides success/failure.
    sw,sh=pyautogui.size()
    next_region=(int(sw*0.30),int(sh*0.60),int(sw*0.70),int(sh*0.86))
    hit=best_match(
        "next_button.png", threshold=0.72, region=next_region,
        scales=(0.86,0.92,0.96,1.0,1.04,1.10,1.18),
    )
    if hit:
        time.sleep(0.10)
        hit2=best_match(
            "next_button.png", threshold=0.72, region=next_region,
            scales=(0.86,0.92,0.96,1.0,1.04,1.10,1.18),
        )
        if hit2:
            print(f"[RESULT] Generic result screen detected via Next score={hit2[2]:.3f}")
            return "result"
    return None



def phase1_spam_until_catchup():
    """Spam abilities, prioritising the short-lived catch-up objective."""
    print("[PHASE 1] Spamming R/F/C/X; monitoring catch-up + death.")
    remaining=float(PHASE_TIMEOUT)
    last_tick=time.monotonic()

    while remaining > 0 and not shutdown.is_set():
        check_restart()
        if not active.is_set():
            if not wait_until_active():
                return None
            last_tick=time.monotonic()
            continue

        now=time.monotonic()
        remaining -= now-last_tick
        last_tick=now

        for key in ("r","f","c","x"):
            check_restart()
            if shutdown.is_set() or not wait_until_active():
                return None

            # IMPORTANT: catch-up is brief. Scan it BEFORE the much heavier
            # result/death matching and transition immediately on a clean hit.
            if catchup_visible():
                release_keys()
                print("[CHASE] Catch-up confirmed - stopping Phase 1 immediately.")
                return "catchup"

            # During active combat only Failure is relevant. Do not scan the
            # Successful summary here; it previously generated false positives.
            if failure_summary_visible():
                release_keys()
                print("[PHASE 1] Failure summary detected during spam.")
                return "failure"

            pydirectinput.press(key)
            if not pause_aware_sleep(SKILL_INTERVAL):
                return None

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
    """Detect the user's full Raid Summary: Failure screenshot, persistently."""
    hit=best_match(
        "failure_summary.png",
        threshold=0.72,
        region=None,
        scales=(0.90,0.94,0.97,1.0,1.03,1.06,1.10),
    )
    if not hit:
        return False
    time.sleep(0.12)
    hit2=best_match(
        "failure_summary.png",
        threshold=0.72,
        region=None,
        scales=(0.90,0.94,0.97,1.0,1.03,1.06,1.10),
    )
    if hit2:
        print(f"[RESULT] Failure summary CONFIRMED score={hit2[2]:.3f}")
        return True
    return False


def success_summary_visible():
    """Detect the user's full Raid Summary: Successful screenshot, persistently."""
    hit=best_match(
        "success_summary.png",
        threshold=0.72,
        region=None,
        scales=(0.90,0.94,0.97,1.0,1.03,1.06,1.10),
    )
    if not hit:
        return False
    time.sleep(0.12)
    hit2=best_match(
        "success_summary.png",
        threshold=0.72,
        region=None,
        scales=(0.90,0.94,0.97,1.0,1.03,1.06,1.10),
    )
    if hit2:
        print(f"[RESULT] Success summary CONFIRMED score={hit2[2]:.3f}")
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

    # Recenter once with middle mouse after Ready.
    print("[CYCLE] Ready clicked. Pressing middle mouse button once to recenter.")
    pyautogui.mouseDown(button="middle")
    time.sleep(0.10)
    pyautogui.mouseUp(button="middle")
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


def recovery_pause_gate():
    """Make every recovery step obey F6 without losing its current step."""
    while not active.is_set() and not shutdown.is_set():
        if restart_requested.is_set():
            raise RestartCycle
        time.sleep(0.05)
    return not shutdown.is_set()


def windows_cursor_to(x, y, duration=0.55):
    """
    Move to a point returned by template matching.

    Template coordinates come from the screenshot. Convert them explicitly to
    the Windows desktop coordinate space before moving. This also handles a
    machine where display scaling still causes screenshot and desktop sizes to
    differ despite DPI-awareness.
    """
    sx, sy = int(x), int(y)

    shot = pyautogui.screenshot()
    shot_w, shot_h = shot.size

    if os.name == "nt":
        desk_w = ctypes.windll.user32.GetSystemMetrics(0)
        desk_h = ctypes.windll.user32.GetSystemMetrics(1)
    else:
        desk_w, desk_h = pyautogui.size()

    tx = round(sx * desk_w / shot_w)
    ty = round(sy * desk_h / shot_h)

    print(
        f"[CURSOR] screenshot={shot_w}x{shot_h}, desktop={desk_w}x{desk_h}, "
        f"target screenshot=({sx},{sy}) -> desktop=({tx},{ty})"
    )

    try:
        if os.name == "nt":
            pt = __import__("ctypes.wintypes", fromlist=["POINT"]).POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            start_x, start_y = pt.x, pt.y
        else:
            pos = pyautogui.position()
            start_x, start_y = pos.x, pos.y

        steps = max(12, int(duration / 0.02))
        for i in range(1, steps + 1):
            if not recovery_pause_gate():
                return False
            nx = round(start_x + (tx - start_x) * i / steps)
            ny = round(start_y + (ty - start_y) * i / steps)
            if os.name == "nt":
                ctypes.windll.user32.SetCursorPos(nx, ny)
            else:
                pyautogui.moveTo(nx, ny)
            time.sleep(duration / steps)

        if os.name == "nt":
            ctypes.windll.user32.SetCursorPos(tx, ty)
        else:
            pyautogui.moveTo(tx, ty)
        time.sleep(0.18)
        return True
    except Exception as exc:
        print(f"[CURSOR] Physical move failed: {exc}")
        pyautogui.moveTo(tx, ty, duration=duration)
        return True



def recovery_click(template_name, threshold=0.64, timeout=45.0, region=None):
    return cc_click_template(template_name, threshold, timeout, region, settle=0.85)


def click_gamemodes_verified(timeout=90.0, initial_load_wait=6.0):
    """Click the correctly cropped Gamemodes control and verify Raids appears."""
    print(f"[RECOVERY] Waiting {initial_load_wait:.1f}s for main menu.")
    if not pause_aware_sleep(initial_load_wait):
        return False
    print("[RECOVERY] Finding the actual Gamemodes button (corrected source-image template).")
    return cc_click_template(
        "gamemodes_button.png", 0.72, timeout, None,
        next_template="raids_button.png", next_threshold=0.70,
        settle=0.8, clicks=1
    )


def click_raids_verified(timeout=30.0):
    """Click the correctly cropped Raids control and verify the raid browser opens."""
    print("[RECOVERY] Finding the actual Raids button (corrected source-image template).")
    return cc_click_template(
        "raids_button.png", 0.72, timeout, None,
        next_template="create_tab.png", next_threshold=0.68,
        settle=0.8, clicks=1
    )


def recovery_click_once(template_name, threshold=0.68, timeout=30.0, settle=0.65):
    """Click a toggle/selection once; do not require that its graphic disappears."""
    end=time.monotonic()+timeout
    while time.monotonic()<end and not shutdown.is_set():
        if restart_requested.is_set():
            raise RestartCycle
        if not recovery_pause_gate():
            return False
        hit=cc_match(template_name,threshold)
        if not hit:
            time.sleep(0.15)
            continue
        time.sleep(0.20)
        hit=cc_match(template_name,threshold)
        if not hit:
            continue
        x,y,score=hit
        print(f"[RECOVERY/MSS] {template_name} CLICK CENTER -> ({x},{y}) score={score:.3f}")
        if not cc_glide_to(x,y):
            return False
        if not cc_click(1):
            return False
        return pause_aware_sleep(settle)
    print(f"[RECOVERY] Timed out finding {template_name}.")
    return False



def click_blue_play_verified(timeout=60.0):
    end=time.monotonic()+timeout
    while time.monotonic()<end and not shutdown.is_set():
        if restart_requested.is_set(): raise RestartCycle
        if not recovery_pause_gate(): return False
        hit=cc_match("play_button.png",0.90)
        if not hit:
            time.sleep(0.15); continue
        time.sleep(0.20)
        hit=cc_match("play_button.png",0.90)
        if not hit: continue
        x,y,score=hit
        # play_button.png is now the user's clean button-only screenshot.
        # cc_match() already returns the physical center of that matched button.
        print(f"[RECOVERY/MSS] Play exact center -> ({x},{y}) score={score:.3f}")
        if not cc_glide_to(x,y): return False
        # Calamity Cleaver uses repeated Play clicks; use 3 here.
        if not cc_click(3): return False
        if not pause_aware_sleep(2.0): return False
        if cc_match("play_button.png",0.90) is None:
            print("[RECOVERY/MSS] Play click confirmed.")
            return True
        print("[RECOVERY/MSS] Play still visible; retrying.")
    return False



def recover_from_disconnect(start_from_home=False):
    """
    Recover from the supplied Roblox disconnect/error flow:
    Leave -> Play -> Gamemodes -> Raids -> Create -> Projection ->
    Calamity -> Friends Only -> Modifiers -> Weaken -> Hardcore ->
    Create -> Start -> Ready.
    """
    recovery_in_progress.set()
    release_keys()
    print("[RECOVERY] Disconnect/error detected. Rebuilding the raid lobby.")

    try:
        # Determine which supplied error screen is currently visible.
        sw, sh = pyautogui.size()
        failed279 = best_match(
            "connection_failed_popup.png",
            threshold=0.68,
            region=(int(sw*0.25), int(sh*0.20), int(sw*0.75), int(sh*0.75)),
            scales=(0.72, 0.82, 0.90, 1.0, 1.10, 1.22, 1.35),
        )

        if start_from_home:
            print("[RECOVERY] Already on Roblox experience page; skipping Cancel/Leave.")
        elif failed279:
            # "Connection Failed" / Error Code 279 is already on the Roblox
            # experience page. Cancel dismisses it; then use the blue Play button.
            print("[RECOVERY] Connection Failed / Error 279 detected.")
            if not recovery_click("cancel_button.png", 0.60, 20.0):
                return False
            if not pause_aware_sleep(0.75):
                return False
        else:
            # In-game "Disconnected" dialog: Leave returns to experience page.
            if not recovery_click("leave_button.png", 0.62, 20.0):
                return False
            if not pause_aware_sleep(0.75):
                return False

        # Roblox experience page. Use the dedicated slow-move + verified
        # click routine because this page handles mouse input differently from
        # the in-game Roblox UI.
        if not click_blue_play_verified(60.0):
            return False

        # Main menu -> Gamemodes -> Raids. Gamemodes uses a restricted
        # search band so the Start button cannot be mistaken for it.
        if not click_gamemodes_verified(90.0, initial_load_wait=6.0):
            return False
        if not pause_aware_sleep(1.25):
            return False
        if not click_raids_verified(30.0):
            return False

        # Raid browser -> Create tab -> Projection.
        if not cc_click_template("create_tab.png", 0.70, 30.0, None, next_template="projection_card.png", next_threshold=0.68):
            return False
        if not cc_click_template("projection_card.png", 0.68, 30.0, None, next_template="calamity_button.png", next_threshold=0.66):
            return False

        # Projection configuration.
        if not recovery_click_once("calamity_button.png", 0.68, 30.0):
            return False
        if not recovery_click_once("friends_only_button.png", 0.68, 20.0):
            return False
        if not recovery_click_once("modifiers_button.png", 0.68, 20.0):
            return False
        if not recovery_click_once("weaken_button.png", 0.66, 20.0):
            return False
        if not recovery_click_once("hardcore_button.png", 0.66, 20.0):
            return False

        # Click outside/onto Create after modifier selections; Create also
        # naturally dismisses the modifier popup in this UI.
        if not cc_click_template("create_raid_button.png", 0.68, 30.0, None, next_template="lobby_start_button.png", next_threshold=0.66, settle=0.45, clicks=2):
            return False

        # Raid lobby -> Start.
        if not recovery_click("lobby_start_button.png", 0.68, 60.0):
            return False

        # Start loads back to the existing Ready screen used by the macro.
        print("[RECOVERY] Start clicked. Waiting for the normal Ready screen.")
        end = time.monotonic() + 90.0
        while time.monotonic() < end and not shutdown.is_set():
            if not recovery_pause_gate():
                return False
            hit = best_match(
                "ready_button.png",
                threshold=0.60,
                region=None,
                scales=(0.70, 0.80, 0.90, 1.0, 1.10, 1.22, 1.35),
            )
            if hit:
                print("[RECOVERY] Ready screen found. Returning to normal macro.")
                return True
            time.sleep(0.30)

        print("[RECOVERY] Ready screen did not appear in time.")
        return False
    finally:
        recovery_in_progress.clear()


def controller():
    print("=" * 62)
    print(VERSION)
    print("F6 Start/Pause | F7 Emergency Stop | F8 Restart | F9 Mouse coordinates")
    print("=" * 62)

    while not shutdown.is_set():
        # v3.15: always initialize cycle result before recovery branches.
        ok = True
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
        except HomePageRecovery:
            print("[CONTROLLER] Home page detected - starting recovery from blue Play.")
            release_keys()
            try:
                recover_from_disconnect(start_from_home=True)
                continue
            except RestartCycle:
                recovery_in_progress = False
                continue
        except ConnectionRecovery:
            release_keys()
            print("[RECOVERY] Roblox connection/error popup detected.")
            try:
                recovered = recover_from_disconnect()
                continue
            except RestartCycle:
                recovery_in_progress.clear()
                restart_requested.clear()
                print("[HOTKEY] Restart accepted during recovery.")
                continue

            if recovered:
                print("[RECOVERY] Recovery complete. Resuming from Ready.")
                continue

            print("[RECOVERY] Automatic recovery failed. Macro PAUSED for safety.")
            active.clear()
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
