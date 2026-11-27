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
| vendor modules | the ROM's own `.ko` files load: `exfat`, `cfg80211`, `wlan` |
| WiFi | `wificond` up, `wlan0` UP, associates (5 GHz, 130 Mbps) |
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

## Stock vendor modules: two loader checks have to be relaxed

The ROM's `.ko` files are prebuilt against Xiaomi's own `Image`, and a rebuilt kernel
fails both of the loader's checks. Each one was isolated on hardware with `fastboot boot`
(loads into RAM, writes nothing):

### 1. Module signatures — `MODULE_SIG_FORCE=n`

MIUI's defconfig enforces signatures and every `.ko` of a MIUI build is signed with the
key generated for that build. Only the stock `Image` carries the matching public key, so
a rebuilt kernel rejects all of them:

```
android.hardware.wifi@1.0-service: finit_module return: -1: Required key not available
android.hardware.wifi@1.0-service: Failed to load WiFi driver
```

That silently removes WiFi (`qca_cld_wlan.ko`), exFAT and `wil6210`. Measured:
the ROM's own global `boot.img` loads `exfat.ko` at boot and `qca_cld_wlan.ko` when WiFi
is switched on; a kernel with the stock value loads no external module at all and
`/sys/module` stays empty of them.

`CONFIG_MODULE_SIG_FORCE=n` now — the ROM's own kernel does not enforce signatures
either. The modules load and the kernel is tainted with `module verification failed`,
which is expected and harmless. `scripts/build.sh` fails the build if the option comes
back.

### 2. WiFi — the AID → capability mapping

With the modules loading, WiFi was still dead: `wificond` was in a `SIGABRT` restart loop.

```
E wificond: Failed to set uevent socket SO_RCVBUFFORCE option: Operation not permitted
E wificond: Failed to setup synchronous netlink socket
F wificond: main.cpp:130] Check failed: netlink_manager.Start() Failed to start netlink manager
```

`SO_RCVBUFFORCE` needs CAP_NET_ADMIN, and the ROM starts `wificond` with group membership
instead of capabilities (`user wifi`, `group wifi net_raw net_admin`). The kernel turns
those groups into capabilities in `security/commoncap.c`, and that code is compiled only
under `CONFIG_ANDROID_PARANOID_NETWORK`:

```c
#ifdef CONFIG_ANDROID_PARANOID_NETWORK
	if (cap == CAP_NET_RAW && in_egroup_p(AID_NET_RAW))
		return 0;
	if (cap == CAP_NET_ADMIN && in_egroup_p(AID_NET_ADMIN))
		return 0;
#endif
```

The layer turns `ANDROID_PARANOID_NETWORK` off so non-root uids can `socket()` inside a
container, which compiled the mapping out and took CAP_NET_RAW/CAP_NET_ADMIN away from
`wificond`, `wpa_supplicant`, `hostapd`, `lowi`, `cnss-daemon` and non-root `ping`.

`patches/03-restore-aid-capabilities.patch` compiles the mapping unconditionally, so
containers keep the permissive `socket()` and the phone keeps its daemons. Measured:

| Kernel | `wificond` | `wlan0` | WiFi |
|---|---|---|---|
| ROM's own global `boot.img` | `running` | UP | associates, 5 GHz, 130 Mbps |
| `PARANOID_NETWORK=n`, no patch 03 | `restarting` (SIGABRT) | created then removed | dead |
| this kernel | `running` | UP | associates |

`scripts/build.sh` aborts if `security/commoncap.c` still guards the mapping, so the two
cannot drift apart.

### CRC warnings are expected

Adding the IPC namespace grows `struct task_struct`, which renumbers two thirds of the
export table (6,328 of 9,378) without changing any struct a driver embeds.
`patches/02-allow-crc-mismatch.patch` warns instead of refusing; missing symbols stay
fatal, and the build fails if a critical module loses an import. `dmesg` therefore shows
a few `disagrees about version of symbol` warnings while the modules load.

## What is added

- **Namespaces** — `UTS_NS` (the stock defconfig turned it off), `IPC_NS`; `PID_NS`,
  `NET_NS` and `SECCOMP_FILTER` were already enabled. `USER_NS` stays off on purpose:
  Droidspaces runs as root and only lists user namespaces as optional.
- **IPC** — `SYSVIPC`, `POSIX_MQUEUE` (required by `IPC_NS` on 3.18).
- **Cgroups v1** — `CGROUP_DEVICE`, `MEMCG_SWAP_ENABLED`.
- **Filesystems** — `DEVTMPFS`, `OVERLAY_FS`.
- **Network** — `MACVLAN`, `NF_TABLES` / `NFT_NAT` / `NFT_MASQ`, IPv6 NAT
  (`IP6_NF_NAT`, `NF_NAT_IPV6`), `XT_TARGET_TCPMSS`, `XT_MATCH_ADDRTYPE`.
- **Android** — `ANDROID_PARANOID_NETWORK=n` for container uids, plus patch 03 so the
  AID capability mapping survives (see above).
- **Vendor modules** — `MODULE_SIG_FORCE=n` (see above).

Every other option — every MSM8996 driver, WiFi, modem, camera, audio, touch, charging,
thermal and debug option — keeps its stock value.

## Toolchain

The ROM's `Image` reports `gcc version 4.9.x 20150123`, and this kernel has to be built
with that generation: an `Image` built from the same tree, config, patches and packer
with gcc 9.4 hangs at the MI logo before `console_init()`, so there is no log to read.
The release is built with the AOSP `aarch64-linux-android-4.9` prebuilt, and the
`Image` size lands within 4 KB of Xiaomi's own.

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
