# Architecture illustrations

The README uses `framework.svg` in light mode and `framework-dark.svg` in dark mode. Both have opaque backgrounds, readable independently of the page theme. GitHub embeds are static images; they cannot run an interactive walkthrough.

Download and open [framework.html](framework.html) locally for the standalone walkthrough. It uses no server, external fonts, network requests or runtime credentials. Choose a lifecycle step, use Previous/Next, or select Play flow. Playback stops at the last step and when the page is hidden; Pause and Reset remain available. Reduced-motion preferences disable moving connectors. The diagram is an illustration, not a live execution trace.

## Edit and reproduce

`scripts/render-framework.mjs` owns the framework layout, light/dark tokens and walkthrough copy. Its output is deterministic. Edit this source rather than the generated SVG/HTML files:

```sh
node scripts/render-framework.mjs
```

[framework.mmd](framework.mmd) remains the editable Mermaid topology for conventional diagram tools. Keep its relationships aligned with the illustration when changing architecture; it is not the source of the custom SVG layout. The custom renderer emphasizes the same trust boundaries and includes reference deployment examples.

To regenerate all diagrams, install the locked documentation dependencies and run:

```sh
npm ci
npm run diagrams
```

Other diagrams continue to render from their Mermaid sources. This visual refresh changes no runtime behavior or benchmark claims. The illustrated dispatch path is conditional: denial, missing evidence, errors, unresolved review and stale authorization prevent progression. Review and model assessments cannot independently authorize execution. Audit records cover the lifecycle; the audit panel's arrow does not imply that only final outcomes are recorded.

Check the walkthrough with `npm run check:framework-diagram`. The check uses installed Chrome on Windows and Playwright Chromium elsewhere (`npx playwright install chromium`). It exercises light/dark accessibility, text fit, keyboard navigation, playback, reduced motion and narrow-screen scrolling.
