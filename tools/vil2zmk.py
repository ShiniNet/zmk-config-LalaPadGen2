#!/usr/bin/env python3
"""Cornix の大西配列.vil（Vial, 10レイヤー）から LaLapad Gen2 用の ZMK キーマップを起こす。

一度きりの変換用。変換後は config/lalapadgen2.keymap が正本で、手で直してよい。
（このスクリプトを再実行すると keymap は上書きされる）

使い方:
    python3 tools/vil2zmk.py docs/ohnishi_cornix.vil config/lalapadgen2.keymap

位置の対応（Cornix の Vial 行列 → Gen2 のキー位置番号）
    左手  行 r=0..2, 列 c=1..5          → pos r*10 + (c-1)           （列0=外側の列は Gen2 にない）
    右手  行 r=4..6, 列 c=5..1（鏡像）    → pos (r-4)*10 + 5 + (5-c)
    親指  左 行3 列0..5                  → pos 30..35
          右 行7 列5..0                  → pos 36..41
    外側の列（ESC/TAB/戻る/DEL など）    → 小指の縦コンボ（combos）
    列6（エンコーダー押下）と回転         → 5方向スイッチ（左=エンコーダー0、右=エンコーダー1）
    トラックパッドの仮想キー（52..67）    → Gen2 標準ファームウェアのまま
"""
import json
import sys

# ---- QMK/Vial キーコード → ZMK バインディング -------------------------------------------
SIMPLE = {
    "KC_ESCAPE": "ESC", "KC_TAB": "TAB", "KC_DELETE": "DEL", "KC_ENTER": "ENTER",
    "KC_SPACE": "SPACE", "KC_BSPACE": "BSPC",
    "KC_COMMA": "COMMA", "KC_DOT": "DOT", "KC_MINUS": "MINUS", "KC_SLASH": "SLASH",
    "KC_SCOLON": "SEMI", "KC_QUOTE": "SQT", "KC_LBRACKET": "LBKT", "KC_RBRACKET": "RBKT",
    "KC_NONUS_HASH": "NON_US_HASH",
    "KC_LCTRL": "LCTRL", "KC_LALT": "LALT", "KC_LGUI": "LGUI",
    "KC_RCTRL": "RCTRL", "KC_RALT": "RALT", "KC_RGUI": "RGUI", "KC_RSHIFT": "RSHIFT",
    "KC_LANG1": "LANG1", "KC_LANG2": "LANG2",
    "KC_HOME": "HOME", "KC_END": "END", "KC_PGUP": "PG_UP", "KC_PGDOWN": "PG_DN",
    "KC_UP": "UP", "KC_DOWN": "DOWN", "KC_LEFT": "LEFT", "KC_RIGHT": "RIGHT",
    "KC_UNDO": "K_UNDO", "KC_CUT": "K_CUT", "KC_COPY": "K_COPY", "KC_PSTE": "K_PASTE",
    "KC_AGIN": "K_AGAIN", "KC_APPLICATION": "K_APP",
    "KC_KP_MINUS": "KP_MINUS", "KC_KP_PLUS": "KP_PLUS", "KC_KP_SLASH": "KP_DIVIDE",
    "KC_KP_ASTERISK": "KP_MULTIPLY", "KC_KP_DOT": "KP_DOT",
    "KC_WBAK": "C_AC_BACK", "KC_MUTE": "C_MUTE",
    "KC_VOLU": "C_VOL_UP", "KC_VOLD": "C_VOL_DN",
    "KC_BRIU": "C_BRI_UP", "KC_BRID": "C_BRI_DN",
    # KC_SLEP は HID Generic Desktop の System Sleep。ZMK は Consumer ページの Sleep で送る。
    "KC_SLEP": "C_SLEEP",
}
for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    SIMPLE[f"KC_{ch}"] = ch
for d in range(10):
    SIMPLE[f"KC_{d}"] = f"N{d}"
    SIMPLE[f"KC_KP_{d}"] = f"KP_N{d}"
for f in range(1, 25):
    SIMPLE[f"KC_F{f}"] = f"F{f}"

MOUSE = {
    "KC_BTN1": "&mkp LCLK", "KC_BTN2": "&mkp RCLK", "KC_BTN3": "&mkp MCLK",
    "KC_MS_U": "&mmv MOVE_UP", "KC_MS_D": "&mmv MOVE_DOWN",
    "KC_MS_L": "&mmv MOVE_LEFT", "KC_MS_R": "&mmv MOVE_RIGHT",
    "KC_WH_U": "&msc SCRL_UP", "KC_WH_D": "&msc SCRL_DOWN",
    "KC_WH_L": "&msc SCRL_LEFT", "KC_WH_R": "&msc SCRL_RIGHT",
}

# ZMK に同等の機能がないもの（&none に置き、対応表に書く）
UNSUPPORTED = {"KC_ACL0"}

MODS = {"LSFT": "LSHIFT", "RSFT": "RSHIFT", "LCTL": "LCTRL", "LALT": "LALT", "LGUI": "LGUI"}

# 左手側に置く mod-tap は ht_l、右手側は ht_r（Chordal Hold 相当の位置指定のため）
LEFT_POS = set(list(range(0, 5)) + list(range(10, 15)) + list(range(20, 25)) + list(range(30, 36)))


def conv(code, pos=None):
    if code in ("KC_NO", -1):
        return "&none"
    if code in ("KC_TRNS", "KC_TRANSPARENT"):
        return "&trans"
    if code in SIMPLE:
        return f"&kp {SIMPLE[code]}"
    if code in MOUSE:
        return MOUSE[code]
    if code in UNSUPPORTED:
        return "&none"
    if code.startswith("LT") and "(" in code:  # LT3(KC_LANG2)
        layer = int(code[2:code.index("(")])
        inner = code[code.index("(") + 1:-1]
        return f"&lt {layer} {SIMPLE[inner]}"
    if "_T(" in code:  # LSFT_T(KC_SPACE)
        mod = MODS[code[:code.index("_T(")]]
        inner = code[code.index("(") + 1:-1]
        if inner == "KC_NO":
            return f"&kp {mod}"  # タップ時は何も出さない＝押している間だけ Shift
        side = "ht_l" if pos in LEFT_POS else "ht_r"
        return f"&{side} {mod} {SIMPLE[inner]}"
    if code.startswith("LSFT(") and code.endswith(")"):
        return f"&kp LS({SIMPLE[code[5:-1]]})"
    raise SystemExit(f"未対応のキーコード: {code}")


def gen2_layer(vil_layer, enc, idx):
    """vil の 1 レイヤーを Gen2 の位置 0..51 に並べる（52..67 は別に足す）。"""
    b = ["&none"] * 52
    for r in range(3):
        for c in range(1, 6):
            p = r * 10 + (c - 1)
            b[p] = conv(vil_layer[r][c], p)
        for c in range(1, 6):
            p = r * 10 + 5 + (5 - c)
            b[p] = conv(vil_layer[4 + r][c], p)
    for c in range(6):
        b[30 + c] = conv(vil_layer[3][c], 30 + c)
        b[36 + (5 - c)] = conv(vil_layer[7][c], 36 + (5 - c))
    # 5方向スイッチ: 左 42=押下 43=右 44=下 45=左 46=上 / 右 47=上 48=左 49=下 50=右 51=押下
    (l_ccw, l_cw), (r_ccw, r_cw) = enc[idx]
    b[46] = conv(l_cw)
    b[44] = conv(l_ccw)
    b[42] = conv(vil_layer[2][6])   # 左の列6（エンコーダー押下）
    b[47] = conv(r_cw)
    b[49] = conv(r_ccw)
    b[51] = conv(vil_layer[5][6])   # 右の列6（エンコーダー押下）
    # 回転に当たらない左右方向は空き
    for p in (43, 45, 48, 50):
        b[p] = "&none"
    return b


# Gen2 標準ファームウェア（ShiniNet/zmk-config-LalaPadGen2 ea4909a）のトラックパッド仮想キー
# 52..57 = タップ（左 1/2/3 本指, 右 1/2/3 本指）, 58..67 = スワイプ（左 ←→↑↓ピンチ, 右 ←→↑↓ピンチ）
TP_BASE = ["&mkp LCLK", "&mkp RCLK", "&mkp MCLK", "&mkp LCLK", "&mkp RCLK", "&mkp MCLK",
           "&mkp MB4", "&mkp MB5", "&kp LG(TAB)", "&kp LG(D)", "&kp LCTRL",
           "&mkp MB4", "&mkp MB5", "&kp LG(TAB)", "&kp LG(D)", "&kp LCTRL"]
TP_L1 = ["&trans"] * 6 + ["&kp LC(LG(LEFT))", "&kp LC(LG(RIGHT))", "&trans", "&trans", "&trans",
                          "&kp LC(LG(LEFT))", "&kp LC(LG(RIGHT))", "&trans", "&trans", "&trans"]
TP_TRANS = ["&trans"] * 16

# Gen2 標準の System レイヤー（位置 0..51）。ここでは layer 10 に置き、Num+Nav 同時押しで出す。
SYSTEM = (
    ["&kp F1", "&kp F2", "&kp F3", "&kp F4", "&kp F5",
     "&out OUT_TOG", "&bt BT_SEL 0", "&bt BT_SEL 1", "&bt BT_SEL 2", "&bt BT_SEL 3"]
    + ["&kp F6", "&kp F7", "&kp F8", "&kp F9", "&kp F10",
       "&sys_reset", "&bootloader", "&bt BT_CLR", "&bt BT_CLR_ALL", "&trans"]
    + ["&kp F11", "&kp F12", "&kp F13", "&kp F14", "&kp F15",
       "&zip_dyn_scale ZDS_XY ZDS_INC", "&zip_dyn_scale ZDS_XY ZDS_DEC",
       "&zip_dyn_scale ZDS_SC ZDS_INC", "&zip_dyn_scale ZDS_SC ZDS_DEC",
       "&zip_dyn_scale ZDS_ALL ZDS_RST"]
    + ["&trans"] * 22
)

LAYER_NAMES = [
    ("BASE", "Base"), ("NUM", "Num"), ("NAV", "Nav"), ("FUNC", "Fn"), ("MOUSE", "Mouse"),
    ("L5", "L5"), ("L6", "L6"), ("L7", "L7"), ("L8", "L8"), ("L9", "L9"), ("SYSTEM", "System"),
]

ROWS = [list(range(0, 10)), list(range(10, 20)), list(range(20, 30)), list(range(30, 42)),
        list(range(42, 52)), list(range(52, 58)), list(range(58, 68))]


def fmt_rows(b):
    width = max(len(x) for x in b) + 2
    out = []
    for i, row in enumerate(ROWS):
        cells = [b[p].ljust(width) for p in row]
        if i in (0, 1, 2, 6):
            cells = cells[:5] + [" " * (width * 2 - 2)] + cells[5:]
        elif i == 4:
            cells = [" " * width] + cells
        elif i == 5:
            cells = cells[:3] + [" " * (width * 8 - 6)] + cells[3:]
        out.append("".join(cells).rstrip())
    return "\n".join(out)


def main(vil_path, out_path):
    vil = json.load(open(vil_path, encoding="utf-8"))
    layers = vil["layout"]
    enc = vil["encoder_layout"]
    used_td = [t for t in vil.get("tap_dance", []) if any(x != "KC_NO" for x in t[:4])]
    used_combo = [c for c in vil.get("combo", []) if any(x != "KC_NO" for x in c)]
    if used_td or used_combo or any(m for m in vil.get("macro", [])):
        raise SystemExit("tap_dance / combo / macro に使用中のものがある。変換規則を足すこと")

    all_layers = []
    for i, vl in enumerate(layers):
        b = gen2_layer(vl, enc, i)
        tp = TP_BASE if i == 0 else TP_L1 if i == 1 else TP_TRANS
        all_layers.append(b + tp)
    all_layers.append(SYSTEM + TP_TRANS)

    blocks = []
    for (node, disp), b in zip(LAYER_NAMES, all_layers):
        assert len(b) == 68, (node, len(b))
        blocks.append(
            f"        {node.lower()}_layer {{\n"
            f"            display-name = \"{disp}\";\n"
            f"            bindings = <\n{fmt_rows(b)}\n            >;\n"
            f"        }};"
        )

    text = TEMPLATE.replace("@@LAYERS@@", "\n\n".join(blocks))
    open(out_path, "w", encoding="utf-8").write(text)
    print(f"wrote {out_path}: {len(all_layers)} layers")


TEMPLATE = r"""/*
 * LaLapad Gen2 キーマップ — Cornix 大西配列.vil（10レイヤー）から起こしたもの（REQ-189）
 *
 * 正本はこのファイル。tools/vil2zmk.py は最初の変換に使ったもの（再実行すると上書きされる）。
 * 直したら `python3 tools/gen_visualizer.py` でビジュアライザーを作り直す。
 *
 * レイヤー: 0 Base(大西) / 1 Num / 2 Nav / 3 Fn / 4 Mouse / 5-9 空き（.vilどおり）/ 10 System
 *   - 1 と 2 を同時に押すと 10 System（Gen2 標準の Num+Nav→System と同じ仕組み）
 *   - トラックパッドの低速モードは shield 側で layer 1・2 に掛かる（Gen2 標準のまま）
 */

#define ZMK_POINTING_DEFAULT_SCRL_VAL 120   /* smooth scrolling 有効時の推奨値 */

#include <input/processors.dtsi>
#include <dt-bindings/zmk/zip_dynamic_scale.h>
#include <behaviors.dtsi>
#include <dt-bindings/zmk/bt.h>
#include <dt-bindings/zmk/keys.h>
#include <dt-bindings/zmk/outputs.h>
#include <dt-bindings/zmk/pointing.h>

#define BASE   0
#define NUM    1
#define NAV    2
#define FUNC   3
#define MOUSE  4
#define SYSTEM 10

/* 片手側のキー位置（Chordal Hold 相当の判定に使う） */
#define KEYS_L 0 1 2 3 4 10 11 12 13 14 20 21 22 23 24
#define KEYS_R 5 6 7 8 9 15 16 17 18 19 25 26 27 28 29
#define THUMBS 30 31 32 33 34 35 36 37 38 39 40 41

/* .vil の設定: Tapping Term 250 / Permissive Hold オン / Hold On Other Key Press オフ /
 *              Chordal Hold オン / Flow Tap 120 / Quick Tap Term は未設定（= Tapping Term） */
&lt {
    flavor = "balanced";
    tapping-term-ms = <250>;
    quick-tap-ms = <250>;
    require-prior-idle-ms = <120>;
};

/ {
    behaviors {
        zip_dyn_scale: zip_dyn_scale {
            compatible = "zmk,behavior-zip-dynamic-scale";
            #binding-cells = <2>;
        };

        zip_dyn_scale_set: zip_dyn_scale_set {
            compatible = "zmk,behavior-zip-dynamic-scale-set";
            #binding-cells = <2>;
        };

        /* 左手側の mod-tap: 反対の手か親指と同時押しのときだけホールドにする */
        ht_l: hold_tap_left {
            compatible = "zmk,behavior-hold-tap";
            #binding-cells = <2>;
            flavor = "balanced";
            tapping-term-ms = <250>;
            quick-tap-ms = <250>;
            require-prior-idle-ms = <120>;
            hold-trigger-key-positions = <KEYS_R THUMBS>;
            hold-trigger-on-release;
            bindings = <&kp>, <&kp>;
        };

        /* 右手側の mod-tap */
        ht_r: hold_tap_right {
            compatible = "zmk,behavior-hold-tap";
            #binding-cells = <2>;
            flavor = "balanced";
            tapping-term-ms = <250>;
            quick-tap-ms = <250>;
            require-prior-idle-ms = <120>;
            hold-trigger-key-positions = <KEYS_L THUMBS>;
            hold-trigger-on-release;
            bindings = <&kp>, <&kp>;
        };
    };

    /* Cornix の外側の列（Gen2 にない列）は、小指の縦2キー同時押しに置く。
     * 上段+中段 = 外側の列の上段、中段+下段 = 外側の列の中段（.vil の位置どおり）。 */
    combos {
        compatible = "zmk,combos";

        combo_esc {
            bindings = <&kp ESC>;
            key-positions = <0 10>;
            timeout-ms = <50>;
            layers = <BASE NUM NAV MOUSE>;
        };

        combo_tab {
            bindings = <&kp TAB>;
            key-positions = <10 20>;
            timeout-ms = <50>;
            layers = <BASE NUM NAV MOUSE>;
        };

        combo_back {
            bindings = <&kp C_AC_BACK>;
            key-positions = <9 19>;
            timeout-ms = <50>;
            layers = <BASE NUM NAV FUNC>;
        };

        combo_rshift_mouse {
            bindings = <&kp RSHIFT>;
            key-positions = <9 19>;
            timeout-ms = <50>;
            layers = <MOUSE>;
        };

        combo_del {
            bindings = <&kp DEL>;
            key-positions = <19 29>;
            timeout-ms = <50>;
            layers = <BASE NUM NAV FUNC MOUSE>;
        };
    };

    keymap {
        compatible = "zmk,keymap";

@@LAYERS@@
    };

    conditional_layers {
        compatible = "zmk,conditional-layers";

        num_nav_to_system {
            if-layers = <NUM NAV>;
            then-layer = <SYSTEM>;
        };
    };
};
"""

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
