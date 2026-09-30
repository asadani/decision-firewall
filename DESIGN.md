---
version: alpha
colors:
  background: '#edf2f7'
  surface: '#ffffff'
  text: '#172d43'
  muted: '#52667b'
  primary: '#175ec4'
  success: '#17664d'
  warning: '#82500a'
  danger: '#a02c3d'
typography:
  display:
    fontFamily: 'Bahnschrift, Segoe UI, sans-serif'
  body:
    fontFamily: 'Segoe UI, Arial, sans-serif'
  data:
    fontFamily: 'Consolas, monospace'
rounded:
  panel: '10px'
  control: '6px'
spacing:
  panel: '24px'
  page: '40px'
components:
  panel:
    backgroundColor: '{colors.surface}'
    textColor: '{colors.text}'
  primaryButton:
    backgroundColor: '{colors.primary}'
---

# Decision Firewall inspector

## Overview

Product/admin register for a local engineer and reviewer. Think of a transaction investigation desk: a readable ledger, a clearly separated review decision, and evidence that follows the action. The signature is the intent-to-consequence timeline, not a decorative hero.

## Colors

Slate surfaces and a blue action color. Green means successful or permitted; amber means review/evidence/uncertainty; red means denial/failure. Text always names the state. Runtime token owner: `src/decision_firewall/static/app.css` `:root`; this document records the matching normative palette. Change both together. No dark theme in v0.1.

## Typography

Bahnschrift gives headings a restrained instrument-panel character. Segoe UI supports legible Windows forms. Consolas identifies machine IDs and evidence payloads. Fonts are local; no network dependency. Base body is 15px with 1.6 line height; text reflows at browser zoom.

## Layout

Desktop: 220px navigation and a naturally scrolling content region. The request detail uses an evidence column and an event timeline. At 1000px, detail becomes one column; below 700px, navigation becomes horizontal and filters stack. Tables own horizontal overflow; forms never inherit a fixed viewport height.

## Elevation & Depth

Flat bordered panels; no decorative shadows. Hierarchy comes from grouping and whitespace.

## Shapes

10px panels and 6px controls. Status badges are compact rounded rectangles. Use a circular marker only for timeline events.

## Components

Shared base template, panels, notices, tables, labels, buttons, badges, and timeline styles. Loading feedback uses stable inline status text and disabled submit buttons. Native select behavior is accepted. Scrollbars are globally styled through standard properties plus engine fallback.

## Do's and Don'ts

Keep simulated-money labels visible. Preserve explicit unknown values and original evidence. Do not call approval execution, hide critical errors in a toast, infer safety from color, or style unknown as successful. Respect reduced motion and forced colors. Keyboard focus must remain visible.

## Documentation architecture illustration

The framework illustration is a separate documentation surface; the inspector tokens above remain unchanged. Its canonical token and layout owner is `scripts/render-framework.mjs`, generating opaque light/dark SVGs and a standalone HTML walkthrough. Use slate backgrounds, blue lifecycle emphasis and amber bound authorization. All meanings have text labels. Local Segoe UI/Bahnschrift fonts match the inspector. Six numbered stages provide the signature; animation is user-initiated and limited to a current connector, with reduced-motion support. The README selects a static asset for the reader's color scheme. On narrow screens the diagram owns horizontal scrolling and descriptions reflow below it.


## Repository mark

`docs/brand/icon.png` is the generated slate/blue/amber project icon. It uses the architecture palette and depicts input, authorization gate and audit record. Preserve its square aspect ratio and opaque background; the README uses 96 pixels. Asset provenance and the refinement prompt are recorded in `docs/brand/README.md`.
