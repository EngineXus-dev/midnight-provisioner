# Live host resource pressure and external VM awareness

The Nightglass **Diagnostics → Refresh resource monitor** control enables
read-only monitoring of current host memory and system libvirt VM activity.
While Diagnostics is visible, the application refreshes approximately every
20 seconds. The command-line equivalent is:

```bash
nightglass resources
```

The CLI returns a nonzero status for CAUTION, CRITICAL or UNKNOWN so a script
cannot mistake incomplete inspection for an all-clear. It does not stop a
guest, change swap, edit libvirt configuration or invoke privilege elevation.

## What is measured

- **Available RAM** from Linux's `/proc/meminfo` `MemAvailable`, which
  includes reclaimable cache; low `MemFree` alone is not evidence of RAM
  exhaustion.
- **Swap occupancy**, when swap totals are available. Swap occupancy is
  not the same as current swapping activity or performance.
- **Guest concurrency**: every guest that `qemu:///system` lists as
  running, paused, idle, suspended or shutting down, including VMs launched
  through virt-manager or other libvirt clients.
- **Unbound active guests** not present in Nightglass's VM workspace bindings.
  They may be benign; they simply operate outside the app's launch guardrails.
- **Machine profile**: active VM count compared with the user preference,
  always capped by physical RAM and CPU resources.

### Advisory categories

| Status | Meaning |
|---|---|
| NORMAL | RAM appears comfortable and no known concurrency concerns |
| CAUTION | Memory pressure, high swap occupancy, a filled concurrency budget or unbound VM |
| CRITICAL | Less than 1 GiB available RAM or active VMs above the configured count |
| UNKNOWN | Host available RAM or the complete libvirt inventory could not be verified |

The app **does not assert that running a VM is safe** merely because the
resource status is NORMAL. It cannot protect memory reserved by the graphics
driver, predict guest usage, control other privileged hypervisor clients,
or guarantee host stability.

## Privacy and limitations

This is an in-memory status display and terminal output; no resource-history
database, telemetry or cloud requests are added. The read-only output may
include local VM names, so do not share it unredacted if those names are
private. No auto-start, auto-shutdown, VM reconfiguration, GPU throttling,
partition changes or persistent memory changes occur.

On a machine with multiple libvirt connections, the monitor reports
**system libvirt (`qemu:///system`) only**; guests in `qemu:///session` or
non-libvirt hypervisors are not counted. Any incomplete/failed state query
is treated as UNKNOWN instead of a green pass. The refresh interval is
best-effort and only active on the Diagnostics page after manual activation.

Hardware integration testing is still necessary on a real Fedora KDE machine,
especially one with 8 GiB RAM and an AMD integrated GPU.
