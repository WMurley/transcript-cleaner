# Clay — Style Reference
> Invented test theme: warm cream paper, one terracotta accent, a serif display face over a tight sans.

**Theme:** light

A made-up design.md for tests. It exercises the reader's ordinary case: a warm off-white canvas, an accent dark enough to carry text, a serif heading font, a sans body font with negative tracking, generous radii and two soft shadows.

## Tokens — Colors

| Name | Value | Token | Role |
|------|-------|-------|------|
| Terracotta | `#b05a36` | `--color-terracotta` | Primary action buttons, links, active states and small labels |
| Cream | `#fef9ef` | `--color-cream` | Page canvas; never pure white |
| Biscuit | `#f5eee1` | `--color-biscuit` | Card and panel surfaces, one step deeper than the canvas |
| Sand | `#d1c9bf` | `--color-sand` | Hairline borders and dividers |
| Ink | `#2a2b2f` | `--color-ink` | Primary text and headings |
| Charcoal | `#333333` | `--color-charcoal` | Body copy and secondary text |
| Slate | `#515151` | `--color-slate` | Helper text and captions |

## Tokens — Typography

### Fraunces — Display and section headlines in a soft serif. Weight 400 for headlines, 300 for quieter titles. · `--font-fraunces`
- **Substitute:** Georgia
- **Weights:** 300, 400
- **Letter spacing:** normal
- **Role:** Display and section headlines in a soft serif.

### Inter — Body, navigation, buttons, labels and all interface text, with a consistent -0.023em tracking. · `--font-inter`
- **Substitute:** Arial
- **Weights:** 300, 400, 600, 700
- **Letter spacing:** -0.023em (about -0.37px at 16px)
- **Role:** Body, navigation, buttons, labels and all interface text.

## Tokens — Spacing & Shapes

**Density:** comfortable

### Border Radius

| Element | Value |
|---------|-------|
| cards | 24px |
| inputs | 9999px |
| buttons | 40px |

### Shadows

| Name | Value | Token |
|------|-------|-------|
| lg | `rgba(0, 0, 0, 0.15) 0px 0px 20px 0px` | `--shadow-lg` |
| xl | `rgba(42, 43, 47, 0.1) 12px 32px 80px 0px` | `--shadow-xl` |

### Layout

- **Card padding:** 24-32px
- **Element gap:** 16px

## Do's and Don'ts

### Do
- Set body and interface text in Inter with the -0.023em tracking.

### Don't
- Never use pure white (#ffffff) as a background.
- Don't introduce a second accent colour.

## Surfaces

| Level | Name | Value | Purpose |
|-------|------|-------|---------|
| 0 | Cream Canvas | `#fef9ef` | Page background |
| 1 | Biscuit | `#f5eee1` | Card and panel surfaces |
| 2 | Sand Outline | `#d1c9bf` | Bordered containers and dividers |

## Agent Prompt Guide

## Quick Color Reference
- text: #2a2b2f (Ink)
- background: #fef9ef (Cream)
- border: #d1c9bf (Sand)
- accent: #b05a36 (Terracotta)
- card surface: #f5eee1 (Biscuit)
- primary action: #b05a36 (filled action)

## Quick Start

```css
:root {
  --font-fraunces: 'Fraunces', serif;
  --font-inter: 'Inter', sans-serif;
  --color-terracotta: #b05a36;
  --color-cream: #fef9ef;
}
```
