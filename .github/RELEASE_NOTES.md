Xiaomi Mi 5 (gemini, MSM8996) kernel with the configuration layer Droidspaces needs.

Stock base: `MiCode/Xiaomi_Kernel_OpenSource` @ `scorpio-o-oss` (`3.18.71`, commit
`a36928ce4998125d9e71d1377a52d68cfe156872`), repacked into the stock MIUI 10 boot image
layout: only the gzip'ed `Image` is replaced — the 20 DTBs, the stock ramdisk and the
1,354-byte Qualcomm certificate are byte-identical to the ROM's own `boot.img`.

| | |
|---|---|
| `Image` | 33,648,640 B |
| boot image | 24,700,234 B (sha256 in `SHA256SUMS.txt`) |
| vermagic | `3.18.71-perf-g4a0ef96 SMP preempt mod_unload modversions aarch64` |
| config changes vs stock | 26 options |
| boot image structure check | 26 / 26 PASS |
| QEMU boot | reaches userspace, 6 / 6 markers PASS |

## v1.0.1 — this one boots

v1.0.0 was compiled with Ubuntu 20.04's `aarch64-linux-gnu-gcc` 9.4. On the phone
that `Image` hung at the MI logo and the bootloader reset it after ~10 s, before
`console_init()`, so `pstore` / `last_kmsg` stayed empty and no log was possible.

Bisecting on hardware with `fastboot boot` (loads into RAM, writes nothing)
isolated the compiler: the same tree, stock defconfig, patches and packer built
with gcc 9.4 fails; Xiaomi's own `Image` repacked by our packer boots; the full
release built with the AOSP `aarch64-linux-android-4.9` prebuilt — the compiler
the ROM's own `Image` reports — boots on the real device. Full evidence table in
`docs/BUILD-AND-QEMU.md` §1a.

Nothing else changed: same source commit, same two patches, same 26 config
options, same boot image layout.

## What is added

- **Namespaces** — `UTS_NS` (the stock defconfig turned it off), `IPC_NS`; `PID_NS`,
  `NET_NS` and `SECCOMP_FILTER` were already enabled. `USER_NS` stays off on purpose:
  Droidspaces runs as root and only lists user namespaces as optional.
- **IPC** — `SYSVIPC`, `POSIX_MQUEUE` (required by `IPC_NS` on 3.18).
- **Cgroups v1** — `CGROUP_DEVICE`, `MEMCG_SWAP_ENABLED`.
- **Filesystems** — `DEVTMPFS`, `OVERLAY_FS`.
- **Network** — `MACVLAN`, `NF_TABLES` / `NFT_NAT` / `NFT_MASQ`, IPv6 NAT
  (`IP6_NF_NAT`, `NF_NAT_IPV6`), `XT_TARGET_TCPMSS`, `XT_MATCH_ADDRTYPE`.
- **Android** — `ANDROID_PARANOID_NETWORK=n`; with the stock value non-root uids cannot
  even call `socket()` inside a container.

Every other option — every MSM8996 driver, WiFi, modem, camera, audio, touch, charging,
thermal and debug option — keeps its stock value.

## Stock vendor modules

`qca_cld_wlan.ko`, `wil6210.ko`, `exfat.ko`, `br_netfilter.ko` and the rest of the ROM's
modules keep **all** of their imported symbols. `patches/02-allow-crc-mismatch.patch`
makes the loader warn instead of refusing when a genksyms checksum moved: adding the IPC
namespace grows `struct task_struct`, which renumbers two thirds of the export table
(6,328 of 9,378) without changing any struct a driver embeds. `dmesg` therefore shows a few
`disagrees about version of symbol` warnings while the modules load — missing symbols
are still fatal, and the build fails if a critical module loses an import.

## Flash

```sh
fastboot flash boot boot-mi5-droidspaces.img
fastboot reboot
```

Rollback: `fastboot flash boot bootimg/mi5_boot.img` (the stock image, also in the repo).
A Mi 5 always enters fastboot with Vol- + Power, so a bad kernel is always recoverable.

## Limits of a 3.18 kernel

- no cgroup v2 and no cgroup namespace — Droidspaces uses its cgroup v1 "mixed mount" path
- no `--pids-limit` (`CGROUP_PIDS` does not exist here)
- Alpine / OpenRC is the safer choice; systemd on cgroup v1 may misbehave
- `--memory` and `--cpus` work (memcg + CFS bandwidth)

## Assets

| File | Contents |
|---|---|
| `boot-mi5-droidspaces.img` | flash this |
| `SHA256SUMS.txt` | sha256 of the boot image |
| `config-diff-release.txt` | every config change vs the stock defconfig |
| `crc-release.txt` | vendor module CRC comparison (per module, first 40 diffs) |
| `verify-boot.txt` | boot image structure check, 26 invariants |
| `qemu-serial.log` | QEMU boot of the same tree (PL011 console) |

Details: [README](https://github.com/jingbohi/mi5-droidspaces-kernel#readme) ·
[build and verification log](https://github.com/jingbohi/mi5-droidspaces-kernel/blob/main/docs/BUILD-AND-QEMU.md)
