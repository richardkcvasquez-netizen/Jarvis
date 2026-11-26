# ADR-0048 — The Sentinel Ring glows through the desktop

**Status:** Accepted · **Date:** 2026-11-26

## Context

The Sentinel Ring replaces the voice orb, both in the app and in the floating
desktop window. In the app it is a look (docs/looks.md) and draws on a
transparent canvas. The desktop window makes itself transparent with a
colour key: one exact colour (magenta) becomes see-through, so every pixel is
either fully see-through or fully solid. The grey orb lives with that by
keeping a hard circular edge.

The Sentinel Ring is mostly soft glow, sparks and fine lines floating in empty
space. Under a colour key every half-transparent pixel of that glow would
blend with magenta and show up as a pink fringe.

## Decision

1. **Per-pixel transparency first.** Where the system supports it, the desktop
   window shows the ring with real per-pixel alpha (on Windows the layered
   window the Jarvis Bar already uses, `dodaios/ui/dodaiosbar/win_layered.py`;
   on macOS the existing RGBA layer), so the glow fades into whatever is
   behind it.
2. **A dark backdrop as the safety net.** Where per-pixel alpha is not
   available, or keeps failing at runtime (30 refused frames in a row), the
   ring is drawn on a dark disc with a hard edge, which keeps working under
   the colour key.
3. **The colour key stays for every other look the window shows.** This
   decision does not move the Jarvis Bar or the dictation modes.

## Considered options

- **Dark backdrop only.** Safe, but the ring then reads as a badge rather
  than a hologram, which defeats the point of the look.
- **Hard pixels.** No soft glow at the edges; lines and nodes look jagged.
- **Hosting the web page in the desktop window.** Tried before for the orb
  (see `ui/orb/overlay.py`); WebView2 composites through DirectComposition and
  left an opaque box.

## Consequences

The desktop window now has two transparency paths, and both need tests. A
future reader who finds a layered alpha window next to a colour-key window
should not merge them: the colour key cannot carry the glow.
