# Nightglass Security Model — version 0.1

## Boundaries

Nightglass is a desktop controller. It **does not provide** a new hypervisor, kernel-level isolation, mandatory access control, or a separate network firewall. The trusted computing base includes the Fedora host, kernel, KVM/QEMU, libvirt, desktop/display stack and firmware. Host root and other administrators can bypass all Nightglass policies. Nightglass is not a drop-in replacement for Qubes OS, and client compromise may cross VM boundaries through vulnerabilities in the underlying stack.

### Environments and policy

- `host`: native personal Fedora desktop. No separation from the host's own credentials or personal files.
- `trusted`: Distrobox, or a VM explicitly classified trusted. Distrobox shares home and display; no hostile code allowed. Trusted VMs receive only a warning and no mandatory networking restrictions.
- `lab`: Kali/authorized pentest. VM can have **no NIC**, or one or more NICs connected *only* to verified `nightglass-lab`. The `nightglass-lab` XML must have no `<forward>` element. This prevents automatic Internet routing but does **not** stop the guest from reaching host bridge services or peers; the host firewall must be separately reviewed.
- `isolated`: malware analysis. VM must have **no NIC**, host share, host physical device, USB redirect, shared memory device, vsock, guest agent/SPICE channel, host block disk, SPICE graphics or non-local display. Only `VNC` with localhost/unix socket or no graphics passes the display check. These restrictions are evaluated **at start time only**.

## Important security limitations / non-features

- **TOCTOU**: an authorized actor can modify VM XML between inspection and start. A libvirt lifecycle hook or purpose-built policy daemon would be required for stronger enforcement; even that is not a guarantee against host compromise.
- The 8-GB-class low-memory guard checks host RAM and refuses a second active VM or a guest larger than 3.5 GiB when issued through this controller. Other tools are not affected; these are resource guardrails, not security boundaries.
- An external `virt-manager`, `virsh`, or privileged user may start a VM Nightglass would block. Nightglass controls only Nightglass-issued launches.
- QEMU/emulated devices, virtual disk formats, CPU side channels and vulnerabilities in guest-host integration are separate attack surfaces. Consider offline dedicated hardware for high-risk analysis.
- VNC display uses localhost; desktop clipboard integration may still be provided by viewer extensions. Do not copy/paste samples or enable guest tools for hostile VMs. Do not interpret XML guardrails as a guarantee of blocked exfiltration.
- `nightglass-lab` does not provide an Internet-connected test network and will not prevent unauthorized use if bridged/forwarded externally outside this app. Use only systems/networks you are authorized to assess.
- No shared folders, clipboard brokers, USB device redirection, automatic file transfers, or filesystem mounting are implemented for restricted labs.
- No user-level network sandbox is provided for host processes. Personal browsing isn't isolated from development on the same Fedora desktop.
- Persistence of the VM virtual disk does **not** mean a clean restore exists. VM backups and baselines are separate requirements.

## Intended improvements before calling it hardened

1. Per-VM policy enforcement at libvirt lifecycle hook boundaries, using independent root-controlled policy records; no read-only GUI acting as policy authority.
2. AppArmor/SELinux verification on Fedora; disable SPICE channel/clipboard support in untrusted guests and restrict view sockets.
3. Firewall isolation for host/libvirt bridge; no host traffic from lab guest; deny-by-default egress for isolated domain.
4. Carefully tested disposable guest images and cold external snapshot workflow; verified guest rollback, NVRAM handling and disk integrity.
5. A quarantined, auditable file-transfer broker; never drag/drop raw samples into host.
6. Security validation on a dedicated Fedora host with real VMs and network instrumentation.

## Data and privileges

Configuration is JSON under `${XDG_CONFIG_HOME:-~/.config}/nightglass/workspaces.json`, written mode `0600`, and contains only workspace names, domain identifiers, policies and UI descriptions. Never add tokens or secrets here. Nightglass runs unprivileged and asks libvirt/polkit for authorization as applicable. Commands are built as fixed argument vectors, never by concatenating shell strings; workspace identifiers are validated. It does not require a background service or cloud account.
