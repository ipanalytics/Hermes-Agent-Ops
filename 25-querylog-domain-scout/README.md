# 25 — Querylog Domain Scout

_Russian version: [README.ru.md](README.ru.md)_

![License](https://img.shields.io/github/license/ipanalytics/Hermes-Agent-Ops)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

Hermes is my home AI agent: it lives on my own server, runs on a schedule (recurring jobs at fixed
times, the way Unix cron does), and handles the routine I would otherwise forget — digests, price
watches, health checkups, even watching its own failures. Each folder in this repository is one
of those jobs, one self-contained problem and the script I wrote to make it stop biting me.
This folder is the one that watches what every device on my home network is talking to on the
internet, and tells me when something new shows up that I cannot explain.

AdGuard Home is the DNS-layer ad blocker I run on the same network. DNS (Domain Name System) is
the directory service that turns a name like `example.com` into the IP address a computer
actually connects to; running AdGuard Home on my router means every name a device in the house
asks for — every website, every app phoning home, every telemetry endpoint — goes through it
and is recorded in its query log. That log is a running record of the whole household's internet
use, one JSON object per line, written as the requests happen.

I used to open that log only when something had already gone wrong. A new device shipped to the
house had been phoning its maker for two weeks before I checked. An app I did not install was
calling a domain I did not recognise. A piece of malware tried to call home, and I only found
out because the cron job I cared about was unrelated and I happened to scroll the log. The
problem was always the same: by the time I looked, the call had been made for days. So this
folder reads the log routinely, keeps a local database of which device has touched which domain,
and surfaces the domains I have never seen before. A new gadget, a stranger app, or a domain
nobody on the network can explain — that shows up in a weekly report, not in a post-mortem.

## What the scout actually does

The script takes the querylog from AdGuard Home and turns it into a per-device picture. For
every client — identified by its IP, with a name I assigned in the script — it tracks which
domains that client has asked for, when each one was first seen, how many times it has been
queried, and whether the request was blocked at the DNS level. Everything observed so far lives
in a local SQLite database (a small single-file database stored on disk, no server process to
run) of domain-client pairs. "New" therefore means new against the whole history I have
collected since I started watching, not new against yesterday.

Before anything reaches the database or the report, a noise filter strips out the chatter that
would otherwise dominate. Anything in `.local`, `.internal` or `.arpa` is dropped — those are
LAN-side service discovery and reverse-DNS names that never reach the open internet. Anything
starting with an underscore is dropped — that is mDNS / DNS-SD (the multicast protocol devices
use to announce themselves to each other on the local network), not a real hostname. Very long
hex strings (machine identifiers, not hostnames) are dropped. And a hardcoded list of obvious
analytics subdomains — `.clerk.`, `.sentry.`, `.segment.`, `.amplitude.`, `.mixpanel.`,
`.datadog.`, `.newrelic.` — is dropped. Those last ones show up on every device the moment any
app is installed; counting them as "new" would bury anything actually worth noticing. The
filter is conservative on purpose: a missing legitimate domain in the report is cheaper than
a report full of telemetry pings I already know about.

## How it works

The scout connects to the AdGuard Home host over SSH — a secure remote-login shell session
that I use anyway, so no new daemon or API token to manage — and pulls the querylog from there.
Each entry in the log carries the client IP, the requested domain, a UTC timestamp, and a flag
for whether the request was filtered. The script parses that stream, applies the noise filter,
and writes the surviving domain-client pairs into the SQLite database with counters and the
first- and last-seen timestamps.

Two modes cover both ends of the job:

- `baseline` reads the whole querylog file. AdGuard Home keeps roughly seven days of log on
  disk in a rotating file. The first time I run the script, the database is empty and every
  domain in the log is technically "new"; the baseline pass loads that whole window so the
  report has a reference set to compare against. The run also records a `baseline_ts` row in
  the database — the moment watching started.
- `tick` reads only the tail of the log — by default the last 8 MB, which on my network
  covers the last few hours — and is what I run on the regular schedule. It is cheap: a small
  file transfer over a local network, the whole loop finishes in a couple of seconds.

The cut-off for "new" in the report is the later of two values: "now minus N days" (default 7),
and the timestamp of the last baseline run. That second value matters. Without it, the report
would slowly back-fill itself with domains that were already in the log on day one — every
digest I run would tell me about a thousand things I have known for a year. With it, "new"
means "new since I started watching", and that window does not move unless I run `baseline`
again on purpose.

There is also a watchdog mode, and that is the part that has caught real bugs for me. When I
add a block rule to AdGuard — a new tracker or a domain family I want to drop at the DNS
level — I want to know that the rule is actually blocking. The script reads the blocklist file
(`ag_blocks.json`, which another piece of the system writes when a rule is added), looks up
each added domain in the local database, and prints the rules that have been queried since I
added them and yet still came through unfiltered. Wrong domain spelling, wrong rule syntax,
the rule added to the wrong AdGuard list — those all manifest as a request the database can
see and the blocker still let through. Empty output means every recent rule is doing what I
added it to do.

## Quick start

```bash
# Set environment variables
export ADGUARD_HOST="your-adguard-server"
export SSH_KEY_PATH="~/.ssh/adguard_key"
export DATABASE_PATH="./ag_scout.db"

# Run baseline collection (first time)
python3 ag_domain_scout.py --mode baseline

# Run incremental update
python3 ag_domain_scout.py --mode tick

# Generate report of new domains in last 7 days
python3 ag_domain_scout.py
```

The first run is `baseline`: it loads everything AdGuard currently has on disk into the local
SQLite file, sets the reference timestamp, and prints the report. Every later run on the
schedule is `tick` — pull the tail, append, print. The default SQLite path is `./ag_scout.db`;
I keep mine inside the Hermes working directory so it survives across sessions. The default
remote path of the querylog is `/opt/AdGuardHome/data/data/querylog.json`, which is where
AdGuard Home writes it on a standard install.

## Usage

```bash
python3 ag_domain_scout.py [options]

Options:
  --mode MODE          Mode: 'baseline' (full log) or 'tick' (recent entries) [default: tick]
  --days N             Report on domains newer than N days [default: 7]
  --tail-bytes N       Size of log tail to read in 'tick' mode [default: 8000000]
  --no-ingest          Show report only, don't update database
  --quiet              Quiet mode for cron jobs
  --alerts             Show only blocking problems
```

`--quiet` is what I actually run from cron (the scheduler that fires jobs at fixed times):
one line, one summary, no preamble. `--alerts` is the watchdog mode — only print the rules
that are not blocking, and print nothing at all when everything is fine, so an empty stdout
becomes the success signal and a non-empty one is what wakes me up.

## Outputs

A normal run produces three things:

- the SQLite database file at `DATABASE_PATH` (default `./ag_scout.db`), with one row per
  (client, domain) pair plus query counts and first/last-seen timestamps — the accumulating
  memory that makes "new" meaningful;
- a console report grouped by client: for each device, how many new domains appeared in the
  window, how many domains it has touched in total since the baseline, and the top entries
  by query count. Entries that were already blocked at the time of the request are marked
  `[already blocked]`;
- a short status block for the rules I have recently added: any rule that has been queried
  since I added it and yet never filtered a single request is flagged with a warning mark.
  Empty status block means everything is doing what I added it to do.

## Limitations

A few honest ones:

- The AdGuard Home server has to be reachable over SSH; no SSH, no querylog. If the network
  link is down, `tick` exits with an error and the cron run is logged as failing — there is
  no silent degradation, and no fabricated empty report.
- The parser depends on the `querylog.json` format staying as it is. AdGuard writes one JSON
  object per line with keys `IP`, `QH`, `T` and `Result.IsFiltered`; if the upstream format
  changes, the script will keep running and return empty or wrong output rather than throw
  an error. I check the report for emptiness on every run.
- Devices are identified through the `CLIENTS` mapping at the top of the script. Where it
  has no entry, the report falls back to `unknown/<ip>` — I had to fill that dictionary in
  once for the actual devices on my network, and on a router that hands out DHCP leases
  (DHCP is the protocol that hands IP addresses out to devices that join the network) the IPs
  drift over the weeks. A long-term fix would be matching on the AdGuard client name rather
  than the IP; I left it as IP because the format I receive from AdGuard over SSH gives me
  IP, not name.
- The noise filter is intentionally conservative. Some legitimate services use the same
  patterns as telemetry endpoints — anything ending in `.clerk.`, `.sentry.`, and so on is
  dropped wholesale, on the assumption that I would rather miss one legitimate domain in the
  report than bury the report under hundreds of tracker pings.

## Structure

```
ag_domain_scout.py     # Main script
README.md              # English documentation
README.ru.md           # Russian documentation
tests/test_domain_scout.py  # Unit tests
examples/              # Sample data
```

`ag_domain_scout.py` is 231 lines and runs on Python 3.10+. It uses only `argparse`, `json`,
`os`, `re`, `sqlite3`, `subprocess`, `sys` and `datetime` — all standard library, no
third-party dependencies, so it is portable across the same Python versions the rest of Hermes
already targets. The tests in `tests/test_domain_scout.py` cover the parser on valid and
malformed JSON, the noise filter against known telemetry patterns and against ordinary
domains, and the report-cut calculation; they use the real database functions and mock
`AGENT_HOME` and `CLIENTS` so they run with no live AdGuard behind them. The example file in
`examples/querylog_sample.txt` is five realistic entries — three valid, one `device.local`
that the noise filter must drop, one `.com` that must survive — and is what I keep around to
reproduce a parser bug without touching the live database.

## License

MIT