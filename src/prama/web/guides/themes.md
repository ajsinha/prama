<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Themes and display

Choose a theme from the palette button in the top bar. Your choice is stored in a cookie and applied by
the server before the page is drawn, so there is no flash of the wrong colours. Add `?theme=<name>` to
any URL to preview a theme without changing your choice.

Prama has exactly Maya's four themes, under Maya's names, so the two consoles match on one desk and a
choice means the same thing in both:

| Theme | Register |
|---|---|
| Crimson | The default: Harvard crimson over indigo on warm paper. |
| Dark | Maya's night ground with a rose accent, for long sessions. |
| Blue | SAJHA's blue on a cool ground. |
| Green | Deep green and house gold on a cream ground. |

The theme sets the whole shell: the gradient of the top bar and its menus, buttons, cards, tabs and the
footer all take their colour from it.

## Why the colours are derived

Each theme declares only its surfaces and brand colour. The colours for the eight quality dimensions are
*computed* for each theme, moved only as far as needed to meet contrast rules: 3:1 for a mark and 4.5:1 for
text. A test regenerates the stylesheet and fails the build if anyone hand-edits it, and another fails if
a brand colour comes too close to a dimension colour — which is why Dark's accent is slightly pinker
here than in Maya.

## Row density

The list button next to the theme menu switches tables between *comfortable* and *compact*.

## Go deeper

- [Brand](../../../../docs/reference/brand.md): the palette the themes derive from.
- [Platform: the surfaces](../../../../docs/architecture/platform.md#the-surfaces): how the console is built.
