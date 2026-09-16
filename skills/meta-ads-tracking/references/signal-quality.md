# Signal quality: what the numbers mean

## Event Match Quality

Meta scores how well the identifying information in your events matches people
it knows about. Higher means optimisation and attribution work better.

The score alone is not actionable. **Per-key coverage is.**

| Parameter | Effect on matching | Usual availability |
| --- | --- | --- |
| Click id (`fbc`) | strong, and unambiguous | high, if the parameter survives redirects |
| Browser id (`fbp`) | strong | high, if the pixel is present |
| Email (hashed) | strong | depends on whether the user identified themselves |
| Phone (hashed) | strong | lower |
| External id | strong, for logged-in users | depends on the site |
| Name, city, country | weak alone | often present |
| IP, user agent | weak | usually present |

So report coverage rather than the score:

```
weak    "EMQ is 4.1, you should improve it"
useful  "EMQ 4.1. Email is present on 22% of LEAD events and phone on 4%.
         Click id is present on 96%, so the link parameters are surviving.
         Adding hashed email where consent allows is the largest available
         lever."
```

The click-id figure is worth calling out separately: if it is low, the problem
is a redirect stripping query parameters, which is a different fix from
collecting more customer data.

## Event volume

`ads_get_dataset_stats` shows what Meta **received**, over up to 28 days.

| Pattern | Likely cause |
| --- | --- |
| Zero for an event that should fire | not implemented, or renamed |
| Sudden drop to zero | a deploy, a tag removed, a consent change |
| Gradual decline | consent rates, browser restrictions, audience platform mix |
| Browser events fell, server events steady | the pixel |
| Server events fell, browser steady | the Conversions API integration |
| Both fell together | the site, or consent |
| Volume far above expectation | double-firing, or a rule matching too broadly |

Break down by source where possible - browser versus server is the fastest
useful split, because it halves the search space immediately.

Double-firing matters: it inflates reported conversions and teaches the
optimiser from duplicated events. If volume looks too good, check for it before
celebrating.

## Browser and server events

Most advertisers send both: the browser pixel and the Conversions API.

- **Browser** is easy to install and subject to consent, ad blockers, and
  browser restrictions.
- **Server** is more reliable and needs development work.
- **Both** requires deduplication, usually via a shared event id. Broken
  deduplication double-counts.

You cannot verify deduplication from these tools. If reported conversions look
suspiciously high, name double-counting as a candidate and point at Events
Manager, rather than presenting the number as fact.

## Attribution windows

A window defines how long after an interaction a conversion is credited.

Practical consequences:

1. A longer window reports more conversions from the same activity. It has not
   produced more conversions.
2. **Numbers from different windows are not comparable.** If the setting
   changed, the comparison is invalid - say so rather than publishing it.
3. Conversions arrive after the click, so recent periods **understate**
   results. A fresh window always looks worse than it will.

Record the window with every report. A report without one cannot be compared
against anything later, which quietly destroys its value.

## Modelled conversions

Some reported conversions are statistical estimates rather than observed
events, because observation is incomplete - consent, platform restrictions,
cross-device behaviour.

This is not fraud and not an error, but it has consequences:

- Modelled numbers carry more uncertainty than observed ones.
- They may not reconcile with the advertiser's own analytics, and that
  discrepancy is expected rather than a bug to hunt.
- A small difference in a modelled figure deserves more caution than the same
  difference in spend, which is observed.

When a user asks why Meta reports 40 conversions and their CRM shows 26, this
is usually a large part of the answer - along with attribution window
differences and the click-to-session gap below.

## The click-to-session gap

Compare link clicks to landing page views.

| Gap | Reading |
| --- | --- |
| Small | clicks are arriving |
| Large | people click and do not arrive |

Causes, roughly in order of frequency: a slow page, a redirect chain, a consent
wall counted before the pixel fires, a broken or geo-restricted URL, accidental
clicks, and the pixel not present on the landing page.

It is cheap to check and frequently explains a "conversion problem" that has
nothing to do with conversion.

## UTMs

Meta's reporting and the advertiser's analytics are separate measurement
systems, and they will disagree. UTMs are what make the disagreement
investigable.

- Keep conventions consistent - `brand.yaml.utm` holds them.
- Verify parameters **survive to the landing page**. A redirect that strips the
  query string breaks the advertiser's analytics while Meta's reporting looks
  perfect.
- Do not put personal data in a UTM parameter.

## What none of this proves

These tools show what Meta received and how well it matched. They do not show:

- that the pixel fires on every relevant page
- that the values sent are correct
- that deduplication works
- that consent management behaves as intended
- that one specific test conversion was tracked

For those: Events Manager test events, a browser inspection, or server logs.
Say which questions you answered and which you did not. A precise partial
answer beats a confident complete-sounding one.
