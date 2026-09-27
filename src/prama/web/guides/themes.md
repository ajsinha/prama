<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Themes and display

Choose a theme from the palette button in the top bar. Your choice is stored in a cookie and applied by
the server before the page is drawn, so there is no flash of the wrong colours. Add `?theme=<name>` to
any URL to preview a theme without changing your choice.

| Theme | Register |
|---|---|
| Prama light | The default: Prama indigo on a cool white ground. |
| Prama dark | The same palette on a night ground. |
| BMO blue | A retail-banking register. |
| Maya crimson, Maya dark, Maya blue, Maya green | Maya's four themes, so the two consoles match on one desk. |
| Wall Street | Amber on black, like a trading terminal. |

## Why the colours are derived

Each theme declares only its surfaces and brand colour. The colours for the eight quality dimensions are
*computed* for each theme, moved only as far as needed to meet contrast rules: 3:1 for a mark and 4.5:1 for
text. A test regenerates the stylesheet and fails the build if anyone hand-edits it, and another fails if
a brand colour comes too close to a dimension colour — which is why Maya dark's accent is slightly pinker
here than in Maya.

## Row density

The list button next to the theme menu switches tables between *comfortable* and *compact*.
