# Live integration tests

**Disabled by default. Never run in CI. Never run against a real production ad
account.**

Every other test in this repository is offline: the SDK boundary is faked and
nothing reaches Meta. These tests exist for the one thing mocks cannot check -
that the fallback's calls are shaped the way Meta actually expects.

## Requirements

All of these, or the tests skip:

| | |
| --- | --- |
| `META_ADS_LIVE_TESTS=1` | explicit opt-in. Nothing else enables them. |
| `META_ADS_LIVE_TEST_ACCOUNT` | a **designated test ad account**, not a real one |
| `META_ACCESS_TOKEN` | a token with `ads_management` on that account |
| `pytest -m live` | the marker is excluded from the default run |

```bash
META_ADS_LIVE_TESTS=1 \
META_ADS_LIVE_TEST_ACCOUNT=act_<your test account> \
META_ACCESS_TOKEN=<token> \
  uv run pytest -m live -v
```

## Rules these tests follow

- **Nothing is activated.** Ever. No test calls an activation path.
- **Everything created is PAUSED**, and nothing spends: a paused structure with
  no active ad has no delivery.
- **Every created object is named with the prefix `TEST_META_ADS_AGENT_`**, so
  anything left behind is unmistakable in Ads Manager.
- **No budget is set above the account minimum.** Even a paused object should
  not carry a large number.
- **No customer data.** No customer-list audiences, no PII, at any point.
- **No production account.** Use an account created for this purpose, with its
  own spend limit set low as a second line of defence.

## Cleanup

These tests do **not** delete what they create. Deletion is a guarded operation
in this project and it would be inconsistent to have a test suite that
routinely bypasses the guard.

Clean up by hand:

1. In Ads Manager, filter by name containing `TEST_META_ADS_AGENT_`.
2. Confirm everything found is paused and has zero spend.
3. Pause anything active - if something is active, that is a bug worth
   reporting.
4. Delete, or leave paused. Paused costs nothing.

Uploaded test images and videos stay in the account's asset library. They cost
nothing and are harmless; delete them if you prefer a tidy account.

## Why CI never runs these

Running them would mean a Meta access token in repository secrets. That token
would have `ads_management` on a real ad account, reachable by any workflow run
- including one triggered by a fork's pull request, depending on configuration.

The trade is not worth it. `ci.yml` explicitly sets `META_ACCESS_TOKEN=""` and
`META_ADS_LIVE_TESTS=0`, and excludes the `live` marker, so a stray live test
fails loudly instead of quietly picking up a credential.

## What to add here

Only things a mock genuinely cannot verify:

- that a local image upload produces a usable `image_hash`
- that a local video upload completes transcoding and produces a usable
  `video_id`
- that a video creative built from that id is accepted
- that an existing-post creative preserves `object_story_id`
- that `asset_feed_spec` is accepted in the shape we send

Everything else - dedup, ordering, retry-safety, dry-run, error mapping, the
approval model - is our logic, and belongs in the offline suite where it runs on
every push.

## Nothing here yet

0.1.0 ships no live tests. The offline suite covers every code path; what is
missing is confirmation that Meta accepts the request **shapes**, and writing
those tests responsibly requires a designated test account that the author of
this release did not have.

This is a known gap, recorded rather than glossed over. If you have a test
account and add some, please follow the rules above.
