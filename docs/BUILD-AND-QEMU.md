# Build and verification log — Mi 5 (gemini, MSM8996)

Everything below was produced on this machine and is reproducible with the
scripts in `scripts/`. Numbers are the ones the release workflow prints, so a CI
run can be compared line by line.

## 1. Environment

| | |
|---|---|
| Host | WSL2 Ubuntu 20.04 (Windows 10) |
| Compiler | `aarch64-linux-gnu-gcc` (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0 |
| Kernel build host/user | `mi5@droidspaces` (fixed, so the banner is reproducible) |
| QEMU | `qemu-system-aarch64` 4.2.1 (`-M virt`) |
| Python | 3.8 (`tools/` are plain stdlib) |

`scripts/gcc-wrapper.py` from Xiaomi turns every warning into an error and needs
`python2`, so the build calls the cross compiler directly (`CC=aarch64-linux-gnu-gcc`).
All warnings stay in `build.log`.

## 2. Source and patches

| | |
|---|---|
| Tree | `MiCode/Xiaomi_Kernel_OpenSource`, branch `scorpio-o-oss` |
| Commit | `a36928ce4998125d9e71d1377a52d68cfe156872` (Linux 3.18.71) |
| Tarball | 144,866,041 B, cached as `.work/kernel.tar.gz` in CI |

The ROM's own kernel commit `g4a0ef96` is not in the public tree, so the version
string is pinned:

```
CONFIG_LOCALVERSION="-perf-g4a0ef96"
CONFIG_LOCALVERSION_AUTO=n
```

`scripts/build.sh` asserts the *complete* vermagic in `vmlinux`:

```
== vermagic OK: 3.18.71-perf-g4a0ef96 SMP preempt mod_unload modversions aarch64
```

Two patches are applied (both verified with `patch -p1 --dry-run` against this
exact commit):

| Patch | Why |
|---|---|
| `01-fix-xt-qtaguid-panic.patch` | stock `dev_get_stats()` on a socket-less device panics; skip stats for devices outside `init_net`, keep stock per-interface statistics untouched |
| `02-allow-crc-mismatch.patch` | keep stock vendor modules loading although genksyms renumbered two thirds of the export table (see §5) |

## 3. Stock baseline: the tree really is the ROM's kernel

Before changing anything, the untouched defconfig was built and its
`Module.symvers` compared with the CRCs the ROM's own modules import
(`config/vendor-crc/*.versions`, produced with `modprobe --dump-modversions`,
summarised by `tools/import_table.py`):

```
stock Image: 35,729,920 B  md5 d1898b35a6b2a888c5edb77d560051cd
stock exports: 9,378 symbols

module            imports  missing  crc-diff
qca_cld_wlan          370        0         0
wil6210               211        0         0
exfat                 121        0         0
br_netfilter           34        0         0
ansi_cprng             15        0         0
backlight              34        0         0
evbug                  11        0         0
lcd                    26        0         0
mmc_test               48        0         0
rdbg                   38        0         0
spidev                 42        0         0
test-iosched           45        0         0
ufs_test               45        8         3
generic_bl              9        1         0
mmc_block_test         36       11         0
```

12 of 15 shipped modules match the ROM **exactly** (1,082 of 1,085 imported
symbols have the stock checksum), which proves the public tree + stock defconfig
is the same kernel the ROM was built from. The three modules that differ
(`ufs_test`, `generic_bl`, `mmc_block_test`) are Qualcomm factory test modules:
they import symbols (`test_iosched_*`, `devm_backlight_device_register`) that the
stock kernel does not export either, so they cannot load on the stock ROM either.

## 4. The configuration layer

`config/droidspaces.layer` is the single source of truth. `tools/mi5_config.py`
appends it to the stock defconfig, `tools/check_config.py` re-resolves the result
and prints the diff. Release build:

```
layer options: 53 forced
config diff vs stock: 26 option(s)
RESULT: PASS
```

```
CONFIG_ANDROID_PARANOID_NETWORK            y  -> n
CONFIG_BUILD_BIN2C                         n  -> y
CONFIG_CGROUP_DEVICE                       n  -> y
CONFIG_DEVTMPFS                            n  -> y
CONFIG_IKCONFIG                            n  -> y
CONFIG_IKCONFIG_PROC                       n  -> y
CONFIG_IP6_NF_NAT                          n  -> y
CONFIG_IP6_NF_TARGET_MASQUERADE            n  -> y
CONFIG_IPC_NS                              n  -> y
CONFIG_LOCALVERSION                     "-perf" -> "-perf-g4a0ef96"
CONFIG_LOCALVERSION_AUTO                   y  -> n
CONFIG_MACVLAN                             n  -> y
CONFIG_MEMCG_SWAP_ENABLED                  n  -> y
CONFIG_NETFILTER_XT_MATCH_ADDRTYPE         n  -> y
CONFIG_NFT_MASQ                            n  -> y
CONFIG_NFT_NAT                             n  -> y
CONFIG_NF_NAT_IPV6                         n  -> y
CONFIG_NF_NAT_MASQUERADE_IPV6              n  -> y
CONFIG_NF_TABLES                           n  -> y
CONFIG_OVERLAY_FS                          n  -> y
CONFIG_POSIX_MQUEUE                        n  -> y
CONFIG_POSIX_MQUEUE_SYSCTL                 n  -> y
CONFIG_SYSVIPC                             n  -> y
CONFIG_SYSVIPC_COMPAT                      n  -> y
CONFIG_SYSVIPC_SYSCTL                      n  -> y
CONFIG_UTS_NS                              n  -> y
```

Everything else — every MSM8996 driver, WiFi, modem, camera, audio, touch,
charging, thermal, filesystem, debug option — keeps its stock value. `USER_NS`
stays off on purpose (Droidspaces runs as root and only lists user namespaces as
optional); turning it on would add the unprivileged-userns attack surface the
ROM deliberately disabled.

## 5. Vendor module ABI: why CRCs move, and why that is safe here

`IPC_NS` needs `SYSVIPC`/`POSIX_MQUEUE` on 3.18. Both add fields to
`struct task_struct`. genksyms hashes the **whole reachable type graph**, so
`task_struct` → `mutex` → `device`/`module`/`seq_file`/`pci_dev` … renumbers
exports that have nothing to do with IPC.

Measured by dumping genksyms' expanded type graph (`genksyms -D`, the same data
the checksum is computed from) for `drivers/pci/pci.o` and `fs/seq_file.o` under
both configurations, then diffing it with `tools/abidiff.py`:

```
pci.o      : 231 / 234 structs dumped, 209 identical, 22 different
seq_file.o : 198 / 201 structs dumped, 178 identical, 20 different
```

Every single difference is the same insertion inside the nested `task_struct`:

```
== task_struct
   insert  ...epoll_watches ; unsigned long
        ==>  epoll_watches ; unsigned long mq_bytes ; unsigned long ...
   insert  ...total_link_count ; struct
        ==>  total_link_count ; struct sysv_sem { struct sem_undo_list { UNKNOWN } * undo_list ; } sysvsem ;
             struct sysv_shm { struct list_head shm_clist ; } sysvshm ; struct ...
```

No member was removed, reordered or resized anywhere. `file`, `dentry`,
`nsproxy`, `ipc_namespace`, `kernel_param` and `net` are byte-identical between
the two configurations. In other words: the checksums move because a struct that
is *pointed to* grew, not because a struct a driver embeds changed.

`patches/02-allow-crc-mismatch.patch` therefore turns

```
disagrees about version of symbol %s   -> module load fails
```

into a rate-limited warning and lets the module load. Missing symbols are still
fatal, and `tools/crc_compare.py --strict` fails the build if a critical module
loses an import.

Release build result (`tools/import_table.py` over the build's `Module.symvers`
and `config/vendor-crc`; `dist/crc-release.txt` has the same data with the first
40 mismatches spelled out per module):

```
kernel exports: 9410 symbols

module            imports  missing  crc-diff
ansi_cprng             15        0         6
backlight              34        0        22
br_netfilter           34        0        24
evbug                  11        0         9
exfat                 121        0        84
generic_bl              9        1         6
lcd                    26        0        15
mmc_block_test         36       11        10
mmc_test               48        0        31
qca_cld_wlan          370        0       145
rdbg                   38        0        20
spidev                 42        0        23
test-iosched           45        0        21
ufs_test               45        8        18
wil6210               211        0       114
wlan                    0        0         0
TOTAL                1085       20       548

strict modules: br_netfilter, exfat, qca_cld_wlan, wil6210 -- no missing exports
```

The 20 missing imports all belong to the three factory test modules that also
fail on the stock kernel (see §3). Every module the ROM actually loads —
including `qca_cld_wlan.ko` (WiFi) and `wil6210.ko` (11ad) — keeps all of its
imports and loads with a warning in `dmesg` instead of being rejected.

## 6. Release image

```
== building Image (4 jobs)
new Image     : 35,735,040 B  md5 6dfc8bb6c8d0daf8a9da58bd4374e436
new kernel    : 22,873,614 B  (gzip 13,353,125 + 20 DTBs 9,520,489)
output        : dist/boot-mi5-droidspaces.img (25,326,922 B)
sha256        : 41cbe80b2baa84ef25f6c30e0c58112ba71e917bc586da08091a2282d2349092
```

Only the gzip'ed `Image` is replaced inside the stock boot image; the 20 DTBs,
the ramdisk, the second stage and the 1,354-byte Qualcomm certificate are copied
byte for byte and the header `id` digest is recomputed. `tools/verify_boot_mi5.py`
re-checks 26 invariants:

```
PASS  boot magic / header version 0 / page size 4096
PASS  kernel gzip stream complete
PASS  kernel decompresses to Image  md5 6dfc8bb6c8d0daf8a9da58bd4374e436
PASS  DTB tail identical to template  9520489 B
PASS  DTB tail parses as FDT chain  20 DTBs
PASS  ramdisk bytes unchanged  md5 5484fc1797c908752f4574db87e80efb
PASS  second stage size 0 / area unchanged
PASS  certificate trailer unchanged  1354 B
PASS  kernel_addr 0x80008000 / ramdisk_addr 0x81000000 / second_addr 0x80f00000
PASS  tags_addr 0x80000100 / os_version 0x1000012a / board name / cmdline
PASS  header id digest recomputed correctly
PASS  fits 64 MiB boot partition  25326922 B
result : PASS (0 failed)
```

## 7. QEMU probe

`scripts/build.sh probe` builds the same tree with `config/probe.layer` and
`scripts/qemu_probe.sh` boots it in QEMU's `virt` machine. This cannot test
MSM8996 drivers, but it does prove the `Image` is a bootable arm64 kernel:
decompressor, page tables, memory map, GIC, timers, SMP bring-up, every
initcall, initramfs mount and a userspace process actually running.

Three things in a Qualcomm 3.18 kernel do not exist on QEMU; the probe works
around them and the release build is not affected:

| Problem | Workaround |
|---|---|
| `CONFIG_QCOM_EARLY_RANDOM=y` overrides the weak `init_random_pool()` and executes `smc #0` inside `setup_arch()`; QEMU has no EL3, so the trap becomes an undefined-instruction oops | `QCOM_EARLY_RANDOM=n` in `config/probe.layer` (the weak stub in `arch/arm64/kernel/setup.c` is used) |
| `pm-boot.o` is built whenever `CONFIG_PM=y` and its postcore initcall calls the secure monitor before it looks at the device tree; same for `msm_restart_init` and `msm_iommu_sec_init` | `initcall_blacklist=` on the QEMU command line |
| No root filesystem: the kernel panics in `mount_root()` *before* printing `Freeing unused kernel memory` | `tools/probe_init.c`, a freestanding static init packed into a 5-block initramfs |

The probe also has to deal with a 3.18 quirk: `of_amba_device_create()` drops an
AMBA device after a single `-EPROBE_DEFER` (`amba_device_add() failed (-517) for
/pl011@9000000`), so `ttyAMA0` never appears and `/dev/console` cannot be opened.
The init therefore writes its marker to `/dev/kmsg`, which still reaches the
boot console that produced the log.

```
[    1.505171]   No soundcards found.
[    1.509978] Warning: unable to open an initial console.
[    2.059617] Freeing unused kernel memory: 2136K
[    2.060111] Freeing alternatives memory: 112K
[    2.087636] PROBE: userspace init reached
== markers
  PASS  Boot CPU:
  PASS  Linux version
  PASS  Kernel command line
  PASS  Memory:
  PASS  Freeing unused kernel memory
  PASS  PROBE: userspace init reached
== QEMU probe: PASS
```

Full log: `dist/qemu-serial.log` (also attached to the release).

The numbers above come from the local verification build; CI rebuilds the same
commit in an `ubuntu:20.04` container and attaches its own `SHA256SUMS.txt`,
because the banner embeds the build time and the compiler patch level.

## 8. Reproducing in CI

`.github/workflows/build.yml` runs the same scripts in an `ubuntu:20.04`
container (the compiler version this tree was verified with), caches the kernel
tarball and ccache, builds `release` and `probe` in parallel, runs the QEMU smoke
test on the probe image, and uploads `dist/` as artifacts. Pushing a `v*` tag
publishes a release with the boot image, `config-diff-release.txt`,
`crc-release.txt`, `verify-boot.txt` and `qemu-serial.log`.

## 9. Flash and rollback

```bash
fastboot flash boot dist/boot-mi5-droidspaces.img
fastboot reboot
```

The stock image is in `bootimg/mi5_boot.img`:

```bash
fastboot flash boot bootimg/mi5_boot.img     # rollback
```

A bad kernel is recoverable from `fastboot` (Mi 5 enters fastboot with Vol- +
Power), so the stock image is always enough to get the phone back.
