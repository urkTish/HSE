# Phase 0 design pass: UX findings

Scope: Phase 0 Foundation screens (login, privacy notice, invitation, forgot/reset password, app shell, projects, project settings, sites, zones, contractors, engagement tree, users & roles, audit log, profile). Dashboard is Phase 1 and was not touched.

Method: the app was run against the real backend and seed. I signed in as Faisal Al-Harbi (HSE Manager) and Ahmed Al-Zahrani (Contractor HSE Rep, RAWABI) and captured screenshots with Playwright: EN and AR, desktop (1366) and mobile (390). The "before" set is light mode only, because there was no dark mode before this pass. The "after" set has light and dark. WCAG contrast was computed with a script, not judged by eye.

Screenshots: `docs/screenshots/phase-0/design/before/` and `.../after/`, named `<screen>-<en|ar>-<desktop|mobile>-<light|dark>.png` (for example `projects-ar-mobile-light.png`). `drawer-*` shows the mobile navigation open. `rep-*` are taken as the contractor rep. To keep the repo small, only a representative subset is committed (login, projects, zone-detail, engagements, users, drawer).

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | On phones the project switcher overlaps the language switch, and the project name cannot be read | Every app screen on mobile; `before/projects-ar-mobile-light.png`, `before/zone-detail-en-mobile-light.png` | On phones the top bar is two rows: menu, language, theme, bell and user on the first row, a full-width project switcher (icon and chevron) on the second. Language shows as text only on phones | M | Done |
| 2 | High | On phones, tables squeeze into one word per line and scroll sideways, so rows cannot be read | All 8 tables; `before/projects-ar-mobile-light.png`, `before/users-en-mobile-light.png`, `before/engagements-ar-mobile-light.png` | Below 768 px each row becomes a card and every cell shows its column name (`TD label` → `data-label`). The first cell is the row title, with a 44 px link target. Desktop is unchanged | M | Done |
| 3 | High | On phones the filters push the records off the first screen (Users: 6 filters fill the whole screen) | Projects, contractors, users, audit log; `before/users-en-mobile-light.png` | `ListToolbar` shows the first filter (usually search). The others fold behind a "More filters" button (`aria-expanded`) below 1024 px. Desktop is unchanged | M | Done |
| 4 | High | Touch targets are under 44 px: buttons 36–40 px, inputs and selects 40 px, the dialog close button 16 px, menu items 36 px | All forms and dialogs | Control-height tokens: 44 px on touch and small screens, compact (40/36 px) only on a desktop with a mouse (`pointer: fine` and ≥ 1024 px). Dialog and drawer close buttons are 44 px | S | Done |
| 5 | High | No dark mode | Whole app | Light and dark token sets, a toggle (Light / Dark / Match device) in the top bar and on the auth pages, a no-flash boot script, and `color-scheme` set so native controls follow the theme | M | Done |
| 6 | High | Contrast fails AA: warning badge text 4.41:1, success badge 4.55:1 (marginal), form-control borders 1.53:1 (fails WCAG 1.4.11's 3:1) | Status badges, all inputs | New palette, checked in both themes. Body text ≥ 15:1, secondary text ≥ 6.5:1, status text on its tint ≥ 5.5:1 (readable in sunlight), control borders 3.6:1 (light) and 4.0:1 (dark), focus ring ≥ 5.6:1 | S | Done |
| 7 | Medium | Inputs use 14 px text, so iOS zooms the page when a field is focused | All forms on phones | Inputs, selects and textareas are 16 px below `lg`, 14 px on desktop | S | Done |
| 8 | Medium | The system font stack renders Arabic with mixed fallback fonts. Latin and Arabic metrics differ, so mixed lines look uneven | All AR screens | IBM Plex Sans (variable) and IBM Plex Sans Arabic, self-hosted through `@fontsource` (no CDN, works on locked-down site networks) | M | Done |
| 9 | Medium | Arabic is letter-spaced and upper-cased (sidebar section label, `tracking-tight` headings), and the line height is too tight for Arabic | `before/drawer-ar-mobile-light.png`, page titles | `:lang(ar)` resets letter-spacing and text-transform. Line height is 1.7 for AR and 1.5 for EN | S | Done |
| 10 | Medium | RTL mirroring is wrong: every sidebar icon was flipped although none is directional, and the engagement-tree connector `└` was not flipped | Sidebar, engagement tree in AR | Sidebar icons are no longer mirrored. The tree connector is mirrored in RTL. Chevrons and pagination arrows keep their mirroring | S | Done |
| 11 | Medium | Cells with `className="ltr"` would flip the whole stacked card to LTR in Arabic | Codes, emails, IPs in tables | `ltr` moved to an inner `<span>`, so only the code is isolated (rule 42 kept) | S | Done |
| 12 | Medium | The active nav item is shown by background only. The current project code is hard to spot. Profile is lost among the other items | Sidebar, `before/projects-en-desktop-light.png` | Active item has an inline-start indicator bar, bold text and a tinted icon. The project code sits in a chip. Profile is pinned to the bottom | S | Done |
| 13 | Medium | The mobile drawer has no visible close control, and the overlay is pure black | `before/drawer-ar-mobile-light.png` | 44 px close button in the drawer header. Overlay uses a token | S | Done |
| 14 | Low | Alert body text is in the status colour (amber or red paragraphs), which is harder to read and adds alarm | Info, warning and error alerts | Body text uses the foreground colour. The icon (20 px) and border carry the tone | S | Done |
| 15 | Low | Auth pages are a small card in empty space with no brand presence, and the "Forgot password" link is a small target | `before/login-en-desktop-light.png` | Brand band, theme toggle next to the language switch, card elevation, a 44 px link, tagline footer | S | Done |
| 16 | Low | Page titles (24 px) wrap to 3 lines on phones | `before/project-overview-en-mobile-light.png` | 20 px on phones, 24 px from `sm`, `text-balance` | S | Done |
| 17 | Low | Project tabs scroll on phones but are clipped by the page gutter. The 2 px active line is weak in sunlight | `before/engagements-ar-mobile-light.png` | Full-bleed scroll strip, 3 px active indicator, bold active label | S | Done |
| 18 | Low | Yes/No uses text glyphs (✓ ✕) | Zone airside card, project and user details | Lucide Check and X icons with text. "Yes" is in medium weight | S | Done |
| 19 | Low | Table headers wrap ("Project code" on two lines) and numbers do not align | All tables | `nowrap` 12 px semibold headers, `tabular-nums` in tables and on `<time>` | S | Done |
| 20 | Low | Unread notifications are marked only by a faint tint | Notifications popover | Inline-start bar and bold title, 44 px rows | S | Done |
| 21 | Low | The empty state is a bare line of text | Lists with no results | Icon and message in a dashed card | S | Done |
| 22 | Low | No reduced-motion handling | Global | `prefers-reduced-motion` disables transitions and animations | S | Done |
| 23 | Medium | Dates with the Hijri date beside them wrap mid-date in tables ("01 Jun 2025 · 5 Dhuʻl-Hijjah / 1446 AH") | Projects, engagements, users tables | Show the Hijri date as a muted second line. This needs the date formatter to return parts, and it touches every date display | L | Proposal P1 |
| 24 | Medium | On detail pages on phones, the status actions (suspend, close, archive) come after all the details, far down the page | Zone, site, contractor, user detail on mobile | A sticky bottom action bar on phones for the primary status actions | L | Proposal P2 |
| 25 | Low | The project switcher is a native select with long "code — name" options, which will not scale to many projects | Top bar | A searchable combobox with recent projects | L | Proposal P3 |
| 26 | Low | Cross-project lists format dates with the *current* project's display settings (frontend note in PROGRESS) | Projects, contractors and users lists | See proposal P4 | L | Proposal P4 |

Not changed on purpose:
- Red "destructive" buttons for archive, close project, deactivate and blacklist. These actions are hard to undo, so red is right. Status badges still use red only for blacklisted and failed.
- No business logic, API calls, permissions or data shown were changed. No e2e selectors were broken.
- Hijri month names with `ʻ` (U+02BB) render with a slight gap in IBM Plex. The text comes from ICU, so it was not changed.

## The design system (for every later phase)

- **One token file**: `frontend/src/styles/tokens.css`, mapped to Tailwind in `frontend/src/app/globals.css`. Components use tokens only. A grep for raw colours in components finds none.
- **Themes**: light is the default. Dark applies under `prefers-color-scheme: dark` unless the user picks Light, or always with `<html data-theme="dark">`. The choice is stored per device (`localStorage` key `hse.theme`), and a boot script applies it before first paint.
- **Colour roles**: background, surface, muted, foreground, muted-foreground, border (decorative), input (control border, ≥ 3:1), ring, primary, secondary, accent, destructive, overlay.
- **Safety semantics** (use sparingly, always with an icon and text): `danger` only for critical states (expired, blacklisted, LTI, stop-work); `warning` for expiring or at risk; `success` for valid; `info` for in progress; `neutral` for closed. Each has a text/tint pair (≥ 5.5:1). Solid colours for icons, dots and chart status marks: `--safety-ok`, `--safety-caution`, `--safety-serious`, `--safety-critical`.
- **Chart series palette** (Phase 1+): `--series-1..8`, colour-blind-safe in this fixed order, with separate light and dark steps. Checked with the data-viz palette validator: worst adjacent CVD ΔE 9.1 (light) and 8.4 (dark), normal-vision ΔE ≥ 19. Rules:
  - Never cycle the colours. A 9th series goes into "Other".
  - Series 3–5 are below 3:1 on white, so always direct-label them or offer a table view.
  - Never use series colours for status.
  - `--chart-grid` and `--chart-axis` are for chart chrome.
- **Type**: IBM Plex Sans with IBM Plex Sans Arabic. Scale 12/14/16/18/20/24/30 (`--text-*`). Line height 1.5 for EN, 1.7 for AR. Tabular figures in tables.
- **Spacing**: Tailwind's 4 px grid, a 16 px phone gutter, 24–32 px on desktop.
- **Radius**: 8 px base (`--radius`). Cards, tables and dialogs use 12 px.
- **Elevation**: `--shadow-1..3`, mapped to `shadow-xs/sm`, `shadow-md` and `shadow-lg`, with darker values in dark mode.
- **Touch**: `--touch-target` and `--control-h` are 44 px. On a desktop with a mouse, `--control-h` is 40 px and `--control-h-sm` is 36 px.
- **Tables**: always pass `label` to `TD`, so phones get stacked cards. Use `stack={false}` only for tiny inline tables.
- **Filters**: put search first in `ListToolbar`. From the third filter on, filters fold away on phones.
