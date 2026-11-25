#!/usr/bin/env python3
"""config/lalapadgen2.keymap を読んで、レイヤーごとの割当を Gen2 の物理配置で表示する HTML を作る。

使い方:
    python3 tools/gen_visualizer.py                 # docs/lalapadgen2_visualizer.html を作る
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
DEFAULT_OUT = ROOT / "docs" / "lalapadgen2_visualizer.html"


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
        bd = re.search(r"bindings\s*=\s*<&(\w+)>\s*,\s*<&(\w+)>", body)
        behaviors[m.group(1)] = {"tapping_term": tt and int(tt.group(1)), "flavor": fl and fl.group(1),
                                 "hold": bd and bd.group(1), "tap": bd and bd.group(2)}

    # マクロ（&macro_press 修飾キー → &macro_tap キー → &macro_release）。表示用に「⌃⇧⌘＋キー」の形にする
    macros = {}
    sym = {"LCTRL": "⌃", "LSHIFT": "⇧", "LALT": "⌥", "LGUI": "⌘", "RCTRL": "⌃", "RSHIFT": "⇧", "RALT": "⌥", "RGUI": "⌘"}
    for m in re.finditer(r"(\w+):\s*\w+\s*\{\s*compatible\s*=\s*\"zmk,behavior-macro\";(.*?)\};", s, flags=re.S):
        body = re.search(r"bindings\s*=(.*?);", m.group(2), flags=re.S).group(1)
        held, taps, steps = [], [], []
        for kind, codes in re.findall(r"<&macro_(press|tap|release)((?:\s+&kp\s+\w+)+)>", body):
            ks = re.findall(r"&kp\s+(\w+)", codes)
            steps.append(kind + " " + "+".join(ks))
            (held if kind == "press" else taps if kind == "tap" else []).extend(ks)
        label = "".join(sym.get(k, k) for k in held) + "＋".join(t.replace("KP_N", "テンキー") for t in taps)
        macros[m.group(1)] = {"label": label, "detail": label + "（" + " → ".join(steps) + "）"}
    # 接続先 OS で割当を切り替える behavior（REQ-195）: bindings = <Mac 用>, <Windows 用>
    os_morphs = {}
    for m in re.finditer(r"(\w+):\s*\w+\s*\{\s*compatible\s*=\s*\"lalapad,behavior-os-morph\";(.*?)\};", s, flags=re.S):
        b = re.search(r"bindings\s*=\s*<(.*?)>\s*,\s*<(.*?)>;", m.group(2), flags=re.S)
        os_morphs[m.group(1)] = {"mac": "&" + " ".join(b.group(1).strip().lstrip("&").split()),
                                 "win": "&" + " ".join(b.group(2).strip().lstrip("&").split())}
    return layers, combos, conds, behaviors, macros, os_morphs


def expand_os(binding, os_name, behaviors, os_morphs):
    """os-morph と、タップが os-morph の hold-tap を、指定した OS の割当に展開する。"""
    p = binding.split()
    beh = p[0][1:]
    if beh in os_morphs:
        return os_morphs[beh][os_name]
    ht = behaviors.get(beh)
    if ht and ht.get("tap") in os_morphs and ht.get("hold") == "mo":
        tap = os_morphs[ht["tap"]][os_name].split()
        assert tap[0] == "&kp", tap
        return f"&lt {p[1]} {tap[1]}"
    return binding


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


# ---- 表示用の形状（REQ-192）---------------------------------------------------------------
# ZMK の物理配置（lalapadgen2-layouts.dtsi）は格子状なので、表示にはこちらを使う。
# LaLaPad Gen2 は列ごとに縦にずれたカラムスタッガード。値は ShiniNet/LaLaPadGen2 の製品写真
# （docs/images/product_1：真上から撮った左右）から、キーのピッチを 1u として読み取った推定値（±0.1u 程度）。
#   中指・人差し指・内側の列はほぼ同じ高さ、薬指が約 0.3u、小指が約 0.65u 下がる。
#   親指側は、人差し指列の下に小さいキー（位置 33/38）、その内側に大きい親指キー 2 つ（34・35/37・36）。
#   5方向スイッチは中指列と人差し指列の下段の間。トラックパッドは内側の列の外（手の中央側）上部。
# 単位は 1u = 100。左手の座標を決め、右手は左右反転で作る。
STAGGER = [65, 30, 0, 0, 0]          # 列 0=小指, 1=薬指, 2=中指, 3=人差し指, 4=内側
HALF_W = 800                          # 片手の幅
GAP = 120                             # 左右の間
FIVE_DISPLAY_DY = 155                 # 5方向スイッチの拡大図を実機の位置からどれだけ下に描くか
FIVE_STEP = 58                        # 拡大図の上下左右ボタンの中心間隔
FIVE_SIZE = 54


def _left_geometry():
    g = {}
    for r in range(3):
        for c in range(5):
            g[r * 10 + c] = {"x": c * 100, "y": r * 100 + STAGGER[c], "w": 100, "h": 100, "rot": 0}
    g[30] = {"x": 0, "y": 300 + STAGGER[0], "w": 100, "h": 100, "rot": 0}
    g[31] = {"x": 100, "y": 300 + STAGGER[1], "w": 100, "h": 100, "rot": 0}
    g[32] = {"x": 200, "y": 300 + STAGGER[2], "w": 100, "h": 100, "rot": 0}
    g[33] = {"x": 360, "y": 315, "w": 100, "h": 100, "rot": 0}          # 人差し指列の下段（内側・やや下）
    g[34] = {"x": 500, "y": 270, "w": 100, "h": 150, "rot": 12}         # 大きい親指キー（外側）
    g[35] = {"x": 620, "y": 300, "w": 100, "h": 150, "rot": 24}         # 大きい親指キー（内側）
    return g


def _mirror(k):
    return {"x": 2 * HALF_W + GAP - k["x"] - k["w"], "y": k["y"], "w": k["w"], "h": k["h"], "rot": -k["rot"]}


def build_geometry():
    left = _left_geometry()
    keys = {}
    for p, k in left.items():
        keys[p] = k
        if p < 30:
            r, c = divmod(p, 10)
            keys[r * 10 + 5 + (4 - c)] = _mirror(k)
        else:
            keys[71 - p] = _mirror(k)                     # 30↔41, 31↔40, … 35↔36
    knob_l = {"cx": 322, "cy": 360}                       # 実機の 5方向スイッチの位置
    knob_r = {"cx": 2 * HALF_W + GAP - knob_l["cx"], "cy": knob_l["cy"]}
    # 拡大図: 左 42=押下 43=右 44=下 45=左 46=上 / 右 51=押下 50=右 49=下 48=左 47=上
    for knob, (center, right, down, left_, up) in ((knob_l, (42, 43, 44, 45, 46)), (knob_r, (51, 50, 49, 48, 47))):
        cx, cy = knob["cx"], knob["cy"] + FIVE_DISPLAY_DY
        for p, (dx, dy) in ((center, (0, 0)), (right, (1, 0)), (down, (0, 1)), (left_, (-1, 0)), (up, (0, -1))):
            keys[p] = {"x": cx + dx * FIVE_STEP - FIVE_SIZE / 2, "y": cy + dy * FIVE_STEP - FIVE_SIZE / 2,
                       "w": FIVE_SIZE, "h": FIVE_SIZE, "rot": 0}
    pad_l = {"x": 515, "y": -10, "w": 280, "h": 260}
    pad_r = {"x": 2 * HALF_W + GAP - pad_l["x"] - pad_l["w"], "y": pad_l["y"], "w": pad_l["w"], "h": pad_l["h"]}
    return {
        "keys": [keys[p] for p in range(52)],
        "pads": [dict(pad_l, side="L"), dict(pad_r, side="R")],
        "knobs": [knob_l, knob_r],
        "width": 2 * HALF_W + GAP,
        "height": knob_l["cy"] + FIVE_DISPLAY_DY + FIVE_STEP + FIVE_SIZE / 2 + 30,
    }


def win_profiles():
    """Windows として扱う Bluetooth プロファイル（1 始まり）。Kconfig の既定値か、shield の .conf の設定値。"""
    mask = None
    for f in (ROOT / "config" / "boards" / "shields" / "lalapadgen2").glob("*.conf"):
        m = re.search(r"CONFIG_ZMK_BEHAVIOR_OS_MORPH_WIN_PROFILES\s*=\s*(\w+)", f.read_text(encoding="utf-8"))
        if m:
            mask = int(m.group(1), 0)
    if mask is None:
        m = re.search(r"WIN_PROFILES.*?default\s+(0x[0-9a-fA-F]+|\d+)", (ROOT / "Kconfig").read_text(encoding="utf-8"), flags=re.S)
        mask = int(m.group(1), 0)
    return [i + 1 for i in range(32) if mask >> i & 1]


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
    layers, combos, conds, behaviors, macros, os_morphs = parse_keymap(text)
    raw = [dict(L, bindings=list(L["bindings"])) for L in layers]
    layers_win = [dict(L, bindings=[expand_os(b, "win", behaviors, os_morphs) for b in L["bindings"]]) for L in raw]
    for L in layers:
        L["bindings"] = [expand_os(b, "mac", behaviors, os_morphs) for b in L["bindings"]]
    phys = parse_physical()
    for L in layers:
        if len(L["bindings"]) != len(phys):
            raise SystemExit(f"{L['node']}: バインディング数 {len(L['bindings'])} ≠ 物理キー数 {len(phys)}")

    data = {
        "layers": layers,
        "combos": combos,
        "conditional": conds,
        "behaviors": behaviors,
        "macros": macros,
        "layers_win": layers_win,
        "os_morphs": os_morphs,
        "win_profiles": win_profiles(),
        "physical": phys,
        "geometry": build_geometry(),
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
