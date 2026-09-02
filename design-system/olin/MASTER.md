# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Olin
**Generated:** 2026-07-28 10:41:24
**Reviewed against the Olin brand:** 2026-07-28
**Category:** B2B Service
**Design Dials:** Variance 6/10 (Balanced / Modern) | Motion 4/10 (Standard) | Density 4/10 (Standard)

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `#071310` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Secondary | `#0C5A45` | `--color-secondary` |
| Accent/CTA | `#C9FF52` | `--color-accent` |
| Background | `#F4F6F0` | `--color-background` |
| Foreground | `#071310` | `--color-foreground` |
| Muted | `#65736C` | `--color-muted` |
| Border | `#CFD8D2` | `--color-border` |
| Destructive | `#C7433F` | `--color-destructive` |
| Ring | `#0C5A45` | `--color-ring` |

**Color Notes:** Olin is institutional, warm and legible: obsidian and mineral green for trust, warm canvas for readability and lime only for actions or a single key signal. Never introduce generic fintech blue or purple gradients.

### Typography

- **Heading Font:** Inter, 650–750 weight, tight tracking
- **Body Font:** Inter
- **Data Font:** JetBrains Mono
- **Mood:** institutional credit infrastructure with human warmth; editorial hierarchy without decorative serif type
- **Google Fonts:** [Inter + JetBrains Mono](https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
```

### Spacing Variables

*Density: 4/10 — Standard*

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: #C9FF52;
  color: #071310;
  padding: 12px 24px;
  border-radius: 999px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: #071310;
  border: 1px solid #071310;
  padding: 12px 24px;
  border-radius: 999px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #FFFFFF;
  border-radius: 12px;
  padding: 24px;
  border: 1px solid #CFD8D2;
  box-shadow: none;
  transition: all 200ms ease;
  cursor: pointer;
}

.card:hover {
  border-color: #0C5A45;
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #0F172A;
  outline: none;
  box-shadow: 0 0 0 3px #0F172A20;
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Institutional editorial product system

**Keywords:** precise, evidence-led, warm, editorial, auditable, product-first, restrained motion, generous negative space

**Best For:** B2B SaaS mobile dashboards, fintech apps, developer tool mobile companions, marketing analytics apps, HR/operations apps, modern business productivity

**Key Effects:** 180–320ms opacity/translate transitions, one visual focal point per viewport, subtle grid texture, crisp borders, controlled product zooms. No decorative bobbing, pulsing badges or glassmorphism.

### Page Pattern

**Pattern Name:** Enterprise problem → mechanism → product proof → pilot

- **CTA Placement:** Above fold
- **Section Order:** Hero > structural problem > four-step mechanism > product proof > pilot > founder/company > CTA

---

## Motion

**Stagger List** (Standard) — Trigger: load or scroll | Duration: 220-360ms | Easing: `power3.out`

```js
gsap.from('.grid-item', { opacity: 0, y: 14, duration: 0.32, stagger: 0.045, ease: 'power3.out' });
```

**Framework notes:** grid: 'auto' lets GSAP infer rows/columns from a CSS grid layout for a natural wave stagger

- ✅ Use only where sequence clarifies the evidence flow
- ❌ Never stagger dense data tables or analyst decision controls
- ⚡ Group DOM writes; avoid interleaving layout reads (getBoundingClientRect) between staggered tweens

---

## Anti-Patterns (Do NOT Use)

- ❌ Playful design
- ❌ Hidden credentials
- ❌ AI purple/pink gradients
- ❌ Generic fintech blue
- ❌ Lime used as a large decorative field
- ❌ Repeated disclaimers in every section
- ❌ Product screenshots shrunk below readable size

### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile
