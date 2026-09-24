# Test design and reading, in more detail

## Picking the metric

The metric should be the one the decision depends on, measured on enough
volume to be sized. Those two pull against each other:

| Metric | Volume | Tells you |
| --- | --- | --- |
| CTR | high | which creative gets attention - not which one sells |
| Cost per landing page view | medium | who arrives, not who converts |
| Cost per lead | lower | the usual decision metric for lead generation |
| Cost per purchase, ROAS | lowest | the usual decision metric for commerce |

When the decision metric cannot be sized in acceptable time, a higher-volume
metric earlier in the chain can be tested instead - honestly labelled as a
proxy, because a creative that wins on CTR can lose on purchases.

## Why alpha is divided among cells

Each extra cell is another comparison with the control, and every comparison
has its own chance of a false positive. Three cells at alpha 0.05 each have
roughly a one-in-ten chance that at least one "wins" by noise. `report power`
divides alpha among the comparisons (Bonferroni), which is conservative: it
needs more volume, and it keeps a result meaning what it says.

## Duration

Run for whole weeks. Behaviour differs by weekday, and a test that covers two
Mondays and one Sunday is comparing different weeks. The sizing gives a
minimum; round it up to the next whole week.

Do not end early because one cell looks ahead. Early leads are exactly where
noise is largest, and stopping when a result looks good guarantees that the
results reported look better than they are.

## Relative and absolute

A 30% relative lift on a 1% conversion rate is 0.3 percentage points. Both
numbers are true, and a report that gives only the relative one invites the
reader to imagine a larger effect than there is.

## When the result disagrees with the attribution report

It usually should. Attribution assigns conversions to ads that were near
them; a test compares comparable groups that did and did not see a thing. When
they disagree, the test is the better evidence about cause, and the
disagreement is itself worth reporting.
