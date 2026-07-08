# DESIGN.md, Questboard trade paper

The committed visual system. Source of truth artifacts: `packages/ui/src/tokens.css`, `packages/ui/reference/quest-board-mock.html` (the approved v12 mock), and the reference screenshots beside it. Identity preservation wins over trend rules: the warm ground below is a committed brand decision iterated with the owner across many rounds, made specific by the engraving, stamps, and ledger grammar that live on it.

## Theme

Light only. A printed trade paper read at a desk in daylight: cream ground, white paper cards, ink text, hand-drawn postal stamps in five vertical hues. Depth comes from a darker bottom border (paper thickness), never from shadows.

## Palette

| Token | Value | Role |
|---|---|---|
| ground | #F6F3EC | page background |
| paper | #FFFFFF | cards, sheets |
| hair | #E4DED1 | hairline borders |
| edge | #D9D1BF | card bottom border (the only depth) |
| ink | #1C1B17 | headings, primary text |
| soft | rgba(28,27,23,.84) | body text |
| mute | rgba(28,27,23,.66) | secondary text, method lines |
| sage | #3F6B54 | Career + primary action buttons |
| clay | #A6522E | On camera |
| ochre | #8A6A1F | Paid studies |
| slate | #44607A | Behind the camera |
| wine | #7D3B4C | Party quests |

## Typography

- Fraunces (variable, optical sizing): display only. Masthead 78/64, page titles 33, section 26/24, card titles 19.
- Atkinson Hyperlegible Next (variable): all UI text, 15.5 body, 1.55 to 1.6 line height.
- Monospace with tabular-nums: every data value (pay, counts, dates).
- Never pair another sans. Never uppercase-track labels.

## Components

`@questboard/ui`: QuestCard (band + stamp, serif title link, mono meta, needs line, pay footer, Clip and stamp states), Chip (vertical chips with stamp + hue; preset chips with live counts, dim under 3 and never hidden), LedgerRow, Sheet + Scrim, PostmarkStamp (press: scale 1.12 to 1, rotate -5 to -2deg, 250ms), SplitFlap (load-once), TextLink, SageButton, PlainButton, the six stamps.

## Motion budget

Hard cap of three deliberate motions per page: the split-flap row on load, one scroll-sharpened line, the postmark press on Clip. Hovers darken only. prefers-reduced-motion renders final values instantly. Content is never gated on a reveal.

## Layout

Cards 10px radius, controls 4px. Hairline borders everywhere, edge-colored bottom borders on cards. Card grid: repeat(auto-fill, minmax(280px, 1fr)). Wide content scrolls in its own container.

## Bans (repo-wide, enforced in review)

Box shadows. Gradients as atmosphere (single committed exception: the split-flap cell material, present in the approved mock). Uppercase transforms. Middots. Em dashes, in copy and in code comments. Sparkle or robot icons. Chip counts that lie (every count comes from a real query total).
