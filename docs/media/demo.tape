# VHS tape for the Aglet README hero gif.
#
# Setup:   brew install vhs   (or: go install github.com/charmbracelet/vhs@latest)
# Record:  cd docs/media && source ../../.venv/bin/activate && vhs demo.tape
# Output:  docs/media/demo.gif

Output demo.gif

Set Theme "Catppuccin Mocha"
Set FontSize 17
Set Width  1200
Set Height 720
Set Padding 20
Set TypingSpeed 45ms
Set PlaybackSpeed 1.0

# Fresh sandbox so the demo is reproducible.
Hide
Type "mkdir -p /tmp/aglet-demo && cd /tmp/aglet-demo && rm -rf demo && clear"
Enter
Sleep 300ms
Show

Type "# Aglet — every Agent capability is a swappable plugin."
Enter
Sleep 800ms

Type "aglet --version 2>/dev/null || python -c 'import aglet; print(aglet.__version__)'"
Enter
Sleep 1500ms

Type "aglet init demo"
Enter
Sleep 1500ms

Type "cat demo/agent.yaml | head -20"
Enter
Sleep 2500ms

Type "aglet run demo/agent.yaml --input 'hello, Aglet!'"
Enter
Sleep 4500ms

Type "# swap planner.echo -> planner.react in ONE line of YAML"
Enter
Sleep 1500ms

Type "sed -i '' 's/name: echo/name: react/' demo/agent.yaml && grep -A3 planner: demo/agent.yaml"
Enter
Sleep 3000ms

Type "# 9 Elements, 4 plugin runtimes, 26 PyPI packages"
Enter
Sleep 800ms
Type "# github.com/zyssyz123/agentkit"
Enter
Sleep 3000ms
