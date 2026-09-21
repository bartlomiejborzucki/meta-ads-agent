# Codex on Windows, toolchain in WSL

The arrangement this page covers: **Codex runs as a Windows application**, its
integrated terminal runs **WSL2**, and every runtime - Python, Node, uv, pip,
npm - plus this repository live on the **Linux** side. Nothing in this project
gets installed on Windows.

The one thing that catches people out is worth stating first, because it
explains every other decision here:

> The Codex process is a Windows process. It cannot see
> `/home/you/.agents/skills`. A skills directory that is obviously correct
> from the WSL terminal is invisible to the application that has to read it.

So the skills are **copied** into the Windows user profile, and everything
else stays where it is.

```
Windows                                   WSL2 (Ubuntu)
─────────────────────────────────         ─────────────────────────────────
Codex app                                 the repository
  reads  %USERPROFILE%\.agents\skills     python, node, uv, pip, npm
  reads  %USERPROFILE%\.codex\config.toml meta-ads-agent CLI
  opens  OAuth in your Chrome profile     meta-ads-agent install / upgrade
       ▲                                        │
       └──────────── copies files, edits one ───┘
                     config block, hands over a URL
```

Why copy rather than symlink: a Windows symlink into the WSL filesystem needs
Developer Mode or an elevated shell to create, stops resolving when the
distribution is not running, and goes through a 9P file server the Codex
process may or may not reach. Copying is boring, and boring is the right
property for the thing that decides whether the skills load at all.

## Install

Run this **in the WSL terminal**, once.

```bash
uv tool install "git+https://github.com/bartlomiejborzucki/meta-ads-agent.git" \
  && meta-ads-agent install --target windows-codex
```

That is the whole install, and it is safe to run again. The first half puts
the CLI in WSL; the second copies the nine skills into
`%USERPROFILE%\.agents\skills` and verifies every file against the release
manifest before recording the version.

The skills travel inside the wheel, so there is no second clone and no way for
the CLI and the payload to be different versions of the project.

Then **start a new Codex session** - skills are loaded at session start.

### If `%USERPROFILE%` cannot be detected

The installer asks Windows rather than guessing at `/mnt/c/Users/<login>`,
because redirected profiles, a different drive letter and a Microsoft-account
login that does not match the folder name are all common. If the interop
binaries are unavailable, point at it yourself:

```bash
meta-ads-agent install --target windows-codex --windows-home /mnt/c/Users/you
```

Paths with spaces are fine - `/mnt/c/Users/Bartek Borzucki` works, and there
is a test for it.

## Update

```bash
uv tool upgrade meta-ads-agent && meta-ads-agent upgrade --target windows-codex
```

Also safe to re-run. What it does, in order:

1. Works out what is installed, how, and what the package ships.
2. Copies the current installation into `.meta-ads-agent-backup/`.
3. Builds the complete new tree beside the old one and hashes every file in
   it against the release manifest.
4. Swaps it in, deleting files the new release dropped so nothing is left
   over from the previous version.
5. Verifies the installed tree.
6. **Only then** records the new version.
7. Runs any outstanding workspace migrations, each exactly once.

Steps 1-6 replace the whole payload, not the files that happened to be there
already, which is what makes a new `references/` file, a new `assets/`
directory and a new `scripts/` directory arrive rather than being skipped.

### If an update is interrupted

Close the laptop mid-copy and the installation says so:

```bash
meta-ads-agent doctor
#   INTERRUPTED   an update from 0.1.0 to 0.2.0 stopped during 'swap'
```

Two ways out, both safe:

```bash
meta-ads-agent upgrade --target windows-codex              # finish it
meta-ads-agent upgrade --target windows-codex --rollback   # go back
```

The version number is written last, so an interrupted update never leaves an
installation claiming to be current. A resumed update reuses the backup the
failed attempt took rather than archiving the half-installed tree over it.

## Connect Meta's MCP

Two steps, both from WSL.

```bash
meta-ads-agent mcp-config --windows --client-id <YOUR_META_APP_ID>
```

This writes **only** the `[mcp_servers.meta-ads]` block into
`%USERPROFILE%\.codex\config.toml`. The block is fenced with comment markers
and spliced in as text; your model settings, approval policy, other MCP
servers and comments are preserved byte for byte. Re-running it with the same
values changes nothing.

Then authorise. OAuth must open in the Windows browser you are already signed
into:

```bash
meta-ads-agent open-url "https://<the URL Codex or Meta gives you>"
```

There is no Linux browser fallback, on purpose. A browser started inside WSL
has its own empty profile, so Facebook would ask you to sign in again in a
window that is not holding your session, and the redirect would not come back
to the right place. If no Windows launcher is found, the command prints the
URL and stops rather than opening the wrong thing.

To make this the default for anything that shells out to a browser:

```bash
echo 'export BROWSER="$(command -v wslview || echo explorer.exe)"' >> ~/.bashrc
```

## Where your own details go

Your Meta App ID, ad account id and connection notes are **not** in this
repository and must not be copied into a skill. On this machine they live in

```
C:\Users\<you>\.codex\local-context\meta-ads-connection.md
```

Nothing here reads, copies or modifies that file - there is a test asserting
the installer leaves it byte-identical, and another asserting no file of that
name is tracked in git.

The brand workspace (`.meta-ads/`) stays in your project on the WSL side and
is gitignored by default.

## Checking it worked

```bash
meta-ads-agent doctor
```

```
Installation
------------
  COMPLETE                      0.2.0, verified
    target: C:\Users\bartl\.agents\skills
```

In Codex itself, type `$` - the nine `meta-ads-*` skills should be listed. If
they are not, start a new session first.

To confirm the runtimes are where they belong: `where python` in a Windows
shell should find nothing this project put there, and `which python3` in WSL
should find the WSL one.

## Running things from the Windows side

If you want a Windows shortcut that drives the WSL toolchain, this needs
nothing installed on Windows:

```bat
wsl.exe -d Ubuntu -- meta-ads-agent doctor
wsl.exe -d Ubuntu -- meta-ads-agent upgrade --target windows-codex
```

Substitute your distribution name from `wsl.exe -l -q`.

## What is not verified automatically

Honest limits, because the tests run on Linux CI:

- **The Windows side is faked in the test suite.** Path conversion, the
  profile lookup, the config merge, the browser hand-off and the copy are all
  exercised against a stand-in for `C:\`, `wslpath`, `cmd.exe` and
  `explorer.exe`. What is proven is the logic, not Microsoft's filesystem.
- **That Codex for Windows reads `%USERPROFILE%\.agents\skills`** comes from
  OpenAI's documented `$HOME/.agents/skills` lookup. It has not been confirmed
  against a running Windows Codex build here. If yours reads somewhere else,
  `--target path --path <that directory>` installs there and everything else
  on this page still applies.
- **The OAuth round trip** needs a real Meta app and a real browser. The
  command that opens it is tested; the grant is not.

## Troubleshooting

**Codex does not list the skills.** Start a new session. If they are still
absent, run `meta-ads-agent doctor` and compare the `target:` line with what
your Codex build actually reads.

**`wslpath: command not found`.** You are not in WSL, or interop is disabled.
Use `--windows-home` and `--target windows-codex`, or install to a plain path.

**A second `.agents` directory appeared.** It should not - the installer
resolves an existing directory case-insensitively. Report it with the output
of `meta-ads-agent doctor --json`.

**`command not found: meta-ads-agent` inside Codex's terminal.** `uv tool
install` puts it in `~/.local/bin`; make sure that is on `PATH` in the shell
Codex starts.
