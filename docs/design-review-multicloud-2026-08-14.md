# Design Review (DR) — multi-cloud certificate deployment

**Agent:** cs-devsecops-engineer (Riley) · **Pass:** DR · **Date:** 2026-08-14T11:46:11Z
**Scope:** extending TLS certificate automation from OTC ELB only to AWS, Azure and GCP.
**Status:** review completed **before** implementation, per the design-review-first rule.

Evidence is cited as `local://<repo-relative-path>` against branch `fix/otc-elb-best-effort`.
No code-host MCP connector resolved for this review (it is a pre-implementation design, not a
PR diff), so the PR-diff axis is **UNKNOWN** and confidence is capped accordingly.

---

## 1. What the current single-cloud path actually does

| Aspect | Current state | Evidence |
|---|---|---|
| OTC credential | Static username + password, project-scoped | `local://cert_automation/.env.example` (`OS_USERNAME`, `OS_PASSWORD`) |
| Key material in transit | Private key posted in a JSON body to the ELB API | `local://cert_automation/otc_elb_client.py:57-67` |
| Key material at rest | Written under `CERT_BASE_PATH`, default `/tmp/certs` | `local://cert_automation/.env.example`, `local://cert_automation/main.py:432` |
| Directory permissions | `os.makedirs(...)` with no mode — inherits umask | `local://cert_automation/acme_client_wrapper.py:133` |
| Key material in logs | Never logged | grep for `log.*key_content` returns nothing |
| Destructive capability | Same credential can delete certificates | `local://cert_automation/otc_elb_client.py:144` |
| Failure semantics | `OTC_ELB_BEST_EFFORT` opt-in, default false; failures still logged at ERROR and marked `advisory` | `local://cert_automation/main.py` |

**Correction to the brief.** The best-effort path was described to me as "silently swallows
failures". It does not. It is opt-in, defaults to `false`, logs at ERROR, and tags the result
`advisory` so the report still carries it. The design problem is not silence — it is that the
flag is **global**, so enabling it for one unreachable target downgrades every target.

---

## 2. Design decisions

### D1 — No static credentials for the new providers. **Required.**

The OTC path uses a long-lived username/password. Do not replicate that model three more times.
All three new providers support federated, short-lived credentials from CI with no stored secret:

| Provider | Mechanism | Stored secret |
|---|---|---|
| AWS | OIDC → `sts:AssumeRoleWithWebIdentity` | none |
| Azure | Workload identity federation → service principal | none |
| GCP | Workload Identity Federation → service account impersonation | none |

This removes three long-lived secrets from CI and makes credential rotation a non-event.
It is also the single largest security delta between this design and the existing OTC path.

**Residual:** the CI provider's OIDC issuer becomes a trust anchor. Scope each cloud-side trust
policy to a specific repository *and* ref, never to the issuer alone.

### D2 — Deploy and delete are separate capabilities. **Required.**

`otc_elb_client.delete_certificate()` shares a credential with the deploy path
(`local://cert_automation/otc_elb_client.py:144`). A compromised deploy credential can therefore
delete production certificates — an availability attack, not just a confidentiality one.

Split into two roles per provider: `cert-deploy` (import + bind) and `cert-reap` (delete).
The reaper runs as a separate, explicitly-gated job. Carry this back to the OTC path too.

### D3 — Minimum IAM per provider. **Required.**

Grant exactly these, resource-scoped where the provider allows it:

| Provider | Deploy role | Reap role (separate) |
|---|---|---|
| AWS | `acm:ImportCertificate`, `acm:AddTagsToCertificate`, `elasticloadbalancing:ModifyListener`, `elasticloadbalancing:DescribeListeners` | `acm:DeleteCertificate`, `acm:ListCertificates` |
| Azure | `Microsoft.KeyVault/vaults/certificates/import/action`, `.../secrets/read` on the one vault; `Microsoft.Network/applicationGateways/read` + `/write` scoped to the gateway | certificate delete on the one vault |
| GCP | `certificatemanager.certs.create`, `certificatemanager.certs.update`, `compute.targetHttpsProxies.update` | `certificatemanager.certs.delete` |

Do not use `acm:*`, Key Vault Certificates Officer, or `roles/certificatemanager.editor`.

**Note on AWS:** `acm:ImportCertificate` without a resource condition can overwrite *any*
certificate in the account by ARN. Constrain by resource ARN or tag condition, or the deploy
role is effectively account-wide over TLS.

### D4 — Private key handling. **Required.**

- Create the certificate directory mode `0o700` explicitly; do not rely on umask.
  `os.makedirs(path, mode=0o700, exist_ok=True)` — and note `makedirs` ignores `mode` on
  existing directories, so `os.chmod` after is needed for the idempotent case.
- Default `CERT_BASE_PATH` away from `/tmp`. A predictable path in a shared-tmp environment is
  a symlink-swap target.
- Keep the existing property that key material never reaches logs. Add a test asserting it,
  because this is the kind of invariant a future debug line quietly breaks.
- Python cannot reliably zero a `str`, so minimise lifetime instead: read, upload, drop the
  reference. Do not hold key content on a long-lived object attribute.

### D5 — Per-target failure policy replaces the global best-effort flag. **Required.**

Replace `OTC_ELB_BEST_EFFORT` with a per-target field in the target config:

```yaml
targets:
  - provider: aws
    policy: required     # a failure here fails the run (default)
  - provider: otc
    policy: advisory     # logged, reported, does not fail the run
```

Default `required`. The process exit code reflects any `required` failure. This keeps the good
property of the current implementation (failures are always logged and reported) while removing
the bad one (one unreachable target downgrades all of them).

### D6 — Bind before reap, never reap before bind. **Required.**

Order per provider: import new certificate → verify it is present and valid → bind to the
listener/proxy → verify the listener serves the new certificate → only then queue the old one
for the gated reaper. A failure at any step leaves the previous working certificate bound.

### D7 — Provider isolation. **Required.**

One credential per provider per environment. No shared identity across providers. A compromise
of the AWS role must not yield Azure or GCP access. With D1 this is largely automatic, since
each provider federates independently.

---

## 3. Blast radius

| Compromised | Reachable with D1–D7 | Reachable without them |
|---|---|---|
| CI job token | Short-lived creds for the duration of one job, deploy-only, resource-scoped | Three long-lived cloud credentials with delete rights |
| AWS deploy role | Import/bind certs on the scoped listeners | Any ACM certificate in the account, plus delete |
| One provider | That provider only | Only that provider (already isolated) |
| Cert storage dir | Key material if mode is umask-default in shared `/tmp` | same |

---

## 4. Residual risk rating

| Risk | Likelihood | Impact | Residual | Owner |
|---|---|---|---|---|
| CI OIDC trust policy scoped too broadly (issuer, not repo+ref) | Medium | High | **Medium** | implementer |
| `acm:ImportCertificate` unconstrained by resource | Medium | High | **Medium** | implementer |
| Key material readable in shared tmp before D4 lands | Low | High | **Medium** | implementer |
| Deploy credential retains delete (OTC path today) | Low | Medium | **Medium** | implementer |
| Provider API change breaks bind-verify | Medium | Low | **Low** | implementer |
| Long-lived static credential reintroduced for convenience | Medium | High | **Medium** | reviewer at merge |

**Overall residual risk with D1–D7 implemented: MEDIUM.**
**Overall residual risk if the OTC static-credential model is copied to three more providers: HIGH.**

This rating is attached to the implementation. It is not a claim that the control is complete —
D1–D7 are design commitments, and none has been verified in code at the time of this review.

---

## 5. Gate verdict

**Proceed to implementation, conditional on D1–D7.**

Blocking conditions for the merge gate:
1. No static long-lived credential for AWS, Azure or GCP (D1).
2. Deploy role carries no delete permission (D2, D3).
3. Certificate directory created `0o700` and defaulted off `/tmp` (D4).
4. Per-target failure policy, defaulting to `required` (D5).
5. A test asserting key material never reaches log output (D4).

---

```json
{
  "agent_slug": "cs-devsecops-engineer",
  "intent_type": "advise",
  "action": "Proceed to implementation of multi-cloud certificate deployment conditional on design decisions D1-D7; block merge if any of the five gate conditions is unmet.",
  "rationale": "The existing single-cloud path authenticates with a static username/password that also carries certificate-delete rights, and writes private key material to a umask-default directory under /tmp. Replicating that model across three additional providers would triple a known-weak credential pattern. All three target providers support federated short-lived credentials from CI at no cost, so the secure option is also the simpler one.",
  "confidence": 0.7,
  "severity": "medium",
  "key_findings": [
    "OTC path uses a static, project-scoped username/password (OS_PASSWORD) - must not be replicated per-provider",
    "Deploy credential also carries delete_certificate, making a deploy-credential compromise an availability risk",
    "Certificate directory is created with os.makedirs and no mode, defaulting under /tmp/certs",
    "Key material is correctly never logged today; no test protects that invariant",
    "OTC_ELB_BEST_EFFORT is global, so enabling it for one unreachable target downgrades every target",
    "acm:ImportCertificate without a resource condition is effectively account-wide over TLS"
  ],
  "evidence_references": [
    {"source": "local://cert_automation/.env.example", "note": "OS_USERNAME/OS_PASSWORD static credential surface"},
    {"source": "local://cert_automation/otc_elb_client.py", "note": "upload_certificate posts private key; delete_certificate shares the credential"},
    {"source": "local://cert_automation/acme_client_wrapper.py", "note": "os.makedirs without mode for cert storage"},
    {"source": "local://cert_automation/main.py", "note": "CERT_BASE_PATH default and global best-effort handling"}
  ],
  "next_agents": [],
  "human_approval_required": false,
  "timestamp_utc": "2026-08-14T11:46:11Z",
  "gaps": [
    "No code-host MCP connector resolved: this is a pre-implementation design, not a PR diff. The PR-diff axis is UNKNOWN and confidence is capped at 0.7.",
    "No cloud connector resolved: IAM policy recommendations are from provider documentation, not read from a live account."
  ]
}
```
