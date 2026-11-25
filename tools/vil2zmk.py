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
    外側の列 上段・中段（ESC/TAB/戻る/DEL）→ 親指列の右下段・右親指の Shift のタップ（REQ-193。apply_req193）
    列6（エンコーダー押下）と回転         → 5方向スイッチの押し込みと上下（左=エンコーダー0、右=エンコーダー1）
    トラックパッドの仮想キー（52..67）    → macOS のトラックパッドの作法に合わせた割当（REQ-192）

.vil に定義のない同時押し（コンボ）は作らない（REQ-192）。
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
    if code in UNSUPPORTED or str(code).startswith("USER"):
        return "&none"   # USER00〜02 は Cornix 固有のキー（中身不明）
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
    # Cornix の外側の列（Gen2 にない列）は 5方向スイッチの左右に置く（REQ-192）。
    # レイヤー 0〜4 では apply_req193 が左右を ←→・⌘C/⌘V に上書きする（REQ-193）。
    #   左手: 外側の列の上段 → 左スイッチの「左」(45)、中段 → 左スイッチの「右」(43)
    #   右手: 外側の列の上段 → 右スイッチの「右」(50)、中段 → 右スイッチの「左」(48)
    #   （どちらの手も、外側へ倒すと上段、内側へ倒すと中段。下段は .vil で全レイヤー KC_NO）
    b[45] = conv(vil_layer[0][0])
    b[43] = conv(vil_layer[1][0])
    b[50] = conv(vil_layer[4][0])
    b[48] = conv(vil_layer[5][0])
    return b


# トラックパッドの仮想キー（Gen2 の shield 定義 POS_TP_*）。macOS のトラックパッドの作法に合わせる（REQ-192）。
#   52..54 / 55..57 = 左/右パッドの 1本指タップ(MB1)・2本指タップ(MB2)・3本指タップ(MB3)
#   58..62 / 63..67 = 左/右パッドの 3本指スワイプ 右(MB4)・左(MB5)・上(MB6)・下(MB7)、ピンチ中の修飾キー(ZMOD)
#   スワイプの向きは zmk-driver-iqs9151 v1.0.0 の実装（dx>0→BTN_3=MB4、dx<0→BTN_4=MB5、
#   dy<0→BTN_5=MB6、dy>0→BTN_6=MB7）と LaLaPad Gen2 の HowtoUse の既定割当表による。
#   Gen2 標準（Windows 向け）: MB3=中クリック、MB4/5=戻る/進む、MB6=Win+Tab、MB7=Win+D、ZMOD=Ctrl
TP_MAC_ONE_PAD = [
    "&mkp LCLK",          # 1本指タップ = クリック（Mac の「タップでクリック」）
    "&mkp RCLK",          # 2本指タップ = 副ボタンのクリック
    "&kp LC(LG(D))",      # 3本指タップ = 調べる＆データ検出（Mac の「3本指でタップ」設定と同じ ⌃⌘D）
]
TP_MAC_SWIPE = [
    "&kp LC(LEFT)",       # 3本指スワイプ右 = 左の操作スペースへ（Mac: 3本指で右へスワイプ）
    "&kp LC(RIGHT)",      # 3本指スワイプ左 = 右の操作スペースへ
    "&kp LC(UP)",         # 3本指スワイプ上 = Mission Control
    "&kp LC(DOWN)",       # 3本指スワイプ下 = アプリケーションウインドウ（App Exposé）
    "&kp LGUI",           # ピンチ中の修飾キー = ⌘（Gen2 作者が Mac 向けに挙げている設定）
]
TP_BASE = TP_MAC_ONE_PAD * 2 + TP_MAC_SWIPE * 2
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


def apply_req193(layers):
    """稜太の追加修正（REQ-193、2026-11-26）を、.vil から起こしたレイヤーに上書きする。"""
    for i in range(5):                       # 実際に使うレイヤー 0〜4（5〜9 は空き）
        b = layers[i]
        # 1. 左手の修飾キー: Ctrl と ⌘ を入れ替える（左下段 30 と 32）
        if b[30] == "&kp LCTRL" and b[32] == "&kp LGUI":
            b[30], b[32] = "&kp LGUI", "&kp LCTRL"
        # 2. 右手の修飾キーは置かない。右Ctrl の跡（41）に Esc、
        #    右⌘・右Opt の跡（39・40）に、5方向スイッチから外れた Delete と 戻る を仮置き
        if b[41] == "&kp RCTRL":
            b[41] = "&kp ESC"
        if b[39] == "&kp RGUI":
            b[39] = "&kp DEL"
        if b[40] == "&kp RALT":
            b[40] = "&kp C_AC_BACK"
        # 4. 5方向スイッチの左右: 左手＝← →、右手＝左がコピー（⌘C）・右がペースト（⌘V）
        #    押し込み・上下（Sleep・ミュート・輝度・音量）は REQ-192 のまま
        b[45], b[43] = "&kp LEFT", "&kp RIGHT"
        b[48], b[50] = "&kp LG(C)", "&kp LG(V)"
    # 3. 右親指の Shift（位置 37。.vil では RSFT_T(KC_NO)）: タップ＝Tab、長押し＝Shift
    #    Num〜Mouse レイヤーの 37 は .vil どおり（タップ＝Space または App）
    if layers[0][37] == "&kp RSHIFT":
        layers[0][37] = "&ht_r RSHIFT TAB"
    # 5. Num レイヤーのテンキーを右へ1列ずらす（0 を 1 の左、: を 4 の左に置く）
    #    右上の + は残り、* は外す（JIS では ⇧＋: で * が出る）。−・/・. は元の位置
    num = layers[1]
    for p, code in {5: "KP_PLUS", 6: "KP_N7", 7: "KP_N8", 8: "KP_N9",
                    15: "SQT", 16: "KP_N4", 17: "KP_N5", 18: "KP_N6",
                    25: "KP_N0", 26: "KP_N1", 27: "KP_N2", 28: "KP_N3"}.items():
        num[p] = "&kp " + code
    return layers


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
        tp = TP_BASE if i == 0 else TP_TRANS
        all_layers.append(b + tp)
    apply_req193(all_layers)
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
 * LaLapad Gen2 キーマップ — Cornix 大西配列.vil（10レイヤー）から起こしたもの（REQ-189、REQ-192・REQ-193 で修正）
 *
 * 正本はこのファイル。tools/vil2zmk.py は最初の変換に使ったもの（再実行すると上書きされる）。
 * 直したら `python3 tools/gen_visualizer.py` でビジュアライザーを作り直す。
 *
 * レイヤー: 0 Base(大西) / 1 Num / 2 Nav / 3 Fn / 4 Mouse / 5-9 空き（.vilどおり）/ 10 System
 *   - 1 と 2 を同時に押すと 10 System（Gen2 標準の Num+Nav→System と同じ仕組み）
 *   - トラックパッドの低速モードは shield 側で layer 1・2 に掛かる（Gen2 標準のまま）
 *   - 左下段は ⌘・Opt・Ctrl。右下段に修飾キーは置かず、Delete・戻る・Esc（REQ-193）
 *   - 右親指の Shift はタップで Tab（REQ-193）
 *   - 5方向スイッチの左右: 左手＝←→、右手＝⌘C・⌘V（REQ-193）
 *   - トラックパッドのジェスチャーは macOS の作法（⌃←/⌃→・Mission Control など）
 *   - .vil に定義のない同時押し（コンボ）は置かない
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
