# Goals — README hero GIF (VHS tape), refreshed for the current architecture.
# Story: a real goal with a readable building journey and executed proof that
# SURVIVES /clear. Adds beats the old marketing tape lacked: the building
# journey and executed-proof.
#
# Prereqs:  brew install vhs gifsicle
# Setup (run first, builds a REAL goal in /tmp/goals-demo with executed proof):
#   bash docs/marketing-refresh/assets/setup-demo.sh
# Render:   cd docs/marketing-refresh/assets && vhs goals-hero.tape
# Optimize: gifsicle -O3 --colors 128 goals-hero.gif -o goals-hero-opt.gif

Output goals-hero.gif
Output goals-hero.mp4

Set Shell "bash"
Set Theme "Catppuccin Mocha"
Set FontSize 16
Set Width 1200
Set Height 1100
Set Padding 20
Set Margin 40
Set MarginFill "#6B50FF"
Set BorderRadius 10
Set WindowBar Colorful
Set CursorBlink false
Set TypingSpeed 0.05
Set Framerate 24

# ---- Clean reproducible prompt (hidden setup) ----
Hide
Type "cd /tmp/goals-demo" Enter
Type "export PS1='$ '" Enter
Type "clear" Enter
Show

# ===== Beat 1: the hook =====
Type "# your agent forgets the plan the moment you /clear. goals doesn't." Sleep 1.5s Enter
Sleep 600ms

# ===== Beat 2: a real, in-progress goal with recorded proof =====
Type@70ms "goals check" Sleep 400ms Enter
Sleep 4s

# ===== Beat 3: the building journey — WHY, in plain words =====
Type "# why did it do that? read the building journey:" Sleep 800ms Enter
Type@70ms "goals assess journey" Sleep 400ms Enter
Sleep 4s

# ===== Beat 4: simulate a fresh session (/clear) =====
Type "# ----  new session: /clear, agent memory wiped  ----" Sleep 900ms Enter
Type "clear" Enter
Sleep 800ms

# ===== Beat 5: resolution — goal, phase, executed proof ALL still there =====
Type@70ms "goals check" Sleep 400ms Enter
Sleep 4.5s
Type "# goal, phases, executed proof: still here. durable. vendor-neutral." Sleep 1s Enter
Sleep 2.5s
