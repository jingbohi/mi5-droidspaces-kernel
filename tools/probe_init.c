/*
 * Minimal init for the QEMU probe.
 *
 * scripts/qemu_probe.sh cross-compiles this statically, packs it as /init into
 * a tiny initramfs and boots the probe kernel with it.  Without a userspace the
 * kernel panics in mount_root() before it ever prints "Freeing unused kernel
 * memory", so the probe could not tell a working kernel from one that dies in
 * the last initcall.
 *
 * It is freestanding (no libc, -nostdlib) so the probe needs nothing but the
 * cross compiler that is already required to build the kernel.
 *
 * The marker goes to /dev/kmsg as well as to fd 1: on QEMU's virt machine the
 * PL011 device is dropped after a single -EPROBE_DEFER in 3.18's
 * of_amba_device_create(), so /dev/console never opens and fd 1 is closed.  A
 * kmsg write still reaches the boot console, which is exactly what the serial
 * log captures.
 */
#define AT_FDCWD   (-100)
#define O_WRONLY   1
#define SYS_openat 56
#define SYS_write  64
#define SYS_pause  29

static long syscall1(long n, long a)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	__asm__ volatile("svc #0" : "+r"(x0) : "r"(x8) : "memory");
	return x0;
}

static long syscall3(long n, long a, long b, long c)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	__asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory");
	return x0;
}

static long syscall4(long n, long a, long b, long c, long d)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	__asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2), "r"(x3) : "memory");
	return x0;
}

static const char marker[] = "PROBE: userspace init reached\n";
static const char kmsg_path[] = "/dev/kmsg";

void _start(void)
{
	long fd;

	syscall3(SYS_write, 1, (long)marker, sizeof(marker) - 1);

	fd = syscall4(SYS_openat, AT_FDCWD, (long)kmsg_path, O_WRONLY, 0);
	if (fd >= 0)
		syscall3(SYS_write, fd, (long)marker, sizeof(marker) - 1);

	for (;;)
		syscall1(SYS_pause, 0);
}
