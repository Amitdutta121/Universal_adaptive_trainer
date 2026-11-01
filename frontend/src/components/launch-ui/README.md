# Launch UI (landing page only)

Primitives and sections adapted from [Launch UI](https://github.com/launch-ui/launch-ui)
(MIT, see `LICENSE.md`). Used only by the public landing page at `src/app/page.tsx`.

Kept separate from `components/ui` on purpose: the template's `Button` has its own variants
(`glow`) and look, and the Studio's shadcn button must not change.

Changes from upstream:

- `@radix-ui/react-*` imports switched to the `radix-ui` umbrella package the app already uses.
- `Sheet` and `DropdownMenu` come from `components/ui` instead of being duplicated.
- Colours come from the app's tokens: `--brand` maps to the Studio teal (`globals.css`).
- Sections live in `sections.tsx` with Adaptive Trainer copy instead of Launch UI's defaults.
