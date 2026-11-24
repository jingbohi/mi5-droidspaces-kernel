#!/usr/bin/env python3
"""Generate the Mi 5 (gemini) Droidspaces defconfig from the stock one.

    python3 tools/mi5_config.py --src kernel \
        [--layer config/droidspaces.layer] [--extra config/probe.layer] \
        [--out-name mi5_droidspaces_defconfig]

Starts from arch/arm64/configs/gemini_user_defconfig, applies the options in
the layer file(s) and leaves dependency resolution to `make olddefconfig`.
The last layer passed wins when both set the same symbol.

Both layer files use one "SYMBOL=value" per line; blank lines and # comments
are ignored, value may be y, n, m or a quoted string.
"""
import argparse
import os
import re
import sys


def parse_layer(path):
    opts = []
    if not path:
        return opts
    if not os.path.isfile(path):
        sys.exit("missing layer file: %s" % path)
    for lineno, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            sys.exit("%s:%d: expected SYMBOL=value, got %r" % (path, lineno, raw.rstrip()))
        sym, val = line.split("=", 1)
        sym = sym.strip()
        if not re.match(r"^[A-Z0-9_]+$", sym):
            sys.exit("%s:%d: bad symbol name %r" % (path, lineno, sym))
        opts.append((sym, val.strip()))
    return opts


def set_opt(text, sym, val):
    text = re.sub(r'^(CONFIG_%s=[^\n]*\n|# CONFIG_%s is not set\n)' % (sym, sym),
                  "", text, flags=re.M)
    if not text.endswith("\n"):
        text += "\n"
    if val == "n":
        return text + "# CONFIG_%s is not set\n" % sym
    return text + "CONFIG_%s=%s\n" % (sym, val)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--layer", default="config/droidspaces.layer")
    ap.add_argument("--extra", default="", help="second layer, e.g. config/probe.layer")
    ap.add_argument("--out-name", default="mi5_droidspaces_defconfig")
    args = ap.parse_args()

    cfgdir = os.path.join(args.src, "arch/arm64/configs")
    stock = os.path.join(cfgdir, "gemini_user_defconfig")
    if not os.path.isfile(stock):
        sys.exit("missing %s" % stock)
    text = open(stock, encoding="utf-8", errors="surrogateescape").read()

    table = parse_layer(args.layer) + parse_layer(args.extra)
    if not table:
        sys.exit("no options to apply")
    for sym, val in table:
        text = set_opt(text, sym, val)

    out = os.path.join(cfgdir, args.out_name)
    with open(out, "w", encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        f.write(text)
    print("wrote %s (%d bytes, %d options forced)" % (out, len(text), len(table)))


if __name__ == "__main__":
    main()
