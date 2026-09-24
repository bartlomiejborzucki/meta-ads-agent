# Trigger evals

Does each skill's `description` select it for the requests it exists for, and
do none of them fire on requests that have nothing to do with Meta Ads? Every
skill's trigger text is written for this; these cases check it.

One case per skill (`triggers-*`), each a typical request that does not name
the skill, and two negatives (`not-*`). Graders are `tool_used` on the `Skill`
tool, so nothing here is judged by a model - only whether a skill loaded.

```bash
claude plugin eval . --ablation none --trust-plugin --no-publish
```

`--ablation none` matters: with the default two-arm run, a `tool_used: Skill`
grader is reported as an indicator rather than scored, and the suite would
pass whatever the descriptions say.

**Cost.** Every run is a real model call on your credentials: 13 cases x 3
runs x up to 3 turns. It is not part of CI on every push; the `Trigger evals`
workflow runs it on demand, with a cost ceiling, when an `ANTHROPIC_API_KEY`
secret is configured.

`meta-ads-core` also claims "any task that touches a Meta ad account", so it
may load alongside another skill. That is intended, and the positive cases do
not forbid it; the negatives check it does not reach further than that.
