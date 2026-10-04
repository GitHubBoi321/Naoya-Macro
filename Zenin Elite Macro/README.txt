Zen'in Elite Macro v3.20

FLOW
1. Detect/click Ready.
2. Wait for Zen'in Elite boss arena.
3. Press 2, then Z, then 1.
4. Spam R, F, C, X.
5. Detect "Catch up with Zen'in Elite" and stop skill spam.
6. Detect the black "Chase took too long..." screen.
7. Press 2, Z, 1 again and resume R/F/C/X spam.
8. Detect raid result screen and stop spam.
9. Click Next.
10. Click Close on the rewards page.
11. Click Retry.
12. Repeat from Ready.

HOTKEYS
F6 = Start/Pause
F7 = Emergency Stop
F9 = Print current mouse coordinates

Run Setup_and_Run.bat the first time.
After dependencies are installed, Run_Macro.bat can be used directly.

The image templates in this folder were cropped from the reference screenshots
provided for this macro. Keep them in the same folder as the Python script.


v3.20 fixes
----------
- UI clicks now move the mouse first, verify it reached the detected button,
  wait an additional settle period, and only then click.
- Immediately after Ready is clicked, CTRL is pressed twice to recenter.
- Catch-up detection now searches the top-center objective area over many more
  scales and uses a lower template threshold.
- "Catch up with Zen'in Elite" requires two confirmations before stopping,
  reducing false positives while checking frequently enough not to miss it.
- Skill spam is released immediately when catch-up is confirmed.


v3.20 Ready + catch-up fixes
---------------------------
- Ready now has its own verified click routine.
- Cursor moves slowly to Ready, verifies its exact position, hovers for 0.55s,
  clicks while stationary, then checks that Ready actually disappeared.
- If Ready remains visible, the macro reacquires and retries instead of moving on.
- CTRL x2 still runs only after Ready has been confirmed clicked.
- catch_up.png was rebuilt from the newest supplied screenshot.
- Catch-up matching is restricted to the narrow center objective-message band,
  avoiding the boss name/health-bar area.
- Catch-up threshold raised and three consecutive confirmations are required.


v3.20 Roblox mouse-input fix
---------------------------
- Replaced PyAutoGUI mouse movement for clickable UI with PyDirectInput movement.
- After moving to a detected button, the macro sends a +3/-3 pixel DirectInput
  wiggle and finishes at the exact target. This forces Roblox to receive a
  mouse-motion/hover update rather than only seeing the Windows cursor teleport.
- The actual click remains DirectInput mouse-down / mouse-up with deliberate timing.
- Applied to Ready, Next, Close, and Retry.
- Ready still verifies that the Ready UI disappears before continuing.


v3.20 timing adjustment
----------------------
- Added an extra 1.0 second after detecting "Chase took too long...".
- Total transition wait is now 1.70 seconds before the second 2 -> Z -> 1 sequence.


v3.20 failure + true pause/resume
--------------------------------
- Added the supplied Raid Summary: Failure/death screenshot as a detector.
- On death/failure: stop skills -> click Next -> skip Close -> click Retry.
- Successful raid path remains: Next -> Close -> Retry.
- F6 is now cooperative pause/resume: pausing no longer returns False out of
  the current phase. Unpause continues the same function/step.
- Detection timeouts and scripted delays no longer count time spent paused.
- Any held/input state is released when paused, then the current loop continues
  naturally after F6 is pressed again.


v3.20 failure detection + restart hotkey
---------------------------------------
- Failure detection now uses a tighter "Raid Summary: Failure" heading template.
- Added a second fallback detector for the distinctive red Failure text.
- Failure flow remains: Next -> Retry.
- F8 now restarts the macro from the beginning/Ready screen from any cooperative
  phase, and also resumes it if it was paused.
- F6 remains pause/resume, F7 remains emergency stop, F9 prints mouse position.


v3.20 failure timing fix
-----------------------
- Failure detection now runs inside BOTH R/F/C/X spam loops.
- It checks for death immediately before every individual ability press.
- Death during phase 1 now goes directly to Next -> Retry.
- Death during phase 2 does the same.
- F8 restart remains enabled.


v3.20 automatic console cleanup
------------------------------
- Clears the CMD/console display every 10 minutes.
- Console clearing runs independently and does not alter raid progress.
- Version and hotkeys are reprinted after each automatic clear.


v3.20 Retry fix
--------------
- Rebuilt retry_button.png from the newly supplied post-failure screenshot.
- Failure path now waits 1 second after Next before looking for Retry.
- Retry has a dedicated detector for the long top-centre "Retry (0/1)" button.
- Uses DirectInput movement + hover + click and verifies Retry disappeared.
- If the first click does not register, it reacquires and retries.


v3.20 failure false-positive fix
-------------------------------
- Removed the red-pixel failure fallback entirely.
- Red Z/combat effects can no longer trigger failure just because the screen is red.
- Failure now requires the real Raid Summary: Failure heading AND the real Next button.
- The failure heading must persist across two screenshots before it is accepted.
- Generic result detection also requires the Next button to persist across two frames.


v3.20 disconnect/error recovery
------------------------------
- Watches for the supplied Roblox disconnect/error dialog during normal raid operation.
- On detection: Leave -> blue Play -> Gamemodes -> Raids -> Create -> Projection.
- Selects Calamity, Friends Only, Modifiers, Weaken, Hardcore, then Create.
- Clicks Start in the raid lobby and waits until the normal Ready screen returns.
- Recovery uses screenshot templates made from the supplied screenshots and the
  same DirectInput mouse movement/click method as the normal macro.
- If any recovery step cannot be found, the macro pauses for safety instead of
  blindly clicking.


v3.20 additional connection-error recovery
-----------------------------------------
- Added detection for the supplied "Connection Failed" / Error Code 279 screen.
- For Error 279: clicks Cancel, then blue Play, then follows the existing
  Gamemodes -> Raids -> Create -> Projection recovery route.
- The original in-game Disconnected screen still uses Leave -> blue Play.


v3.20 blue Play click fix
------------------------
- Blue Play now has its own click routine instead of using the in-game button routine.
- The cursor moves gradually onto Play so the Roblox experience page receives mouse-motion events.
- It pauses over the button before clicking.
- It first uses a normal Windows mouse click, then DirectInput as a fallback.
- The macro verifies that the Play button disappeared before continuing.
- If Play remains visible, it reacquires the button and retries instead of continuing incorrectly.


v3.20 Play coordinate + recovery pause fix
-----------------------------------------
- Blue Play is clicked at the exact detected centre using the Windows physical cursor API.
- Avoids PyAutoGUI/PyDirectInput coordinate scaling mismatch that moved above/left.
- Prints detected Play centre and actual cursor landing position for diagnosis.
- F6 now pauses the disconnect recovery itself, including while finding/clicking Play.
- F6 resumes from the same recovery step instead of recovery overriding the pause.


v3.20 Play-button coordinate scaling fix
---------------------------------------
- Enables Windows DPI awareness before importing screenshot/mouse libraries.
- Converts template-match screenshot coordinates to Windows desktop coordinates.
- Fixes the consistent above/left cursor offset caused by Windows display scaling.
- Removed the old verification code that could move the cursor back to the wrong raw coordinate.
- CMD now prints screenshot size, desktop size, detected target, converted target,
  and final Windows cursor position when clicking Play.
- F6 recovery pause behaviour from v2.4 is retained.


v3.20 Play-button nudge
----------------------
- After reaching the detected blue Play position, move another 55 px right
  and 22 px down before clicking.
- This nudge only affects the blue Play button during disconnect recovery.
- F6 pause/resume remains checked before and after the movement.


v3.20 Play click fix
-------------------
- Keeps the +55 px right / +22 px down Play-button nudge.
- After reaching the nudged location, sends an explicit Windows left click.
- Sends a second PyAutoGUI left click at the exact same location as fallback.
- No cursor movement occurs between the nudge and the click.
- F6 pause/resume remains respected before each click.


v3.20 recovery click fixes
-------------------------
- Keeps the known-good Play cursor position (+55 right / +22 down).
- Play now clicks with DirectInput first, then a normal click at the SAME spot.
- Gamemodes has a dedicated detector restricted to the lower main-menu band,
  preventing the Start button above it from being selected.
- Gamemodes must disappear after clicking before recovery advances to Raids.
- F6 pause/resume remains active during both routines.


v3.20 home-page recovery
-----------------------
- Existing Error 277 / Error 279 detection is unchanged.
- Added independent detection for the Roblox experience/home page using the
  blue Play button with persistent detection to reduce false positives.
- If the macro finds itself on that page directly, it starts recovery at:
  Play -> Gamemodes -> Raids -> Create -> Projection -> Calamity ->
  Friends Only -> Modifiers -> Weaken -> Hardcore -> Create -> Start -> Ready.
- It does not try to press Leave or Cancel when it was already on the home page.


v3.20 Waiting-for-Ready home-page fix
-------------------------------------
- Fixed the reason v2.9 could remain on "Waiting for Ready".
- The home-page detector had been placed in the wrong section of the script
  and was not participating in the normal watchdog.
- Blue Play detection now runs directly inside check_restart(), which the
  Ready waiting loop already calls continuously.
- HomePageRecovery is explicitly re-raised instead of being swallowed by the
  watchdog's generic exception handler.
- Play must be detected twice before home-page recovery starts.
- Existing Error 277 and Error 279 detection code is unchanged.


v3.20 HomePageRecovery crash fix
--------------------------------
- Fixed NameError: stop_all_inputs was referenced by the new home-page recovery
  handler even though that function does not exist in this macro.
- HomePageRecovery now uses the macro's existing safe input-release routine
  before starting recovery.
- The v3.0 Play detection while Waiting for Ready is retained.
- Existing Error 277 / Error 279 detection is unchanged.


v3.20 Play hover-registration fix
---------------------------------
- The cursor reaching Play was not enough: SetCursorPos can visually move the
  pointer without producing the normal mouse-move events the page uses for hover.
- After reaching Play (+55 right / +22 down), v3.20 now sends real relative
  Windows SendInput mouse movements around the same point and returns to the
  same position.
- It waits for the hover state, then sends a Windows SendInput left-down/up.
- No keyboard focus click or coordinate reset occurs before the Play click.
- Error 277/279 detection and home-page detection are unchanged.


v3.20 recovery timing / registration fix
----------------------------------------
- After Play is confirmed, waits 6 seconds for the Roblox game/main menu to load.
- Gamemodes must be detected twice before it is clicked.
- After clicking Gamemodes, the macro DOES NOT move on just because the
  Gamemodes image disappeared. It waits until the Raids button is visibly
  detected twice, proving the click registered and the next menu loaded.
- Adds another 1.25-second settle before clicking Raids.
- Generic recovery buttons now use stable detection and verify that the clicked
  control disappears before moving to the next input.
- Fixed direct-home recovery so it skips Cancel/Leave when already on Play.
- Error 277/279 detection itself is unchanged.


v3.20 Gamemodes coordinate fix
------------------------------
- Replaced gamemodes_button.png with a fresh crop from the newly supplied
  1919x1079 main-menu screenshot.
- Gamemodes search is now constrained to the left-side menu area.
- The detected screenshot coordinate is explicitly converted to Windows desktop
  coordinates before moving the physical cursor.
- Adds a small real relative hover movement at the final location.
- Does not advance until Raids is visibly detected after the click.


v3.20 Calamity Cleaver input/scanner port
-----------------------------------------
- Recovery screen scans now use MSS + OpenCV two-stage matching.
- Mouse movement now uses Windows SendInput ABSOLUTE | VIRTUALDESK coordinates.
- Uses the Calamity Cleaver curved glide and +/-3px arrival wiggle.
- Recovery clicks use SendInput left-down/up with a registration hold.
- Play uses the new movement system and three clicks, while retaining the
  established +55/+22 Play-only offset.
- Gamemodes uses the new MSS coordinate system directly and will not advance
  until Raids is visibly confirmed.
- Recovery steps use stable double detection and verification before advancing.
- Existing Error 277 / Error 279 detection logic is retained.


v3.20 hotfix
-----------
Fixed the v3.5 MSS scanner crash caused by an undefined template_path() helper. The MSS scanner now uses the templates already loaded into TEMPLATES.


v3.20 Gamemodes row-target fix
------------------------------
- Fixes the persistent Start-vs-Gamemodes confusion.
- Uses the supplied 1919x1079 main-menu geometry: Gamemodes is the row directly
  below Start (about 54 pixels lower at that resolution).
- If template matching lands on the Start-like row, the final mouse target is
  explicitly moved down one menu row and clamped to a Gamemodes-only Y band.
- The macro still refuses to continue until Raids is detected twice.


v3.20 mouse movement + MSS compatibility fix
--------------------------------------------
- Replaced deprecated mss.mss() with mss.MSS().
- Removed the fragile custom ctypes SendInput absolute-movement structure.
- Cursor movement now uses deterministic Windows SetCursorPos interpolation,
  followed by real relative mouse_event movements to register Roblox hover.
- Logs requested and actual final cursor coordinates.
- Gamemodes now has a 2-second scan fallback using the known center from the
  supplied 1919x1079 screenshot, so a failed template match cannot leave the
  mouse stationary forever.
- Raids still must be detected before the recovery sequence advances.


v3.20 Start/Gamemodes targeting correction
------------------------------------------
- Removed the virtual-screen scaling and Y-band clamping from Gamemodes.
- Treats the repeatedly detected Start-like row as the anchor.
- Final Gamemodes click is ALWAYS exactly 54 physical pixels below that match,
  matching the supplied 1919x1079 screenshot.
- Checks the real Windows cursor position before clicking and refuses to click
  if the pointer did not actually reach the lower row.
- Still requires Raids to appear twice before advancing.


v3.20 Raids coordinate fix (1920x1080)
---------------------------------------
- Raids no longer uses the bad template-match coordinate (695,446) for clicking.
- It clicks the user-confirmed physical coordinate (715,517) directly.
- The click is only considered successful when the Create tab on the next screen
  is detected twice.
- Template matching is retained for verification, not for choosing the Raids
  click coordinate.


v3.20 root-cause coordinate/template fix
-----------------------------------------
The problem was not Windows mouse coordinates. Several recovery PNGs had been
cropped using scaled preview coordinates instead of the original 1919x1079
screenshot coordinates. As a result:
- gamemodes_button.png actually contained Start
- raids_button.png contained only the Notice panel border/background
- create_tab.png actually contained Join
- several later controls were mostly blank background

v3.20 rebuilds all of those recovery templates directly from the original
1919x1079 screenshots. The matcher now returns the center of the ACTUAL control,
and that same physical coordinate is sent to the mouse. Fixed-coordinate hacks
for Gamemodes/Raids have been removed.

Persistent selection controls (Calamity, Friends Only, Modifiers, Weaken and
Hardcore) are clicked once instead of incorrectly requiring the button image to
disappear after selection.


v3.20 user-supplied template refresh
-------------------------------------
Replaced these templates directly with the new screenshots supplied by the user:
- disconnect_popup.png: full Error 277 popup
- leave_button.png: clean Leave button
- play_button.png: clean blue Play button
- failure_summary.png: full Raid Summary: Failure panel
- success_summary.png: restored full Raid Summary: Successful panel

Failure and success detection now match the full supplied summary panels instead
of treating failure_summary.png as a small heading crop. Both require a second
persistent match before being accepted.


v3.20 Play centering fix
-------------------------
Removed the old +55 X / +22 Y Play-button correction. That workaround belonged
to the previous badly cropped template. The clean Play screenshot supplied for
v3.12 is button-only, so its template-match center is now used directly.


v3.20 Create Raid double-click fix
-----------------------------------
Create Raid is now pressed twice at the same detected button location.
The first press closes the Modifiers menu; the second press activates Create.
The macro still verifies that the lobby Start button appears before continuing.


v3.20 controller recovery handoff fix
--------------------------------------
Fixed UnboundLocalError for `ok` after recovery finishes and control returns to
the main macro. `ok` is now initialized at the beginning of every controller
iteration, and completed disconnect/home-page recovery branches explicitly
continue into a fresh controller iteration instead of falling through to
`if not ok` with no raid-cycle result.


v3.20 false home-page watchdog fix
-----------------------------------
The normal raid cycle was being interrupted because gameplay falsely matched
the clean blue Play template at only ~0.605 confidence. The watchdog then
mistook the live game for the Roblox experience page and launched recovery.

- Home-page Play watchdog now requires 0.88 confidence.
- Recovery Play matching now requires 0.85 confidence.
- After Ready is successfully clicked, home-page Play detection is suppressed
  for 12 seconds while the arena transition begins.
- Error 277 and Error 279 detection remains active and unchanged.


v3.20 gameplay-vs-home-page detection fix
------------------------------------------
- Added raid_arena_hud.png from the user's actual post-Ready raid screenshot.
- Error 277/279 checks still happen first and are unchanged.
- If the Zen'in Elite boss HUD is visible, Play/home-page detection is skipped.
- Home-page Play now requires a persistent 0.90 match instead of 0.60.
- Recovery Play clicking also requires 0.90.
This prevents the bright raid UI from being mistaken for the simple blue Play icon.


v3.20 startup repair
---------------------
v3.18 was accidentally truncated immediately after the new middle-mouse input,
which made Python exit and the BAT show "Press any key to continue."

v3.20 is rebuilt from the complete v3.17 source and safely reapplies the
middle-mouse change, clean catch-up screenshot, and Phase-1 result guard.


v3.20 catch-up detection priority fix
--------------------------------------
The previous Phase 1 still called the full raid-result detector before checking
Catch Up, despite the intended v3.19 change. Those expensive scans could consume
the short Catch Up display and could also falsely identify Success.

v3.20 checks Catch Up FIRST before every R/F/C/X input and transitions on one
clean match. Success-summary scanning is completely disabled during Phase 1.
The clean user-supplied Catch Up template now uses a focused top-center region
and a 0.66 threshold.
