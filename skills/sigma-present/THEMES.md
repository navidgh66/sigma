# Themes

Named CSS-variable palettes + font pairings for `sigma-present` exports. Set the
`:root` variables in the template to switch theme. Pick **one** direction per
export — do not mix. Default is **Editorial Light**. Use dark only when asked.

Each theme defines: `--accent`, `--ink`, `--surface`, `--muted`, plus a font
pairing (display / body).

## Editorial Light (default)
Calm, magazine-like; serif body + grotesk display. Best for reports & research.
```css
--accent: oklch(62% 0.19 256);  /* indigo */
--ink:    oklch(20% 0 0);
--surface:oklch(99% 0 0);
--muted:  oklch(48% 0 0);
/* fonts: Space Grotesk (display) + Source Serif 4 (body) */
```

## Swiss Modern
High-contrast, grid-driven, neutral with one hot accent. Specs, blueprints.
```css
--accent: oklch(58% 0.24 27);   /* red */
--ink:    oklch(15% 0 0);
--surface:oklch(100% 0 0);
--muted:  oklch(45% 0 0);
/* fonts: Inter / Helvetica Neue (display + body) */
```

## Dark Luxe
Disciplined dark; restrained gold accent. Pitch decks, exec summaries.
```css
--accent: oklch(80% 0.13 85);   /* gold */
--ink:    oklch(95% 0 0);
--surface:oklch(18% 0.01 260);
--muted:  oklch(70% 0 0);
/* fonts: Space Grotesk + Source Serif 4 */
```

## Terminal / Data
Mono display, green/cyan accents on near-black. Verify results, MLOps dashboards.
```css
--accent: oklch(78% 0.16 165);  /* mint */
--ink:    oklch(92% 0 0);
--surface:oklch(16% 0.02 200);
--muted:  oklch(65% 0 0);
/* fonts: JetBrains Mono (display) + Inter (body) */
```

## Paper / Print
Warm off-white, ink-black, sober. Long reports meant to be printed to PDF.
```css
--accent: oklch(45% 0.12 250);
--ink:    oklch(22% 0.01 60);
--surface:oklch(98% 0.01 90);   /* warm paper */
--muted:  oklch(50% 0.01 60);
/* fonts: Source Serif 4 (display + body) */
```

## Theme selection guidance

| Artifact | Suggested theme |
|----------|-----------------|
| research.md | Editorial Light / Paper |
| spec.md, architecture.md | Swiss Modern |
| plan, tasks.md | Editorial Light |
| verify results | Terminal / Data |
| board.md (kanban) | Editorial Light or Terminal |
| pitch / exec deck | Dark Luxe |

Wire `--accent` into Chart.js dataset colors so charts match the page. Keep
contrast WCAG AA: check `--ink` on `--surface` and `--accent` on `--surface`.
