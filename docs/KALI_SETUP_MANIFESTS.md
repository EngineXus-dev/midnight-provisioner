# Kali guest setup plans and version snapshots (read-only)

This phase makes the curated [Kali toolkit profiles](KALI_TEMPLATES.md)
repeatable **without deploying an all-tools image**. Every template remains
an independent VM with its own disk, offline-first networking and a small,
curated software list.

The commands below do **not install tools, start a guest, create a VM,
connect to Kali mirrors, change SELinux, or overwrite local files**.

## 1. Generate a per-guest setup record

```bash
nightglass templates list
nightglass templates show recon

nightglass templates export recon /your/NEW/recon-plan.json
nightglass templates verify /your/NEW/recon-plan.json
```

Optionally use `--guest nightglass-kali-recon-b` to plan another independent
guest and `--iso-sha256 HASH` to record an externally obtained ISO digest.
An exported digest is **claimed**, not rehashed in this command. To
actually verify a local installer and inspect both virt-install dry-run XML
stages, use the separate `nightglass provision pentest --template recon
--iso ... --sha256 ...` workflow.

A setup plan is private `0600` JSON, exclusively created in an existing
folder. It stores the curated package IDs and catalog fingerprint, plus
`initial_network: none`, `status: PLANNED_ONLY`, null package versions,
false installation/guest-boot/dependency/provenance markers and recommended
resources. If the catalog or any safety flag changes, `templates verify`
**refuses** the stale or edited plan. Generate a **new** version rather than
silently trusting drift.

Saving plans through the GUI is available at
**Prepare VM → Kali toolkit → Save private Kali setup plan**. A path that
already exists (including symlinks) is rejected; no existing `.env`,
virtual environments, VM disks or workspace files are touched.

## Standalone guest inventory helper (source checkout)

A read-only Python 3 helper can query only the curated package set
**from inside a separately installed, benign Kali VM**, reducing hand-written
JSON. Use `nightglass templates guest-help PROFILE` or the GUI's
**Guest inventory instructions** button for guidance. The helper does not
run from Nightglass's host UI or cross any VM boundary; there is currently
**no integrated host/guest file-transfer channel**. Do not enable host
sharing, clipboard or USB passthrough to bypass that limitation. See
[manual offline guest collection](KALI_GUEST_INVENTORY.md).

## 2. Collect guest version information manually

After separately and explicitly installing a benign Kali guest with
virt-manager, installing *only the selected packages* in that guest,
and independently authorizing any Kali repository access, check its
software state from **inside the guest**. For example:

```bash
cat /etc/os-release
apt-cache policy nmap dnsrecon whois traceroute curl jq
dpkg-query -W nmap dnsrecon whois traceroute curl jq
dpkg --audit
```

These are read-only queries and are **not run by Nightglass**. Copy only
the package version metadata you wish to record into a small JSON document
on the host. For the Recon profile, the expected inventory schema is:

```json
{
  "format": "nightglass-kali-guest-inventory",
  "version": 1,
  "guest": "nightglass-kali-recon",
  "kali_release": "kali-rolling",
  "packages": [
    {"name": "nmap", "installed_version": "1.0", "candidate_version": "1.0"},
    {"name": "dnsrecon", "installed_version": "1.0", "candidate_version": "1.0"},
    {"name": "whois", "installed_version": "1.0", "candidate_version": "1.0"},
    {"name": "traceroute", "installed_version": "1.0", "candidate_version": "1.0"},
    {"name": "curl", "installed_version": "1.0", "candidate_version": "1.0"},
    {"name": "jq", "installed_version": "1.0", "candidate_version": "1.0"}
  ],
  "dpkg_audit_clean": null
}
```

The `1.0` values are **illustrative placeholders, not verified Kali
package versions**. Replace them with the actual installed and candidate
versions reported inside your own guest. Use `null` for an absent package
or a candidate not available from configured repositories.
`dpkg_audit_clean` is `true` only if you actually ran `dpkg --audit`
and reviewed its output as clean; otherwise use `null` or `false`.

**Do not** trust arbitrary community-provided JSON, submit credentials,
paste command output containing secrets, or run shell fragments from an
untrusted package list. The tool checks local file structure/values but
does not authenticate the guest, repositories or package publisher.

## 3. Compare and record versions, without installing

```bash
nightglass templates compare /your/NEW/recon-plan.json /your/inventory.json
nightglass templates lock /your/NEW/recon-plan.json /your/inventory.json /your/NEW/versions.json
```

The GUI's **Compare guest inventory** action performs the same read-only
comparison. It reports missing/uninstalled packages, unavailable candidates,
changed candidate versions, wrong VM identities, extra entries and a
self-reported `dpkg --audit` error. It never issues guest commands or
enables networking.

A version lock requires every curated package to have an installed
version and candidate plus a user-reported clean `dpkg --audit`. It writes
a **NEW** private local snapshot without overwriting files. It is
`VERSION_SNAPSHOT_ONLY`, with these explicit **false** assertions:
repository signature verified, dependency closure verified and rollback
snapshot verified. The snapshot hash is of the *submitted JSON*, **not**
an attestation of installed guest packages.

## Offline comparison against a previous saved version lock

The next phase can review a newer guest-reported package inventory against
an earlier `VERSION_SNAPSHOT_ONLY` record:

```bash
nightglass templates drift plan.json previous-lock.json new-inventory.json
```

The corresponding GUI action is **Review package version drift**. It
only reads the three local JSON files; no guest commands or downloads
run. A changed version is not automatically classified as upgraded or
downgraded. The lock is not cryptographically authenticated. See
[Kali version drift policy](KALI_VERSION_DRIFT.md).

## 4. Future gating before automated guest-side provisioning

- Test each profile inside a benign, supervised Fedora/KVM Kali guest.
- Independently verify Kali release/package availability and dependency
  footprints; capture apt signature/repository metadata and pinned versions.
- Verify a cold baseline/restore for **each separate VM** before package
  changes, including qcow2 and UEFI NVRAM.
- Measure network denial / SELinux runtime policy and recoverability.
- Only then consider explicit **guest-scoped** package automation and
  dedicated snapshots, never a combined all-tools VM or host execution.

This feature alone does **not** mean any Kali VM has been provisioned.
