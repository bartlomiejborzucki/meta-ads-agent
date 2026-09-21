## Building with no CLI: stop at the plan

Plan validation is the gate between a draft and spent money. It checks the
things that are invisible to a careful reader: minor-unit currency
arithmetic, a budget set on exactly one level, whether the Page, Instagram
identity and dataset actually exist on this account, EU transparency fields,
special-ad-category consistency, and whether each local asset is the type it
claims to be. Reading the plan attentively is not the same check.

So when the probe says the CLI is absent: write the plan, show it, and **stop
before the first write.** Do not create objects and validate afterwards - a
wrong campaign that already exists is much harder to argue with than one that
does not, even paused.

Then give the user the routes forward, and say which you recommend:

1. **Validate without installing anything**, if `uv` is on their PATH:
   ```bash
   uvx --from "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
     meta-ads-agent validate-plan <plan>
   ```
2. **Install it**, if they expect to build campaigns again:
   ```bash
   uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"
   meta-ads-agent doctor
   ```
3. **Build it by hand** in Ads Manager from the plan you just showed them. The
   plan is a complete specification; it does not need this tooling to be
   useful.
4. **Leave the plan as the deliverable** and continue with the read-only work -
   audit, research, creative, reporting - none of which needs the CLI.

Offering no route forward is not an answer, and neither is quietly proceeding.
