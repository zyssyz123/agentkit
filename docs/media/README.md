# Media assets

## Recording `demo.gif`

`demo.gif` is rendered from `demo.tape` via [VHS](https://github.com/charmbracelet/vhs).

### One-shot

```bash
# install vhs (macOS)
brew install vhs        # or: go install github.com/charmbracelet/vhs@latest

# render
cd docs/media
vhs demo.tape           # writes docs/media/demo.gif
```

### Tips

* Run `uv sync && source .venv/bin/activate` in the repo root *before*
  launching `vhs` so the `aglet` CLI is on `PATH`.
* To re-shoot a shorter/longer version, tweak `Set PlaybackSpeed` or the
  `Sleep` calls in `demo.tape` and re-run.
* The README references `docs/media/demo.gif` via a relative link, so the
  moment you commit the rendered gif it will show up on both GitHub and PyPI.
