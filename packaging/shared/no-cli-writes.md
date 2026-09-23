## Building with no CLI: stop at the plan

Plan validation is the gate between a draft and spent money. It catches what a
careful reader misses: minor-unit currency arithmetic, a budget on exactly one
level, whether the Page, Instagram identity and dataset exist on this account,
EU transparency fields, special-category consistency, and whether each local
asset is the type it claims.

So when the probe says the CLI is absent: write the plan, show it, and **stop
before the first write.** Do not create objects and validate afterwards - a
wrong campaign that already exists, even paused, is much harder to argue with.

Then offer the routes forward, and say which you recommend:

1. **Validate without installing anything**, if `uv` is on their PATH:
   ```bash
   uvx --from "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
     meta-ads-agent validate-plan <plan>
   ```
2. **Install it**, if they will build campaigns again:
   ```bash
   uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git"
   meta-ads-agent doctor
   ```
3. **Build it by hand** in Ads Manager from the plan - it is a complete
   specification.
4. **Keep the plan as the deliverable** and continue with the read-only work.

Offering no route forward is not an answer, and neither is quietly proceeding.
