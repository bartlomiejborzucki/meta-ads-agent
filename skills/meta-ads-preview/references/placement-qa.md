# Placement QA notes

Aspect ratios, safe zones, and rendering behaviour change. **Verify against
actual previews** - `ads_get_ad_preview` is the evidence, this file is
orientation. Where a number appears below it is a well-established convention,
not a value read from an API.

## Placements to render

With automatic placements, Meta may deliver to many surfaces. Rendering all of
them is not practical; these four cover the distinct failure modes:

| Placement | Why it matters |
| --- | --- |
| Facebook Feed | the baseline. Truncation and headline behaviour. |
| Instagram Feed | different crop and a different truncation point. |
| Instagram Stories | full-screen vertical with UI overlays. Breaks square assets. |
| Instagram Reels | vertical, with heavier UI and sound-off viewing. |

Add any placement the plan targets manually. If the plan restricts placements,
render exactly those.

## Aspect ratios

| Placement | Typical | A 1:1 asset here |
| --- | --- | --- |
| Facebook Feed | 1:1, 4:5 | fine |
| Instagram Feed | 1:1, 4:5 | fine |
| Stories / Reels | 9:16 | **crops to centre; top and bottom lost** |
| Right column | 1.91:1 | heavily cropped, and tiny |

The recurring problem: one square asset used everywhere. It is fine in Feed and
loses its top and bottom in Stories, which is where the logo and the headline
usually are.

## Safe zones in Stories and Reels

The interface occupies the top and bottom of the frame - profile and controls
above, the CTA and interaction affordances below. Anything important in those
bands is partly hidden on most devices.

Keep text and logos in the middle portion of the frame. The preview shows the
overlays; look at it rather than measuring.

## Text truncation

Primary text truncates with a "see more" affordance, and the cut lands earlier
than people expect - earlier still on narrow devices and in some placements.

Practical consequence: **the first sentence has to work alone.** Use the
preview to find the real cut point for this creative in this placement, rather
than counting to a remembered character limit.

Headlines truncate too, and a headline cut mid-word looks like a bug to the
reader.

Text *inside* an image is a separate concern. Meta no longer enforces a hard
text-proportion rule, but dense small text is unreadable at rendered size
regardless of policy. Judge it from the preview at the size it renders.

## Video

- **Sound off.** Most Feed and Stories viewing is muted. If the message needs
  audio, it needs captions or on-screen text.
- **First frame.** Check the thumbnail is not black or mid-transition. It is
  the still most viewers see.
- **Length.** Placement-dependent, and the real question is whether the message
  lands before people leave.
- **Vertical.** A horizontal video in Stories gets letterboxed or cropped.
  Neither is good.

Where a video creative is built through the fallback, the thumbnail comes from
Meta's generated frames unless one was supplied. Check which frame it picked.

## Instagram identity

Instagram placements need an Instagram identity. Without a linked account, Meta
may fall back to the Page identity, which renders with the Page name where the
user expected their Instagram handle.

Verify `ads_get_ig_accounts` returned the intended account and that the plan
references it.

## Existing-post ads

A promoted post renders as the original post, with its existing engagement.
Check:

- the engagement counts are present - if they are zero, it may have been
  recreated as a dark post rather than promoted
- the post's own copy, which you cannot edit through the ad
- that the post's link, if any, goes where the campaign intends

## Multi-variant creatives

With several copy variants, the preview shows one combination. Meta selects
per impression, so a single clean preview does not mean every combination is
clean.

Render several previews where the tooling allows, and tell the user that
variants are delivered dynamically - so per-variant results are not
straightforward to read back out.

## What a clean preview does not prove

- Meta's ad review will approve it
- The landing page works, or matches the promise
- Tracking fires
- The offer converts

Say what was checked and what was not. Implied coverage is worse than a short
list.
