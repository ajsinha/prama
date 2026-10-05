<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Themes and display

How the console looks: its colour theme and how dense its tables are. Both are in the top bar, and
both are yours alone.

## To choose a theme

1. Press the palette button in the top bar.
2. Pick one of the four themes. Your choice is kept in a cookie and applied by the server before the
   page is drawn, so there is no flash of the wrong colours.

To preview a theme without changing your choice, add `?theme=<name>` to any URL.

| Theme | Register |
|---|---|
| Crimson | The default: Harvard crimson over indigo on warm paper. |
| Dark | Maya's night ground with a rose accent, for long sessions. |
| Blue | SAJHA's blue on a cool ground. |
| Green | Deep green and house gold on a cream ground. |

They are Maya's four themes under Maya's names, so the two consoles match on one desk. The theme sets
the whole shell: the top bar and its menus, buttons, cards, tabs and the footer.

## To change row density

Press the list button next to the theme menu to switch tables between *comfortable* and *compact*.

## What to know

Each theme declares only its surfaces and brand colour. The colours of the quality dimensions are
*computed* for each theme, moved only as far as needed to meet contrast (3:1 for a mark, 4.5:1 for
text). A test fails the build if the stylesheet is edited by hand, and another if a brand colour
comes too close to a dimension colour, which is why Dark's accent is slightly pinker here than in Maya.

## Go deeper

- [Brand](../../../../docs/reference/brand.md): the palette the themes derive from.
- [Platform: the surfaces](../../../../docs/architecture/platform.md#the-surfaces): how the console is built.
