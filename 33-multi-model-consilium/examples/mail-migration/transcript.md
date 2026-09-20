# Consilium — author model vs reviewer model
_tokens: 25089 in / 15711 out, 262.8 s_

## Question

# Question

A small team runs its own mail server on a rented VM, mostly for their own domains. They are
considering moving it home, to a box behind a reverse SSH tunnel that keeps ports 25/465/587
pointed at a cheap public VPS.

What should the migration order be, what has to be verified before the MX record changes, and
what is the rollback trigger?


## 1. Plan (author) — `<author model>`

We need answer. Need think deeply. We have to formulate migration order, verify before MX changes, rollback trigger. At most 450 words. Need explicit assumptions. We are engineer. Need concise.

We need parse scenario: small team runs own mail server on rented VM, mostly own domains. Considering moving home, to box behind reverse SSH tunnel that keeps ports 25/465/587 pointed at cheap public VPS. So architecture: Home box runs mail server? Public VPS has SSH reverse tunnel forwarding public ports 25/465/587 to home box via SSH. Need migrate from rented VM to home. Need migration order, what verified before MX record changes, rollback trigger.

Important: mail server includes inbound SMTP (25), submission (465/587) likely outbound. MX record points domain to rented VM's hostname/IP. If moving home, MX should point to public VPS IP? Since tunnel on VPS exposes ports. Need ensure VPS IP/PTR etc.

Need consider reverse DNS, SPF, DKIM, DMARC, TLS certs, sending reputation, ports, firewall, dynamic IP home? But public VPS cheap, tunnel. Need verify home server works through tunnel before MX changes. Need avoid losing mail during cutover. Need sequencing.

Need identify migration order. Likely:

1. Set up home mail server (same software/config, accounts, data) but keep it in "dry run"/standby. Use rented VM as primary.
2. Set up public VPS with SSH tunnel to home server, listening on ports 25/465/587. Need make sure SSH auto-restarts, persistent, firewall, GatewayPorts, etc. But don't change MX yet. Need verify outbound (submission) through tunnel maybe by sending test from home to external mailbox and from external to home through public VPS. To test inbound before MX change, need run mail server on home box connected via tunnel; but external mail still goes to rented VM's MX. Can test by using "SMTP route" or directly connect to public VPS IP with `swaks` or telnet from external network. Need verify that port 25 on VPS reaches home mail server. Verify EHLO, STARTTLS, authentication, DKIM signing? Need have same hostname maybe.
3. Verify DNS prerequisites: MX for domains should point to hostname whose A record points to VPS IP. Need set up PTR for VPS IP to that hostname (must ask VPS provider). SPF include VPS IP or hostname; DKIM DNS records; DMARC. But before cutover? Need set DNS records but keep TTL low? Need plan.

Need "what has to be verified before MX record changes": 
- Public VPS has static IP, reverse DNS matches HELO hostname.
- Port 25/465/587 reachable from outside through VPS to home server; not blocked by home ISP / CGNAT? Actually tunnel outbound, no inbound needed at home. VPS must allow those ports inbound.
- Home server completes inbound SMTP transaction, accepts email for local domains, stores correctly, and can deliver outbound via submission through VPS. Need test using external mailbox: send mail to something on domain? But domain MX still old. Can test by using `SWAKS` to connect to VPS IP and deliver to a local alias; observe log. For outbound, submit a message through home server via VPS 587 to external address and verify headers (SPF/DKIM) pass.
- DNS settings: MX changed to target hostname with A at VPS. Need TTLs have been lowered before MX switch, maybe 5 min. Need wait TTL.
- DKIM selector DNS record for home server's private key present and correct; SPF updated to include VPS IP; PTR set. Need verify via `dig`.
- Sending IP reputation? VPS IP must not be blacklisted and should pass SPF/DKIM. Need check against Spamhaus/Barracuda.
- Mail client credentials/ports work through tunnel; TLS cert covers hostname used by clients (mail.domain), regardless network path. Need ensure hostname resolves? Clients connect to mail.domain (A record to VPS) before MX? Actually clients use mail domain A, not necessarily MX. So need point A record? Maybe already to rented VM; need later switch? Hmm.

Need think of domains: Their own domains, mail server mostly for own domains. MX changes: they probably host DNS somewhere. Migration order includes changing MX record. But before changing MX, we need ensure home server is fully operational behind tunnel. However if home server is behind tunnel and public VPS forwards port 25, but DNS MX still points to rented VM, mail to external test addresses won't go through home. But we can directly test SMTP by connecting to VPS IP from another server / using a test from Gmail? You can't make Gmail send to alternative MX unless using "SMTP test" direct connection. Need use `telnet`/`swaks` from another VPS to connect to VPS IP and deliver message to a recipient at domain. Or use an external service that allows SMTP send to arbitrary IP? But for verification, direct TCP test enough.

Need identify rollback trigger: Tied to what? Needs specific observable. "Rollback trigger" likely if during/after MX switch, mail flow failures beyond some threshold. Need define: If after MX change, inbound queue on VPS/home shows message loss / service unavailable, or outbound submission fails, or blacklisting occurs; trigger to change MX back to rented VM old IP? But if mail already queued/routed, changing MX back will cause some senders retry. Need monitor. Need define "two bounced legitimate messages" or "25 fails for 5 minutes"? Need be explicit. Need avoid data loss.

Need "migration order" maybe:

Phase 0: Prepare public VPS + home:
- Replicate mail data/config to home.
- Install/tune mail server.
- Start SSH tunnel from home to VPS: `autossh -R 25:localhost:25 -R 465:localhost:465 -R 587:localhost:587 user@vps -o ServerAliveInterval=15 -o ExitOnForwardFailure=yes`
- On VPS, configure SSH to GatewayPorts yes, firewall allow inbound 25/465/587 from any to local socket. But binding 25 on VPS requires root. Need `-o GatewayPorts=yes`, `-R 0.0.0.0:25:localhost:25`. Need ensure VPS doesn't run its own mail service.

Phase 1 Verify transport:
- From external host, `smtp-check` connect to VPS IP port 25 and do SMTP session. Test AUTH/STARTTLS on 465/587.
- Test inbound delivery to alias/domain by injecting message.
- Test outbound via home server's submission to external and check headers.
- Test tunnel resilience: restart tunnel, reboot home; ensure auto-reconnect and port remains open.

Phase 2 DNS prep:
- Lower TTLs on MX, A, SPF, DKIM/DMARC? Existing rDNS point? Need wait old TTL.
- Set PTR for VPS IP to `mail.example.com`; create/update A record for `mail.example.com` to VPS IP? But if MX currently points to `mail.example.com` and A is currently rented VM, changing A before MX effectively sends mail to new server before MX switch? Actually if MX is `mail.example.com`, then changing A to VPS routes SMTP to new home server via VPS. That is a way to cutover without changing MX if hostname same. Need coordinate. But if we change A before MX, external MTAs send to VPS; that's a cutover. It should be done only after verification. In DNS migration, MX record itself may remain same hostname; only A record changes = cutover. Then "before MX record changes" may not be relevant if MX stays same. But question explicitly says "before the MX record changes" so assume MX record points to another hostname/old IP. Need include checking by `dig MX` after update.

Actually many setups: MX records point to `mail.example.com`. If we move from rented VM to home behind VPS, we could keep DNS name `mail.example.com` and change A record to VPS IP. That is not "MX record changes" but equivalent. But the question asks "what has to be verified before the MX record changes" perhaps they will create new MX to public VPS hostname. Need answer both.

Need distinguish: MX record should not be changed until:
- Home server fully configured, data synced, and receives over tunnel.
- Public VPS rDNS matches the hostname that will be in MX/A; SPF includes VPS IP; DKIM DNS is live.
- TTL for old MX/A has expired after lowering.
- The tunnel's public listener is up and stable; if it breaks, you can roll back by DNS, but tunnel must be redundant? Need maybe set systemd service.

Need "rollback trigger": What event should make you flip MX back? Need defined. Since mail is safety-critical, trigger should be "any legitimate message that fails acceptance/queue retention after 5 minutes" or "can't send/receive through tunnel during test window". But after MX switch, if VPS is reachable but mail server not accepting, sending mail will repeatedly retry; you can notice. Need define threshold. Need likely "two test messages to/from external addresses fail after MX TTL has elapsed" or "smoke test succeeds then within first hour no message has been received within 10 min" etc.

Need craft plan with "checks prove step worked". Need 450 words max. Need be concrete.

Let's plan answer structure:

- Assumptions: home ISP permits outbound SSH (no port blocking); VPS is Linux with root and static IP; DNS provider allows low TTL; rented VM can remain available during rollback; mail server software is replicated.
- Order:
  1. Stand up VPS and tunnel as non-authoritative relay; don't alter DNS.
  2. Sync mail data/config from rented VM to home; verify service starts on home.
  3. Harden tunnel: autossh/systemd, GatewayPorts, firewall. Prove: from a third-party host `openssl s_client -connect <VPS_IP>:465 -starttls smtp` and EHLO returns home mail server; `nc -vz <VPS_IP> 25/465/587` success.
  4. Functional tests through VPS: submit test message from home to external via 587; use `swaks --to external --server <VPS_IP> --port 587 --auth` and check DKIM/SPF; inject inbound via `swaks --from external --to user@domain --server <VPS_IP>` and verify it appears in mailbox. Prove MTA queue logs show successful delivery/no bounce.
  5. DNS preparation: lower TTLs to 300s; wait old TTL. Set SPF to include VPS IP, set DKIM selector, set PTR for VPS IP to public hostname (mail.domain), ensure HELO uses that hostname. Prove with `dig -x <VPS_IP>`, `dig TXT`, `dig DKIM`; run `smtp-header` test to see `Received: from ...` etc.
  6. Cutover: change MX (or A) to VPS IP/public hostname, keep old MX as secondary? Actually if old rented VM still runs mail server, can include as lower-priority MX until home is stable. This is useful. Maybe migration order include "set new MX priority 10 to VPS; keep old MX priority 20" to allow fallback. But if old as backup, mail to old might not have new data? Better if data synced. But with backup MX, if tunnel down, mail goes to old VM, causing split brain if later delivered? Need mention. Simpler: change MX exclusively after tests. Or use old as backup with lower priority but must forward/accept and be reconfigured? Too complex.

Need "rollback trigger": Have a defined trigger: If, after MX cutover, the home server does not process any inbound/outbound test message within 10 minutes, or an SMTP connection to VPS gets refused, or two external senders report delays/bounces, revert DNS (MX back to old) and kill tunnel? Actually reverting MX triggers queued mail to retry to old VM. If old VM still running with same mailboxes, no loss. Need make sure old VM kept in read-only? We'll keep rented VM as standby with synchronized data until cutover stable. Good.

Need "what has to be verified before MX changes" perhaps several categories. Need include "send a test to your domain through external SMTP, but direct to VPS IP", "PTR", "SPF/DKIM/DMARC" and "TLS certificate". Need maybe mention "don't change MX before tests using external MTA direct to VPS IP pass".

Need be careful: 465 is implicit TLS, 587 STARTTLS. Need tunnels both.

Need word count. Need avoid filler. Need maybe use bullets.

Need decide on rollback trigger as "any of: VPS port 25 unreachable for >5 min; home server logs connection timeout; an inbound test to a real mailbox fails while SMTP listener is nominally up; SPF/DKIM fail for outbound test" — but after MX change, if tunnel fails, mail to domain will be queued, not bounced immediately. Trigger maybe "if the tunnel has been down for 5 minutes, switch MX back to old VM; if tunnel stays up but mail queue > 10 messages or oldest > 5 min, rollback." Need define "rollback trigger" as concrete event to act. Need say "Roll back the moment one of these is observed: (1) `ss -ltn` on VPS shows no listener on 25, or (2) a test message to the domain does not arrive in home mailbox within 10 minutes, or (3) an outbound test via 587 returns 5xx after auth. Then change MX back to rented VM's IP, leave tunnel down, restore A/PTR if changed."

Need also mention "before MX record changes" includes "old rented VM must still be running as fallback, and data sync must be as current as possible" to enable rollback. Good.

Let's craft final answer, 450 word max. Need include assumptions. Let's write succinct.

Potential final:

**Assumptions**: home ISP allows outbound SSH; VPS has root/static IP; DNS TTL can be lowered; old VM can stay alive after cutover.

**Order**

1. Replicate mail system to home box: same MTA version, users, maildirs, TLS keys, DKIM keys. Sync mail stores daily. Verify home daemon starts on its own LAN.
2. Build tunnel: `autossh -R 0.0.0.0:25:localhost:25 ...` on home; same for 465/587. On VPS enable `GatewayPorts yes`, firewall only those ports. Run under systemd, `Restart=always`.
   Check: from a separate host, `nc -vz VPS 25/465/587`; `swaks --to user@domain --server VPS` reaches home mailbox and appears in logs.
3. Test outbound through new path: submit from home client via 587/VPS to external address. Check headers contain DKIM signature aligned with domain and SPF passes.
   Check tunnel resilience: restart home box; autossh re-establishes; VPS listener returns.
4. Before MX switch:
   - Lower DNS TTLs (MX/SPF/A) to 300s; wait old TTL expiry.
   - Set PTR for VPS IP to public HELO hostname; verify `dig -x`.
   - Update SPF to include VPS IP; add/check DKIM TXT; DMARC.
   - Verify public VPS not on any RBL.
   - Keep old VM running and current as rollback target.
   - Prove with `swaks` from external to VPS IP using HELO/PTR and `openssl s_client` that TLS cert matches `mail.domain` and mail is delivered to home.
5. Cutover: change MX to `mail.domain` (or update A if MX already points to `mail.domain`) to VPS IP. Wait for TTL; send test in/out.

**Rollback trigger**: If any of these occur during the first 24h: VPS port 25 stops listening; a test external→domain message fails to reach home mailbox within 10 min; submission auth fails with 535; home server logs 'connection refused' or external sender reports bounce.

[reply truncated by the token limit — raise --max-tokens]

## 2. Attack (reviewer) — `<reviewer model>`

**Review: Critical Holes**

**1. Source IP visibility is destroyed by the tunnel.** All inbound SMTP connections appear to originate from 127.0.0.1 on the home box. This silently breaks RBL lookups, per-IP rate limiting, fail2ban, and any `permit_mynetworks` logic. The plan doesn't mention this. Checkable: after tunneling, run `postconf smtpd_client_restrictions` and send a test — watch logs show `client=unknown[127.0.0.1]`.

**2. Outbound path is ambiguous.** The plan says "submit via 587/VPS to external address" but doesn't specify whether the home MTA relays through the VPS or sends directly from the home IP. If direct from home: residential IP, no matching PTR, likely on dynamic ranges → deferred/rejected by Gmail, Outlook, and most corporate filters. If via VPS relay: the plan never configures a relay on the VPS. This must be explicit.

**3. Port 25 inbound on VPS is not guaranteed.** Many budget providers block inbound port 25 by default or require an abuse-team request. The plan says "firewall allow" but never says "confirm with provider that port 25 is not filtered upstream." Checkable: `nc -l 25` on VPS, connect from outside.

**4. No monitoring for tunnel failure.** The plan says autossh restarts, but doesn't address detection. If the tunnel drops at 3 AM, mail queues at sending servers — some retry for 5 days, some bounce in hours. No alerting is specified. Checkable: what happens to `ss -tlnp :25` on the VPS when the home box loses connectivity? (The listener stays up but returns connection refused or timeouts — indistinguishable from a dead server unless you probe end-to-end.)

**5. Rollback trigger is not actionable.** "Any legitimate message that fails" — how do you detect this? No log query, no threshold, no monitoring endpoint. You need: "if end-to-end probe (external → VPS:25 → home mailbox) fails for 5 consecutive minutes, flip MX back." The plan must define the probe.

**6. Split-brain during cutover.** MX TTL hasn't fully expired globally, so mail arrives at both old VM and home box simultaneously. The plan says "keep old VM running" but never explains how you reconcile mailboxes — IMAP sync? rsync? Forward all from old to new? This is unresolved data loss risk.

**7. Unverified claim: home connection reliability.** A 99% uptime home link means ~7 hours of downtime per month. No SLA, no dual-WAN, no mention of testing connection stability over days before cutover.

## 3. Final plan (author answers the attack) — `<author model>`

I accept all seven objections; none are safely dismissed. Revised plan:

**Preconditions**
- Ask VPS provider to confirm inbound and outbound port 25 is allowed and PTR is settable. If not, stop.
- Soak-test the home link for at least 7 days while the old VM remains primary. Require total tunnel downtime under 5 minutes and no outage longer than 2 minutes. Do not cut over unless that passes.

**Architecture changes**
- Run the VPS as an edge SMTP relay, not just an SSH port-forwarding target.
- Preserve source-IP visibility using PROXY protocol or equivalent; if your MTA cannot parse it, do RBL/rate-limiting/fail2ban on the VPS and have the home box accept only from the VPS.
- Make outbound mail relay through the VPS with authentication. Home IP must never send directly to external MXes.

**Build and verification before MX change**
- Replicate configs/mailboxes to home. Configure the old VM, after cutover, to forward any residual or late mail to home via a dedicated dedicated path; no local authoritative delivery on old VM.
- Set up an external black-box probe every minute: connect to VPS IP:25, send EHLO/MAIL/RCPT to a unique alias, and confirm the message reaches the home mailbox. Require 100% success for 24 hours and <2-minute delivery latency.
- Test outbound through VPS relay to a Gmail or Outlook temporary address; check SPF/DKIM/DMARC pass and no 5xx.
- Verify provider-level port-25 access, PTR, SPF, DKIM, TLS certificate, RBL status, and that DNS TTLs were lowered and expired.

**Cutover**
- Change MX to the VPS hostname; keep old VM as low-priority MX configured to forward to home. Wait for TTL and rerun the probe.

**Rollback trigger**
- Flip MX back to the old VM if the black-box probe fails for 5 consecutive minutes, an accepted probe message fails to appear in the home mailbox within 2 minutes, or outbound relay returns 5xx for 5 consecutive probes. Do this immediately, before users notice, and keep the new path down until diagnosed.
