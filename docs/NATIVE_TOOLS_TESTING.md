# Native libvirt/QEMU smoke tests (no VM boot)

Nightglass now has two independent verification layers.

1. Unit tests simulate libvirt calls and check that unsafe input is rejected.
2. Native integration tests use real libvirt XML schema tooling and QEMU
   image utilities against harmless, temporary test fixtures.

In GitHub Actions, the dedicated native-tools job installs libvirt-clients
and qemu-utils in an ephemeral Ubuntu runner, then runs the native tests.
The tests check a schema-valid offline VM definition, demonstrate that a
schema-valid guest NIC is still prohibited by the Nightglass offline policy,
create harmless 8-MiB qcow2/raw disks in a temporary directory, and verify
that a real QCOW2 external backing-file chain is rejected.

On Fedora, run from the project root:

    python3 -m unittest discover -s tests -p test_native_tools.py -v

The native test suite skips if those utilities are not installed; such a
skip is NOT native validation success. GitHub's native job explicitly
requires both utilities before running.

## What remains untested

- GitHub-hosted Ubuntu is not Fedora KDE on your machine.
- No real hypervisor, KVM device, VM registration, startup, guest boot, live
  packet-denial or firewall checks are part of the native test suite.
- A schema-valid VM definition can still be unsafe, incompatible or unbootable.
- Disk header checks do not prove the image content is benign or trustworthy.
- This workflow never changes local Windows partitions, UEFI or VM images.

Run the supervised Fedora/KVM acceptance procedure in FEDORA_ACCEPTANCE.md
with harmless guest images before enabling automatic VM import or treating
Nightglass as an isolation boundary.
