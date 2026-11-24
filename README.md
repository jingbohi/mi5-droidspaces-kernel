# Mi 5 Droidspaces kernel (gemini / MSM8996)

Xiaomi Mi 5 (MIUI 10, Android 8.0, non-Treble) kernel with the configuration
layer Droidspaces needs, built from Xiaomi's public kernel source and repacked
into the **stock boot image layout**, so every vendor module and every original
driver keeps working.

| | |
|---|---|
| Device | Xiaomi Mi 5 `gemini` (MSM8996) |
| ROM base | `mi5_gemini_images_V10.2.1.0.OAACNXM_20181224.0000.00_8.0_cn` |
| Source | `MiCode/Xiaomi_Kernel_OpenSource` branch `scorpio-o-oss`, `3.18.71`, commit `a36928c` |
| Target vermagic | `3.18.71-perf-g4a0ef96 SMP preempt mod_unload modversions aarch64` |
| Toolchain | `aarch64-linux-gnu-gcc` 9.4 (Ubuntu 20.04) |
| Release | [v1.0.0](https://github.com/jingbohi/mi5-droidspaces-kernel/releases/tag/v1.0.0) — `boot-mi5-droidspaces.img` plus every verification report |

The ROM's own kernel commit `g4a0ef96` is not in the public tree, so the version
string is pinned with `CONFIG_LOCALVERSION="-perf-g4a0ef96"` +
`CONFIG_LOCALVERSION_AUTO=n`. Built from the untouched defconfig, this tree
reproduces the ROM kernel's symbol checksums exactly (1,082 of 1,085 imported
symbols match), which is the evidence that it is the same source the ROM was
built from — see [the CRC section](#vendor-module-compatibility-the-crc-question).

## Verified

The release is built by CI (`.github/workflows/build.yml`) from the same commit
these scripts produce locally, and its artifacts were re-checked with
`tools/verify_boot_mi5.py` and `tools/import_table.py` after download:

| Check | Result |
|---|---|
| `Image` | 35,735,040 B |
| boot image | 25,326,922 B (sha256 in `SHA256SUMS.txt`) |
| boot image structure | 26 / 26 checks PASS — DTBs, ramdisk, certificate, cmdline and addresses byte-identical to stock |
| config diff vs stock | 26 options (full list in `config-diff-release.txt`) |
| kernel exports | 9,410 symbols |
| vendor module CRC | 20 missing imports, all from the three factory test modules that also fail on stock; `br_netfilter`, `exfat`, `qca_cld_wlan`, `wil6210` import everything |
| QEMU boot | reaches userspace, 6 / 6 markers PASS (`qemu-serial.log`) |

The QEMU test boots the same tree with a PL011 console; it cannot exercise
MSM8996 hardware, but it does run the decompressor, page tables, SMP bring-up,
every initcall and a userspace process. Details: [docs/BUILD-AND-QEMU.md](docs/BUILD-AND-QEMU.md).

## Why this works on a stock ROM

The boot image is **not** rebuilt with mkbootimg. The stock `boot.img` is used as
a template and only the gzip'ed `Image` inside the kernel section is replaced:

```
 page 0        ANDROID! v0 header (4096 B, id digest recomputed)
 +4096         gzip(Image)  ||  20 stock DTBs
 page aligned  stock ramdisk (gzip)
 page aligned  second stage (size 0)
 page aligned  1354-byte Qualcomm certificate
```

`tools/verify_boot_mi5.py` re-checks 20+ invariants after packing (DTB chain
still parses as 20 FDTs, ramdisk/certificate/cmdline/addresses byte-identical,
digest correct, image fits the 64 MiB boot partition).

## What is added

Everything else stays at the stock value. `config/droidspaces.layer` is the
single source of truth; the CI prints the full resolved diff
(`config-diff-release.txt`) on every build.

| Area | Change |
|---|---|
| Namespaces | `UTS_NS` (stock explicitly disabled it), `IPC_NS`; `PID_NS`, `NET_NS`, `SECCOMP`/`SECCOMP_FILTER` were already on. `USER_NS` stays off — Droidspaces runs as root and only lists it as optional |
| IPC | `SYSVIPC`, `POSIX_MQUEUE` (required by `IPC_NS` on 3.18) |
| Cgroups (v1) | `CGROUP_DEVICE`, `MEMCG_SWAP_ENABLED` (the rest was already on) |
| Filesystems | `DEVTMPFS` (`DEVTMPFS_MOUNT` stays off), `OVERLAY_FS` |
| Network | `MACVLAN`, `NF_TABLES`/`NFT_NAT`/`NFT_MASQ`, IPv6 NAT (`IP6_NF_NAT`, `NF_NAT_IPV6`), `XT_TARGET_TCPMSS`, `XT_MATCH_ADDRTYPE` |
| Android | `ANDROID_PARANOID_NETWORK=n` — otherwise non-root uids cannot `socket()` inside a container |
| Versioning | `LOCALVERSION="-perf-g4a0ef96"`, `LOCALVERSION_AUTO=n`, `IKCONFIG_PROC=y` |

`ANDROID_PARANOID_NETWORK=n` removes the extra group-`AID_INET` gate on
`socket()`; per-app networking is still enforced by `netd`/iptables, not by the
kernel. If you would rather keep the stock gate, flip that one line in
`config/droidspaces.layer` — Droidspaces will then need services to run with
`inet` group membership.

## Vendor module compatibility (the CRC question)

The stock ROM loads 100+ prebuilt modules built against Xiaomi's own kernel.
`modversions` compares a checksum per imported symbol, and genksyms derives that
checksum from the **whole type graph reachable from the symbol**, not just its
signature.

`IPC_NS` needs `SYSVIPC` and/or `POSIX_MQUEUE`, which add `sysvsem`, `sysvshm`
and `mq_bytes` to `struct task_struct`. `task_struct` is reachable from
`struct mutex`, which is embedded in `struct device`, `struct module`,
`struct seq_file`, … so **6,328 of the 9,378 exports (67.5%) get a new
checksum** — measured by diffing the stock and the release `Module.symvers` —
even though **no driver-facing struct changed layout**. 32 exports are new
(macvlan, IPv6 NAT) and none disappeared.

Measured on this tree (`tools/abidiff.py`, genksyms `-D` dumps of
`drivers/pci/pci.o` and `fs/seq_file.o`): the *only* difference in
`task_struct`, `pci_dev`, `device`, `module`, `seq_file`, `mutex`, `pci_bus`,
`msi_controller` and `user_struct` is those three inserted fields; `file`,
`dentry`, `nsproxy`, `ipc_namespace`, `kernel_param` and `net` are byte
identical.

`patches/02-allow-crc-mismatch.patch` therefore turns the loader's
`disagrees about version of symbol` rejection into a rate-limited warning
(`check_version()` returns 1). Missing symbols are still fatal, and
`tools/crc_compare.py --strict` fails the build if any symbol a critical module
imports disappears.

Trade-off: a vendor module that really did break ABI would still load. This
kernel keeps every stock driver and every stock `struct` layout, so the only
realistic break would be a new option that changes a struct a driver uses —
which `config/droidspaces.layer` deliberately avoids.

If you would rather not touch the loader, remove that patch and drop `IPC_NS`,
`SYSVIPC` and `POSIX_MQUEUE` from `config/droidspaces.layer`; the build then
reports CRC mismatches (`crc_compare.py` without `--fail-on-mismatch`) but no
longer supports SysV IPC / POSIX mqueues inside containers.

## Limits of a 3.18 kernel

| Feature | Status |
|---|---|
| cgroup v2, cgroup namespace | **not available** — Droidspaces falls back to its cgroup v1 "mixed mount" path |
| `--pids-limit` (`CGROUP_PIDS`) | **not available** |
| Macvlan, veth/bridge, IPv4+IPv6 NAT, overlayfs, devtmpfs, seccomp filter | available |
| `--memory` / `--cpus` | available (memcg + CFS bandwidth) |
| Recommended distro | Alpine / OpenRC; systemd on 3.18/cgroup v1 may misbehave |

## Build

Locally (Linux or WSL, needs `gcc-aarch64-linux-gnu`, `bc`, `bison`, `flex`,
`libssl-dev`, `libelf-dev`, `python3`, and for the probe `qemu-system-arm` +
`cpio`):

```bash
scripts/build.sh release        # out-release/  dist/boot-mi5-droidspaces.img
scripts/build.sh probe          # out-probe/    dist/Image-probe (PL011 for QEMU)
scripts/qemu_probe.sh dist/Image-probe qemu-serial.log
```

The source tarball is downloaded once into `.work/kernel.tar.gz` (direct → local
proxy `127.0.0.1:1081` → error). To use an existing tree:

```bash
SRC=/root/mi5-kernel scripts/build.sh release
```

CI (`.github/workflows/build.yml`) builds both variants in an Ubuntu 20.04
container, runs the QEMU smoke test on the probe image, uploads artifacts, and
publishes a release when a `v*` tag is pushed.

## Flash and rollback

```bash
fastboot flash boot boot-mi5-droidspaces.img
fastboot reboot
```

Keep the stock image: `bootimg/mi5_boot.img` (this repo is the stock template).

```bash
fastboot flash boot bootimg/mi5_boot.img     # rollback
```

A boot loop is recoverable from `fastboot` (Mi 5 boots to fastboot with
Vol- + Power), so the stock image is always enough to get back.

## Repository layout

```
config/gemini_user_defconfig     stock defconfig, byte-identical to the ROM source
config/droidspaces.layer         the option delta (single source of truth)
config/probe.layer               PL011 + no Qualcomm secure monitor (QEMU only)
config/vendor-crc/*.versions     symbol CRCs of the stock vendor modules
config/stock-resolved.config     stock `make olddefconfig` result (diff base)
bootimg/mi5_boot.img             stock boot image used as repack template
patches/01-fix-xt-qtaguid-panic.patch    non-GKI crash fix, stock behaviour kept
patches/02-allow-crc-mismatch.patch      warn instead of refusing vendor modules
scripts/build.sh, qemu_probe.sh  build + VM smoke test
tools/                           defconfig generator, config/CRC/boot checkers,
                                 boot image extractor, probe_init.c (initramfs
                                 init for the QEMU probe)
.github/workflows/build.yml      CI: both variants, QEMU test, release on v* tags
.github/RELEASE_NOTES.md         release body (rendered on the release page)
docs/BUILD-AND-QEMU.md           evidence, verification log and design notes
```

## Credits

* Xiaomi / MiCode for the `scorpio-o-oss` kernel source.
* Droidspaces for the container runtime and its non-GKI kernel notes.

## License

The patches modify a GPL-2.0 kernel and are released under the same terms; the
scripts and tools in this repository are provided under GPL-2.0 as well.
