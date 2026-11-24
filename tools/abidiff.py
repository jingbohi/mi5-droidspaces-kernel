#!/usr/bin/env python3
"""Compare struct definitions inside two genksyms -D dumps.

    python3 tools/abidiff.py stock.txt changed.txt

The dumps have one "Export sym == <expanded type>" line per exported symbol, with
struct definitions nested inline.  genksyms expands a struct in full the first
time it needs it and then refers to it by name, so the same struct appears
several times with different depth.  This takes the longest (fully expanded)
occurrence of every struct from both dumps and reports which ones really differ,
then word-diffs each difference so the actual member change is visible.

Exit code 1 if a struct in WATCH changed layout.
"""
import difflib
import re
import sys

WATCH = ["sk_buff", "net_device", "netdev_queue", "pci_dev", "device", "file",
         "sock", "socket", "dentry", "inode", "cfg80211_ops", "wiphy",
         "ieee80211_hw", "seq_file", "module", "kernel_param", "net",
         "skb_shared_info", "task_struct", "nsproxy", "ipc_namespace"]


def blocks(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    found = {}
    for m in re.finditer(r"struct ([A-Za-z_][A-Za-z_0-9]*) \{", text):
        name, i, depth = m.group(1), m.end() - 1, 0
        while i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[m.start():i + 1]
        prev = found.get(name)
        if prev is None or len(body) > len(prev):
            found[name] = body
    return found


def main():
    a, b = blocks(sys.argv[1]), blocks(sys.argv[2])
    common = sorted(set(a) & set(b))
    differ = [n for n in common if a[n] != b[n]]
    print("structs seen: %d / %d, identical %d, different %d"
          % (len(a), len(b), len(common) - len(differ), len(differ)))

    for n in differ:
        x, y = a[n].split(), b[n].split()
        print("\n== %s" % n)
        sm = difflib.SequenceMatcher(None, x, y)
        shown = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            print("   %-8s ...%s  ==>  %s..."
                  % (tag, " ".join(x[max(0, i1 - 4):i2]), " ".join(y[max(0, j1 - 4):j2])))
            shown += 1
            if shown >= 12:
                print("   ...")
                break

    print("\nwatched structs:")
    bad = 0
    for n in WATCH:
        if n not in a or n not in b:
            print("  %-18s not in dump" % n)
            continue
        ok = a[n] == b[n]
        if not ok:
            bad += 1
        print("  %-18s %s" % (n, "identical" if ok else "CHANGED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
