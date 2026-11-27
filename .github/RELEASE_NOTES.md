Xiaomi Mi 5 (gemini, MSM8996) kernel with the configuration layer Droidspaces needs.

Stock base: `MiCode/Xiaomi_Kernel_OpenSource` @ `scorpio-o-oss` (`3.18.71`, commit
`a36928ce4998125d9e71d1377a52d68cfe156872`), repacked into the stock MIUI 10 boot image
layout: only the gzip'ed `Image` is replaced — the 20 DTBs, the stock ramdisk and the
1,354-byte Qualcomm certificate are byte-identical to the ROM's own `boot.img`.

| | |
|---|---|
| `Image` | one Image, 33.6 MB, used by both boot images |
| boot images | `boot-mi5-droidspaces.img` (CN ROM), `boot-mi5-droidspaces-global.img` (global ROM) |
| vermagic | `3.18.71-perf-g4a0ef96 SMP preempt mod_unload modversions aarch64` |
| config changes vs stock | 27 options |
| boot image structure check | 26 / 26 PASS on both images |
| QEMU boot | reaches userspace, 6 / 6 markers PASS |

## Which image to flash

| ROM | File |
|---|---|
| MIUI 10 CN, e.g. `V10.2.1.0.OAACNXM` | `boot-mi5-droidspaces.img` |
| MIUI 10 global, e.g. `V10.2.2.0.OAAMIXM` | `boot-mi5-droidspaces-global.img` |

```sh
adb shell getprop ro.build.fingerprint
# ...V10.2.1.0.OAACNXM...  -> boot-mi5-droidspaces.img
# ...V10.2.2.0.OAAMIXM...  -> boot-mi5-droidspaces-global.img
```

Both files contain the **same kernel Image**; only the wrapper differs. The CN and the
global MIUI 10 build ship the identical kernel (same commit `g4a0ef96`, same config, same
compiler, both `Image` files 33,644,544 B), but their ramdisks differ in `default.prop`
(ROM version) and `sepolicy`, and the 20 DTBs are stored in a different order. Packing
into the wrong template usually still boots, but it then runs the other ROM's SELinux
policy.

## v1.0.2 — vendor modules load again

v1.0.1 booted, but it could not load a single factory module. MIUI's defconfig enforces
module signatures (`CONFIG_MODULE_SIG_FORCE=y`) and every `.ko` of a MIUI build is signed
with the key generated for that particular build. Only the stock `Image` carries the
matching public key, so a rebuilt kernel rejects all of them:

```
android.hardware.wifi@1.0-service: finit_module return: -1: Required key not available
android.hardware.wifi@1.0-service: Failed to load WiFi driver
```

That means no WiFi (`qca_cld_wlan.ko`), no exFAT and no `wil6210`. Measured on hardware
with `fastboot boot` (RAM only): the ROM's own global `boot.img` loads `exfat.ko` at boot
and `qca_cld_wlan.ko` as soon as WiFi is switched on; v1.0.1 loaded neither, and
`/sys/module` stayed empty of every external module.

`CONFIG_MODULE_SIG_FORCE=n` now — the ROM's own kernel does not enforce signatures either.
The modules load and the kernel is tainted with `module verification failed`, which is
expected and harmless. `scripts/build.sh` fails the build if the option ever comes back.

v1.0.2 also adds the global boot image: same `Image`, packed into the global ROM's own
`boot.img` template (byte-identical to `images/boot.img` of the global ROM package).

## v1.0.1 — the compiler, not the config

v1.0.0 was compiled with Ubuntu 20.04's `aarch64-linux-gnu-gcc` 9.4. On the phone
that `Image` hung at the MI logo and the bootloader reset it after ~10 s, before
`console_init()`, so `pstore` / `last_kmsg` stayed empty and no log was possible.

Bisecting on hardware with `fastboot boot` (loads into RAM, writes nothing)
isolated the compiler: the same tree, stock defconfig, patches and packer built
with gcc 9.4 fails; Xiaomi's own `Image` repacked by our packer boots; the full
release built with the AOSP `aarch64-linux-android-4.9` prebuilt — the compiler
the ROM's own `Image` reports — boots on the real device. Full evidence table in
`docs/BUILD-AND-QEMU.md` §1a.

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
- **Vendor modules** — `MODULE_SIG_FORCE=n`, see above.

Every other option — every MSM8996 driver, WiFi, modem, camera, audio, touch, charging,
thermal and debug option — keeps its stock value.

## Stock vendor modules

`qca_cld_wlan.ko`, `wil6210.ko`, `exfat.ko`, `br_netfilter.ko` and the rest of the ROM's
modules keep **all** of their imported symbols. Two loader checks have to be relaxed for
that, both documented in `docs/BUILD-AND-QEMU.md`:

- **signatures** — the modules are signed with Xiaomi's build key, which a rebuilt kernel
  does not have, so enforcement is off (`MODULE_SIG_FORCE=n`).
- **CRC** — adding the IPC namespace grows `struct task_struct`, which renumbers two
  thirds of the export table (6,328 of 9,378) without changing any struct a driver
  embeds. `patches/02-allow-crc-mismatch.patch` warns instead of refusing; missing
  symbols stay fatal, and the build fails if a critical module loses an import.

`dmesg` therefore shows a few `disagrees about version of symbol` warnings while the
modules load.

## Flash

```sh
fastboot flash boot boot-mi5-droidspaces-global.img   # or boot-mi5-droidspaces.img
fastboot reboot
```

Rollback: `fastboot flash boot bootimg/mi5_boot.img` (CN) or
`bootimg/mi5_boot_g.img` (global) — both stock images are in the repo.
A Mi 5 always enters fastboot with Vol- + Power, so a bad kernel is always recoverable.

## Limits of a 3.18 kernel

- no cgroup v2 and no cgroup namespace — Droidspaces uses its cgroup v1 "mixed mount" path
- no `--pids-limit` (`CGROUP_PIDS` does not exist here)
- Alpine / OpenRC is the safer choice; systemd on cgroup v1 may misbehave
- `--memory` and `--cpus` work (memcg + CFS bandwidth)

## Assets

| File | Contents |
|---|---|
| `boot-mi5-droidspaces.img` | flash on a CN ROM (`...CNXM`) |
| `boot-mi5-droidspaces-global.img` | flash on a global ROM (`...MIXM`) |
| `SHA256SUMS.txt` | sha256 of both boot images |
| `config-diff-release.txt` | every config change vs the stock defconfig |
| `crc-release.txt` | vendor module CRC comparison (per module, first 40 diffs) |
| `verify-boot.txt` | CN boot image structure check, 26 invariants |
| `verify-boot-global.txt` | global boot image structure check, 26 invariants |
| `qemu-serial.log` | QEMU boot of the same tree (PL011 console) |

Details: [README](https://github.com/jingbohi/mi5-droidspaces-kernel#readme) ·
[build and verification log](https://github.com/jingbohi/mi5-droidspaces-kernel/blob/main/docs/BUILD-AND-QEMU.md)
