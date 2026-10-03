Zen'in Elite Macro v1.4

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


v1.4 fixes
----------
- UI clicks now move the mouse first, verify it reached the detected button,
  wait an additional settle period, and only then click.
- Immediately after Ready is clicked, CTRL is pressed twice to recenter.
- Catch-up detection now searches the top-center objective area over many more
  scales and uses a lower template threshold.
- "Catch up with Zen'in Elite" requires two confirmations before stopping,
  reducing false positives while checking frequently enough not to miss it.
- Skill spam is released immediately when catch-up is confirmed.


v1.4 Ready + catch-up fixes
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


v1.4 Roblox mouse-input fix
---------------------------
- Replaced PyAutoGUI mouse movement for clickable UI with PyDirectInput movement.
- After moving to a detected button, the macro sends a +3/-3 pixel DirectInput
  wiggle and finishes at the exact target. This forces Roblox to receive a
  mouse-motion/hover update rather than only seeing the Windows cursor teleport.
- The actual click remains DirectInput mouse-down / mouse-up with deliberate timing.
- Applied to Ready, Next, Close, and Retry.
- Ready still verifies that the Ready UI disappears before continuing.


v1.4 timing adjustment
----------------------
- Added an extra 1.0 second after detecting "Chase took too long...".
- Total transition wait is now 1.70 seconds before the second 2 -> Z -> 1 sequence.
