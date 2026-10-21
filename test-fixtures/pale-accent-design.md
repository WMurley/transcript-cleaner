# Lime Ledger — Style Reference
> Invented test theme: ink outlines on white with one pale highlighter accent.

**Theme:** mixed

A made-up design.md for tests. It exercises the reader's harder cases: a pale accent that cannot carry text, black ink borders, colour roles written with a slash, a condensed interface font, label-only letter-spacing ranges and a no-shadow rule.

## Tokens — Colors

| Name | Value | Token | Role |
|------|-------|-------|------|
| Highlighter Lime | `#c4f7a1` | `--color-highlighter-lime` | Primary action fill and active states only |
| Ink | `#111111` | `--color-ink` | Text and every border |
| Sheet | `#ffffff` | `--color-sheet` | Page and card surfaces |

## Tokens — Typography

### Archivo Narrow — Interface text, navigation, buttons and labels. Letter-spacing opens up on small caps labels. · `--font-archivo-narrow`
- **Substitute:** Arial Narrow
- **Weights:** 400, 600
- **Letter spacing:** 0.08em to 0.16em for small caps labels
- **Role:** UI chrome, navigation, buttons and labels. Narrow proportions keep labels compact.

### Lora — Display and section headlines in a light serif. · `--font-lora`
- **Substitute:** Georgia
- **Weights:** 300, 400
- **Role:** Display and hero headlines. A light serif voice for page titles.

## Tokens — Spacing & Shapes

**Density:** comfortable

### Border Radius

| Element | Value |
|---------|-------|
| cards | 18px |
| buttons | 18px |

### Layout

- **Card padding:** 24px
- **Element gap:** 12px

## Do's and Don'ts

### Don't
- Don't apply drop shadows to cards or buttons; borders carry the structure.
- Don't put text in the highlighter colour.

## Agent Prompt Guide

Quick Color Reference
- text: #111111
- background: #ffffff
- border: #111111
- accent / highlight: #c4f7a1
- primary action: #c4f7a1 (filled action)

## Quick Start

```css
:root {
  --font-archivo-narrow: 'Archivo Narrow', sans-serif;
  --font-lora: 'Lora', serif;
}
```
