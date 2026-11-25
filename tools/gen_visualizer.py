#!/usr/bin/env python3
"""config/lalapadgen2.keymap を読んで、レイヤーごとの割当を Gen2 の物理配置で表示する HTML を作る。

使い方:
    python3 tools/gen_visualizer.py                 # visualizer/lalapadgen2_visualizer.html を作る
    python3 tools/gen_visualizer.py --out 別の場所.html

キーマップを直したら毎回これを実行する。HTML にはキーマップの SHA-256 と git のコミットを埋め込むので、
どの版のキーマップから作ったかを画面で確かめられる。
"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYMAP = ROOT / "config" / "lalapadgen2.keymap"
LAYOUT = ROOT / "config" / "boards" / "shields" / "lalapadgen2" / "lalapadgen2-layouts.dtsi"
SHIELD = ROOT / "config" / "boards" / "shields" / "lalapadgen2" / "lalapadgen2.dtsi"
DEFAULT_OUT = ROOT / "visualizer" / "lalapadgen2_visualizer.html"


def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


def parse_defines(s):
    d = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(.+)$", s, flags=re.M):
        d[m.group(1)] = m.group(2).strip()
    return d


def expand(tokens, defines):
    out = []
    for t in tokens:
        if t in defines:
            out.extend(expand(defines[t].split(), defines))
        else:
            out.append(t)
    return out


def parse_bindings(body):
    parts = [p.strip() for p in body.split("&") if p.strip()]
    return ["&" + " ".join(p.split()) for p in parts]


def parse_keymap(text):
    defines = parse_defines(text)
    s = strip_comments(text)
    km = re.search(r"keymap\s*\{\s*compatible\s*=\s*\"zmk,keymap\";(.*?)\n    \};", s, flags=re.S)
    layers = []
    for m in re.finditer(r"(\w+)\s*\{\s*display-name\s*=\s*\"([^\"]*)\";\s*bindings\s*=\s*<(.*?)>;", km.group(1), flags=re.S):
        layers.append({"node": m.group(1), "name": m.group(2), "bindings": parse_bindings(m.group(3))})

    combos = []
    cm = re.search(r"combos\s*\{(.*?)\n    \};", s, flags=re.S)
    if cm:
        for m in re.finditer(r"(\w+)\s*\{(.*?)\};", cm.group(1), flags=re.S):
            body = m.group(2)
            b = re.search(r"bindings\s*=\s*<(.*?)>;", body, flags=re.S)
            kp = re.search(r"key-positions\s*=\s*<(.*?)>;", body, flags=re.S)
            if not (b and kp):
                continue
            ly = re.search(r"layers\s*=\s*<(.*?)>;", body, flags=re.S)
            to = re.search(r"timeout-ms\s*=\s*<(\d+)>;", body)
            combos.append({
                "name": m.group(1),
                "binding": parse_bindings(b.group(1))[0],
                "positions": [int(x) for x in expand(kp.group(1).split(), defines)],
                "layers": [int(x) for x in expand(ly.group(1).split(), defines)] if ly else None,
                "timeout": int(to.group(1)) if to else None,
            })

    conds = []
    cl = re.search(r"conditional_layers\s*\{(.*?)\n    \};", s, flags=re.S)
    if cl:
        for m in re.finditer(r"if-layers\s*=\s*<(.*?)>;\s*then-layer\s*=\s*<(.*?)>;", cl.group(1), flags=re.S):
            conds.append({
                "if": [int(x) for x in expand(m.group(1).split(), defines)],
                "then": int(expand(m.group(2).split(), defines)[0]),
            })

    behaviors = {}
    for m in re.finditer(r"(\w+):\s*\w+\s*\{\s*compatible\s*=\s*\"zmk,behavior-hold-tap\";(.*?)\};", s, flags=re.S):
        body = m.group(2)
        tt = re.search(r"tapping-term-ms\s*=\s*<(\d+)>", body)
        fl = re.search(r"flavor\s*=\s*\"([\w-]+)\"", body)
        behaviors[m.group(1)] = {"tapping_term": tt and int(tt.group(1)), "flavor": fl and fl.group(1)}
    return layers, combos, conds, behaviors


def parse_physical():
    s = strip_comments(LAYOUT.read_text(encoding="utf-8"))
    keys = []
    for m in re.finditer(r"&key_physical_attrs\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", s):
        w, h, x, y = map(int, m.groups())
        keys.append({"w": w, "h": h, "x": x, "y": y})
    return keys


def parse_trackpad_positions():
    s = SHIELD.read_text(encoding="utf-8")
    pos = {}
    for m in re.finditer(r"#define\s+POS_TP_(\w+)_(L|R)\s+(\d+)", s):
        pos[int(m.group(3))] = {"gesture": m.group(1), "side": m.group(2)}
    return pos


def git_info():
    try:
        commit = subprocess.check_output(["git", "-C", str(ROOT), "log", "-1", "--format=%h", "--", "config/lalapadgen2.keymap"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--", "config/lalapadgen2.keymap"], text=True).strip()
        branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        return {"commit": commit, "branch": branch, "dirty": bool(dirty)}
    except Exception:
        return {"commit": "?", "branch": "?", "dirty": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    text = KEYMAP.read_text(encoding="utf-8")
    layers, combos, conds, behaviors = parse_keymap(text)
    phys = parse_physical()
    for L in layers:
        if len(L["bindings"]) != len(phys):
            raise SystemExit(f"{L['node']}: バインディング数 {len(L['bindings'])} ≠ 物理キー数 {len(phys)}")

    data = {
        "layers": layers,
        "combos": combos,
        "conditional": conds,
        "behaviors": behaviors,
        "physical": phys,
        "trackpad": parse_trackpad_positions(),
        "meta": {
            "keymap_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            **git_info(),
        },
    }
    html = TEMPLATE.replace("/*@@DATA@@*/null", json.dumps(data, ensure_ascii=False))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(layers)} layers, keymap {data['meta']['keymap_sha256']})")


TEMPLATE = (Path(__file__).resolve().parent / "visualizer_template.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    main()
