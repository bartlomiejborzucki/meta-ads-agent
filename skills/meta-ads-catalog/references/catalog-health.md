# Catalog health, in more detail

## Issues by what fixes them

| Issue kind | Usually fixed in | Note |
| --- | --- | --- |
| Missing or broken image | the feed | the most common, and the most visible - a product with no image cannot appear in a dynamic ad |
| Missing or malformed price, currency | the feed | a price in the wrong currency is worse than a missing one |
| Invalid or unreachable product URL | the shop | check the domain and redirects, not only the path |
| Availability out of date | the feed schedule | an out-of-stock product still advertised costs clicks and trust |
| Disapproved for policy | each item | read the reason per item; do not bulk-edit around a policy decision |
| Duplicate ids | the feed | two products with one id: one of them never serves |

Report issues as a count and a share of the catalog. 200 products with no
image is a problem in a 400-product catalog and a rounding error in a
40,000-product one.

## Feeds

A feed's schedule should match how often the shop changes. A daily feed for a
shop whose prices change hourly is serving stale prices most of the day. A
feed whose last upload failed is serving whatever it had before - check the
last *successful* upload, not only the last attempt.

## Event-source match

Retargeting catalog ads show people the products they looked at. That works
only when the product id on the pixel event matches the id in the catalog.
Match rates are reported per event:

- **ViewContent** low: the product page sends an id in a different format
  (a SKU where the catalog has a variant id, or the reverse).
- **AddToCart** or **Purchase** low but ViewContent fine: the cart and
  checkout templates send a different id from the product page.

Fixing the id format fixes every audience built on those events at once.
It is a change to the shop's tracking, not to the catalog, and belongs with
`meta-ads-tracking`.

## Product sets that look right and are not

- A filter on a custom label the feed does not populate matches nothing.
- A price filter in the wrong currency unit matches the wrong products.
- "All products" includes the out-of-stock and disapproved ones.

Always read the set's product count and a sample of its products before
proposing it for a campaign.
