# Security policy

## What this software is

Life-Dash is a self-hosted database of one person's life: where they were,
what they did, who with, and photographs of it. There is no cloud service to
report a problem *about* — every instance belongs to whoever runs it. A
vulnerability here is therefore not an incident someone else can contain for
you; it is a change you have to deploy.

## Supported versions

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Anything older | ❌ |

This is a single-author project. Fixes go into the next release; there are no
backports to older versions, and there is no tested upgrade path out of the
`0.x` line — see `docs/internal/ROADMAP.md`.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's [private vulnerability
reporting](https://github.com/Noxon007/life-dash/security/advisories/new) on
this repository. That keeps the report between us until there is something to
update to.

What helps, in order:

1. What an attacker can reach that they should not — data, an account, the host.
2. The smallest sequence of steps that shows it.
3. Which sign-in mode (`local`, `oidc`, `dev`) and whether the instance is
   exposed to the internet.

**What to expect.** One person reads these, in their spare time. You will get
an acknowledgement within a week. If the report is valid, the fix and its
reasoning are written up in `docs/internal/DECISIONS.md` like everything else
in this project, and you are credited there unless you would rather not be.
There is no bounty programme and no payment.

## Things that are known and deliberate

Reporting these again costs us both time, so they are listed here with the
reasoning. All of them are decisions, not oversights:

- **`AUTH_MODE=dev` disables authentication entirely.** It refuses to start in
  an environment that looks reachable, and `DEV_AUTH_ALLOW_PUBLIC=true` is the
  documented way to run a public demo instance on purpose.
- **The first registration is open** when `AUTH_MODE=local` and no account
  exists yet — there is no other way to bootstrap without a console. The window
  is seconds long if you follow `docs/DEPLOY.md`.
- **Sessions are revoked all at once, never individually.** There is no device
  list, on purpose.
- **The failed-login lockout is per process and per email address.** Behind
  several workers it is a baseline rather than a guarantee, and a determined
  attacker can lock a single account for fifteen minutes. Both are stated in
  `docs/DEPLOY.md`.
- **Map tiles are fetched from whichever tile server the operator configures**,
  and Wikipedia thumbnails come from Wikimedia. Those requests carry
  coordinates by their nature. Which map gets to see them is the operator's
  choice, which is why no provider is preset.
- **The admin role can read every account's rows** through the raw table view
  — minus passwords and API keys, which it neither returns nor accepts. An
  administrator of your own instance is you.

## Things that are *not* deliberate

Everything else. In particular: anything that lets one account read or write
another account's data, anything that turns stored text (a place name, a
journal entry, an imported album title) into executing code, anything that
leaks a secret into a response, a log, or a backup, and any path that reaches
the host filesystem or an internal network address the operator did not name.

Those are the classes this project has repeatedly found in itself, and they are
the ones worth your report.
