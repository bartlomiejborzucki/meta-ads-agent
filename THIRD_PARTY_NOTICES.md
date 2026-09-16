# Third-party notices

This file records third-party material and influences. The full audit trail — what was
reviewed, under which license, at which commit, and what class of reuse applies — is in
[`docs/research/provenance.md`](docs/research/provenance.md).

**No third-party source code or text is bundled in this repository.** Every third-party
influence listed below was reimplemented from scratch. The notices are given because credit
is due, not because a license compels it.

## Runtime dependencies

Dependencies are installed from PyPI at their own licenses and are not redistributed here.

| Package | License | Installed by default |
| --- | --- | --- |
| [`pydantic`](https://github.com/pydantic/pydantic) | MIT | yes |
| [`PyYAML`](https://github.com/yaml/pyyaml) | MIT | yes |
| [`facebook-business`](https://github.com/facebook/facebook-python-business-sdk) | Facebook Platform License | **no** — optional `api` extra |

### facebook-business (Meta Business SDK)

Copyright (c) Meta Platforms, Inc. and affiliates. Licensed under the Facebook Platform
License, which is **not** an OSI-approved open-source license. It permits use in connection
with Meta's platform, which is this project's only use of it.

It is an **optional extra** (`pip install "meta-ads-agent[api]"`). A default installation that
uses only the official Ads MCP does not install it. It is never vendored, never redistributed,
and its source is never copied into this repository.

## Reimplemented ideas

Credited by source. No code or text from any of these entered this repository.

| Source | License | Idea adopted, reimplemented |
| --- | --- | --- |
| [`byadsco/meta-ads-mcp`](https://github.com/byadsco/meta-ads-mcp) | MIT © 2025 ByAds — Santiago Bastidas | Single-source Graph API version module; writes paced as a distinct risk class from reads; a Meta error-code reference; pinning the secret scanner's version in CI |
| [`sepivip/meta-ads-skill`](https://github.com/sepivip/meta-ads-skill) | MIT © 2026 Beka Zakaidze | The stance that the official MCP's tool contracts differ from the Graph API and must be introspected rather than assumed; that a platform VALIDATION error outranks any local note; checking account eligibility fields before writing. Specific factual observations are credited inline in [`docs/research/current-meta-capabilities.md`](docs/research/current-meta-capabilities.md) |
| [`Sandy-zippy/meta-ads-stack`](https://github.com/Sandy-zippy/meta-ads-stack) | MIT © 2026 ZippyScale | Skills reason, MCP executes, the human approves; a monitoring role that never writes, separated from an execution role that only applies approved actions; an append-only action log |
| [`kelpi-ai/meta-ads-skills`](https://github.com/kelpi-ai/meta-ads-skills) | MIT © 2026 Kelpi | One skill per job with an explicit read/write posture; requiring multiple independent signals before declaring creative fatigue; baselining an entity against its own history; enumerating alternative explanations; declining to conclude on thin data |
| [`rafaelszago/meta-ads-mcp`](https://github.com/rafaelszago/meta-ads-mcp) | MIT © 2026 Rafael Zago | The brand-workspace concept; structured account facts kept separate from free-form brand voice; naming the currency unit in the field; tokenised naming conventions reused for UTM construction |
| [`mardab96/meta-ads-skills`](https://github.com/mardab96/meta-ads-skills) | MIT © 2026 Marek Dabrowski / AdLume | Deterministic arithmetic in code with judgement left in prose; a noise band plus a volume floor before flagging a change; thresholds as parameters rather than constants |
| [`Digitizers/meta-ads-mcp`](https://github.com/Digitizers/meta-ads-mcp) | MIT-0 © 2026 Digitizer | Thin-skill-plus-references packaging; preferring pause over delete because deleted objects lose optimisation history permanently; special ad categories as an account-suspension risk; explicit PII handling rules |

## Reference-only sources

Read for orientation. **Nothing was copied, adapted, quoted, or depended upon.** Listed so the
record is complete and so nobody mistakes them for available material.

| Source | License | Why nothing was taken |
| --- | --- | --- |
| [`pipeboard-co/meta-ads-mcp`](https://github.com/pipeboard-co/meta-ads-mcp) | Business Source License 1.1 | Not an open-source license; restricts competing products and converts to permissive only at a future change date |
| [`lil-j/meta-ads-mcp`](https://github.com/lil-j/meta-ads-mcp) | none | No license file, so all rights are reserved by default |
| [`itsfromgaurav/ultimate-meta-ads-skill`](https://github.com/itsfromgaurav/ultimate-meta-ads-skill) | MIT with carve-out (`NOASSERTION`) | The license explicitly withholds rights to the underlying advertising frameworks, which belong to a commercial book's authors and publisher |
| [`gomarble-ai/facebook-ads-mcp-server`](https://github.com/gomarble-ai/facebook-ads-mcp-server) | MIT | Reuse would be permitted; nothing applicable to a Codex/Claude Code plugin |

## Meta documentation

Tool names, endpoint URLs, OAuth scope names, and API version numbers were read from Meta's
developer documentation and are recorded as facts. Meta's documentation prose is not licensed
for redistribution and none is reproduced here.

## Host plugin formats

The `.claude-plugin/` and `.codex-plugin/` manifest schemas were read from Anthropic's and
OpenAI's published plugin references and example repositories. Manifest field names are
required by those formats; all values in this repository describe this project.

## Trademarks

"Meta", "Facebook", "Instagram", "Messenger", "WhatsApp", "Advantage+", "Meta Business Suite",
"OpenAI", "ChatGPT", "Codex", "Anthropic", and "Claude" are trademarks of their respective
owners. They are used here descriptively, only to identify the platforms this project
interoperates with. This project is independent and is not affiliated with, sponsored by, or
endorsed by any of them.
