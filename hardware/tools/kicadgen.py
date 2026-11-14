#!/usr/bin/env python3
"""
kicadgen - shared helpers for generating KiCad 10 projects from Python.

Usage (see gen_backplane.py):

    p = Project("backplane", outdir, lib="trs80_backplane", title=..., paper="A2")
    p.stock("Device", "R")                              # load stock symbols
    p.ic("74HCT244", "U", desc, fp, left=[...], right=[...])   # custom symbols
    p.place("U1", "trs80_backplane:74HCT244", "74HCT244", fp, x, y, {pin: net})
    p.power("+5V", x, y, flag=True)
    p.text("...", x, y)
    p.write()

Every symbol pin must be assigned a net name or 'NC'; nets are joined by
local labels on short wire stubs. Power nets (+5V, +3V3, GND) use power
symbols. UUIDs are deterministic (stable regeneration).
"""
import copy
import math
import os
import re
import shutil
import sys
import uuid

KICAD_SHARE = r"C:\Program Files\KiCad\10.0\share\kicad"
POWER_NETS = ("+5V", "+3V3", "GND")

I, O, B, T, P, OC, NCT, PO, PAS = ("input", "output", "bidirectional", "tri_state", "power_in",
                                   "open_collector", "no_connect", "power_out", "passive")


# ------------------------------------------------------------------ s-expr
def parse(text):
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack = [[]]
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t)
    return stack[0]


def ser(x, ind=0):
    if not isinstance(x, list):
        return x
    out, first, nl = "(", True, False
    for c in x:
        if isinstance(c, list):
            out += "\n" + "\t" * (ind + 1) + ser(c, ind + 1)
            nl = True
        else:
            out += ("\n" + "\t" * (ind + 1) + c) if nl else (("" if first else " ") + c)
        first = False
    return out + ("\n" + "\t" * ind if nl else "") + ")"


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def unq(t):
    return t[1:-1].replace('\\"', '"').replace("\\\\", "\\") if t.startswith('"') else t


def f(v):
    v = round(float(v), 4)
    s = ("%.4f" % (0.0 if v == 0 else v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def child(node, head):
    for c in node:
        if isinstance(c, list) and c and c[0] == head:
            return c
    return None


def effects(size=1.27, justify=None):
    e = ["effects", ["font", ["size", f(size), f(size)]]]
    if justify:
        e.append(["justify"] + justify.split())
    return e


def prop(name, val, x, y, ang=0, hide=False, justify=None):
    p = ["property", q(name), q(val), ["at", f(x), f(y), f(ang)]]
    if hide:
        p.append(["hide", "yes"])
    p.append(effects(justify=justify))
    return p


# ------------------------------------------------------------------ project
class Project:
    def __init__(self, name, outdir, lib, title, rev="0.1", date="", comments=(), paper="A2",
                 root_uuid=None):
        self.name, self.outdir, self.lib = name, outdir, lib
        self.title, self.rev, self.date, self.comments, self.paper = title, rev, date, comments, paper
        self.root = root_uuid or str(uuid.uuid5(uuid.NAMESPACE_URL, "kicadgen/" + name))
        self._ns = uuid.uuid5(uuid.NAMESPACE_URL, "kicadgen-items/" + name)
        self._n = 0
        self.syms = {}           # lib_id -> dict(node, pins, props)
        self.custom = []         # nodes for the project symbol library
        self.items = []
        self.used = set()
        self.labels = {}
        self.footprints = {}     # name -> sexpr node (project .pretty)
        self._pwr = 0
        self._flg = 0

    def uid(self):
        self._n += 1
        return str(uuid.uuid5(self._ns, str(self._n)))

    # ---------------------------------------------------------- symbols
    def _register(self, libid, node):
        pins, props = {}, {}
        for c in node:
            if isinstance(c, list) and c and c[0] == "property":
                at = child(c, "at")
                props[unq(c[1])] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0)
        for sub in node:
            if not (isinstance(sub, list) and sub and sub[0] == "symbol"):
                continue
            m = re.match(r".*_(\d+)_(\d+)$", unq(sub[1]))
            if not m or int(m.group(1)) not in (0, 1) or int(m.group(2)) not in (0, 1):
                continue
            for p in sub:
                if isinstance(p, list) and p and p[0] == "pin":
                    at = child(p, "at")
                    pins[unq(child(p, "number")[1])] = (float(at[1]), float(at[2]), int(float(at[3])))
        self.syms[libid] = dict(node=node, pins=pins, props=props)

    def stock(self, lib, name):
        path = os.path.join(KICAD_SHARE, "symbols", lib + ".kicad_sym")
        tree = parse(open(path, encoding="utf-8").read())[0]
        for c in tree:
            if isinstance(c, list) and c[:2] == ["symbol", q(name)]:
                if child(c, "extends"):
                    sys.exit("stock symbol %s:%s is derived; pick a base symbol" % (lib, name))
                node = copy.deepcopy(c)
                node[1] = q(lib + ":" + name)
                self._register(lib + ":" + name, node)
                return
        sys.exit("stock symbol %s:%s not found" % (lib, name))

    def ic(self, name, ref, desc, fp, left, right, half_w=10.16, datasheet=""):
        """Rectangular symbol; left/right lists of (num, name, type) or None (gap)."""
        n = max(len(left), len(right))
        ytop = math.ceil((n - 1) / 2) * 2.54
        ybot = ytop - (n - 1) * 2.54
        pins, seen = [], set()
        for side, lst in (("L", left), ("R", right)):
            for i, p in enumerate(lst):
                if p is None:
                    continue
                num, pname, ptype = p
                if num in seen:
                    sys.exit("duplicate pin %s in %s" % (num, name))
                seen.add(num)
                x = -(half_w + 2.54) if side == "L" else (half_w + 2.54)
                pins.append(["pin", ptype, "line", ["at", f(x), f(ytop - i * 2.54), "0" if side == "L" else "180"],
                             ["length", "2.54"], ["name", q(pname), effects()], ["number", q(num), effects()]])
        rect = ["rectangle", ["start", f(-half_w), f(ytop + 2.54)], ["end", f(half_w), f(ybot - 2.54)],
                ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]
        node = ["symbol", q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"],
                ["in_bom", "yes"], ["on_board", "yes"],
                prop("Reference", ref, 0, ytop + 5.08), prop("Value", name, 0, ybot - 5.08),
                prop("Footprint", fp, 0, ybot - 7.62, hide=True), prop("Datasheet", datasheet, 0, 0, hide=True),
                prop("Description", desc, 0, 0, hide=True),
                ["symbol", q(name + "_0_1"), rect], ["symbol", q(name + "_1_1")] + pins,
                ["embedded_fonts", "no"]]
        self.custom.append(copy.deepcopy(node))
        emb = copy.deepcopy(node)
        emb[1] = q(self.lib + ":" + name)
        self._register(self.lib + ":" + name, emb)

    # ---------------------------------------------------------- placement
    def label(self, net, x, y, ang):
        just = {0: "left bottom", 180: "right bottom", 90: "left bottom", 270: "right bottom"}[ang]
        self.items.append(["label", q(net), ["at", f(x), f(y), str(ang)], effects(justify=just),
                           ["uuid", q(self.uid())]])
        self.labels[net] = self.labels.get(net, 0) + 1

    def place(self, ref, libid, value, fp, X, Y, pins, desc=None):
        S = self.syms[libid]
        self.used.add(libid)
        missing, extra = set(S["pins"]) - set(pins), set(pins) - set(S["pins"])
        if missing or extra:
            sys.exit("%s: missing pins %s, unknown pins %s" % (ref, sorted(missing), sorted(extra)))
        in_bom = (child(S["node"], "in_bom") or ["in_bom", "yes"])[1]
        on_board = (child(S["node"], "on_board") or ["on_board", "yes"])[1]
        inst = ["symbol", ["lib_id", q(libid)], ["at", f(X), f(Y), "0"], ["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", in_bom], ["on_board", on_board], ["dnp", "no"],
                ["uuid", q(self.uid())]]
        for pname, pv in (("Reference", ref), ("Value", value), ("Footprint", fp), ("Datasheet", None),
                          ("Description", desc or "")):
            if pv is None:
                pv = next((unq(c[2]) for c in S["node"]
                           if isinstance(c, list) and c[:2] == ["property", q("Datasheet")]), "")
            px, py, pa = S["props"].get(pname, (0, 0, 0))
            hide = pname in ("Footprint", "Datasheet", "Description") or ref.startswith("#")
            if libid.startswith("power:") and pname == "Value":
                hide = False
            inst.append(prop(pname, pv, X + px, Y - py, pa, hide=hide))
        for num in S["pins"]:
            inst.append(["pin", q(num), ["uuid", q(self.uid())]])
        inst.append(["instances", ["project", q(self.name), ["path", q("/" + self.root),
                                                            ["reference", q(ref)], ["unit", "1"]]]])
        self.items.append(inst)
        if libid.startswith("power:"):
            return
        for num, (px, py, pa) in S["pins"].items():
            net = pins[num]
            ax, ay = X + px, Y - py
            if net == "NC":
                self.items.append(["no_connect", ["at", f(ax), f(ay)], ["uuid", q(self.uid())]])
                continue
            dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[pa]
            ex, ey = ax + dx * 2.54, ay + dy * 2.54
            self.items.append(["wire", ["pts", ["xy", f(ax), f(ay)], ["xy", f(ex), f(ey)]],
                               ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(self.uid())]])
            if net in POWER_NETS:
                self.power(net, ex, ey)
            else:
                self.label(net, ex, ey, {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}[(dx, dy)])

    def power(self, net, x, y, flag=False):
        self._pwr += 1
        if "power:" + net not in self.syms:
            self.stock("power", net)
        self.place("#PWR%03d" % self._pwr, "power:" + net, net, "", x, y, {"1": net})
        if flag:
            if "power:PWR_FLAG" not in self.syms:
                self.stock("power", "PWR_FLAG")
            self._flg += 1
            self.place("#FLG%02d" % self._flg, "power:PWR_FLAG", "PWR_FLAG", "", x, y, {"1": net})

    def flag(self, net, x, y):
        """PWR_FLAG on a non-power-symbol net (e.g. a battery rail), joined by a label."""
        if "power:PWR_FLAG" not in self.syms:
            self.stock("power", "PWR_FLAG")
        self._flg += 1
        self.place("#FLG%02d" % self._flg, "power:PWR_FLAG", "PWR_FLAG", "", x, y, {"1": net})
        self.label(net, x, y, 0)

    def text(self, s, x, y, size=1.8):
        self.items.append(["text", q(s), ["exclude_from_sim", "no"], ["at", f(x), f(y), "0"],
                           effects(size=size, justify="left top"), ["uuid", q(self.uid())]])

    # ---------------------------------------------------------- output
    def check_footprints(self):
        bad = []
        for it in self.items:
            if it[0] != "symbol":
                continue
            for c in it:
                if isinstance(c, list) and c[:2] == ["property", q("Footprint")] and unq(c[2]):
                    nick, name = unq(c[2]).split(":")
                    if nick == self.lib:
                        if name not in self.footprints:
                            bad.append(unq(c[2]))
                    elif not os.path.exists(os.path.join(KICAD_SHARE, "footprints", nick + ".pretty",
                                                         name + ".kicad_mod")):
                        bad.append(unq(c[2]))
        if bad:
            sys.exit("missing footprints: %s" % sorted(set(bad)))

    def write(self):
        self.check_footprints()
        refs = []
        for it in self.items:
            if it[0] == "symbol":
                for c in it:
                    if isinstance(c, list) and c[:2] == ["property", q("Reference")] and not unq(c[2]).startswith("#"):
                        refs.append(unq(c[2]))
        dup = sorted({r for r in refs if refs.count(r) > 1})
        if dup:
            sys.exit("duplicate references: %s" % dup)
        for net, n in sorted(self.labels.items()):
            if n < 2:
                sys.exit("net %s has only one connection" % net)
        os.makedirs(os.path.join(self.outdir, self.lib + ".pretty"), exist_ok=True)
        tb = ["title_block", ["title", q(self.title)], ["date", q(self.date)], ["rev", q(self.rev)]]
        for i, c in enumerate(self.comments):
            tb.append(["comment", str(i + 1), q(c)])
        sch = ["kicad_sch", ["version", "20250610"], ["generator", q("eeschema")],
               ["generator_version", q("10.0")], ["uuid", q(self.root)], ["paper", q(self.paper)], tb,
               ["lib_symbols"] + [self.syms[l]["node"] for l in sorted(self.used)]] + self.items + \
              [["sheet_instances", ["path", q("/"), ["page", q("1")]]], ["embedded_fonts", "no"]]
        w = lambda fn, s: open(os.path.join(self.outdir, fn), "w", encoding="utf-8", newline="\n").write(s)
        w(self.name + ".kicad_sch", ser(sch) + "\n")
        w(self.lib + ".kicad_sym", ser(["kicad_symbol_lib", ["version", "20251024"],
                                        ["generator", q("kicad_symbol_editor")],
                                        ["generator_version", q("10.0")]] + self.custom) + "\n")
        for name, node in self.footprints.items():
            w(os.path.join(self.lib + ".pretty", name + ".kicad_mod"), ser(node) + "\n")
        w("sym-lib-table", '(sym_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") '
          '(uri "${KIPRJMOD}/%s.kicad_sym") (options "") (descr ""))\n)\n' % (self.lib, self.lib))
        w("fp-lib-table", '(fp_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") '
          '(uri "${KIPRJMOD}/%s.pretty") (options "") (descr ""))\n)\n' % (self.lib, self.lib))
        pro = os.path.join(self.outdir, self.name + ".kicad_pro")
        if not os.path.exists(pro):
            w(self.name + ".kicad_pro", '{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 3\n  }\n}\n'
              % self.name)
        return sum(1 for i in self.items if i[0] == "symbol"), len(self.labels)


def copy_footprint(src_mod_path, project, name=None):
    """Copy an existing .kicad_mod into the project library (parsed, renamed)."""
    node = parse(open(src_mod_path, encoding="utf-8").read())[0]
    name = name or unq(node[1])
    node[1] = q(name)
    project.footprints[name] = node
