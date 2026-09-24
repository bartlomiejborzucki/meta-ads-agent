# Lookalike sources, in practice

Heuristics with reasons attached, not Meta rules. The rules - minimum source
size, allowed countries, the percentage range - are Meta's to set, change over
time, and are read with `ads_get_help_article` at the time of use.

## Why value beats volume

A lookalike model learns what the source has in common. A source of
purchasers has a purchase in common; a source of all visitors has a click in
common. The second is larger and easier to build, and describes almost
everyone who has ever clicked an ad.

When the user has customer value (repeat purchases, order value, lifetime
value), a source of their best customers usually outperforms one of all
customers, which usually outperforms one of leads. "Usually" is doing work
there: a small, very high-value source can be too thin to model well.

## Recency

Customers from three years ago describe a product, a price and a market that
may no longer exist. A recent window - the last six months is a common
choice - describes who buys now. The trade is size: a shorter window is a
smaller source.

## One source, one question

A lookalike built from a mixed source - buyers and newsletter sign-ups
together - resembles neither well. If the user has two kinds of valuable
people, two lookalikes answer more than one blended one.

## Reading "too small"

When a lookalike under-delivers, the causes in order of likelihood:

1. It is still populating. Check its status.
2. The percentage is at the closest band in a small country.
3. The ad set's other targeting (age, placements, exclusions) is narrowing it
   further.
4. The source is thin, so the model has little to go on.

Widening the percentage addresses 2 and sometimes 4. It does nothing for 1 or
3, which are the more common.

## Reporting a lookalike

Always with: its source (and the source's size and date range), the country,
the percentage, its status, and its current size estimate. A lookalike
reported as a name alone cannot be judged by anyone reading the report.
