#!/usr/bin/env python3
"""Cornix の .vil（Vial, 10レイヤー）から LaLapad Gen2 用の ZMK キーマップを起こす。

正本は Cornix の .vil（REQ-194 からは docs/cornix_20261126.vil）。キーマップを直すときは
.vil を差し替えるか、Gen2 側の決めごと（apply_gen2）を直して、このスクリプトを再実行する。
config/lalapadgen2.keymap は上書きされる。

使い方:
    python3 tools/vil2zmk.py docs/cornix_20261126.vil config/lalapadgen2.keymap

位置の対応（Cornix の Vial 行列 → Gen2 のキー位置番号）
    左手  行 r=0..2, 列 c=1..5          → pos r*10 + (c-1)           （列0=外側の列は Gen2 にない）
    右手  行 r=4..6, 列 c=5..1（鏡像）    → pos (r-4)*10 + 5 + (5-c)
    親指  左 行3 列0..5                  → pos 30..35
          右 行7 列5..0                  → pos 36..41
    外側の列（Gen2 にない列）            → 5方向スイッチの左右と下（レイヤー 0〜4 は apply_gen2 が上書き）
    列6（エンコーダー押下）と回転         → 5方向スイッチの押し込みと上下（左=エンコーダー0、右=エンコーダー1）
                                            上下はレイヤー 0〜4 で apply_gen2 が上書き（REQ-192・193 の決定を優先）
    トラックパッドの仮想キー（52..67）    → macOS のトラックパッドの作法に合わせた割当（REQ-192）
    コンボ・マクロ                         → .vil の定義をそのまま移す（REQ-194）。.vil にないコンボは作らない
    接続先 OS で変わる割当                 → OS_MORPHS の os-morph に包む（REQ-195。Mac 用は .vil どおり）

置けなかったキー（Gen2 側の決めごとで上書きしたもの）は実行時に一覧を出す。
"""
import json
import sys

# ---- QMK/Vial キーコード → ZMK バインディング -------------------------------------------
SIMPLE = {
    "KC_ESCAPE": "ESC", "KC_TAB": "TAB", "KC_DELETE": "DEL", "KC_ENTER": "ENTER",
    "KC_SPACE": "SPACE", "KC_BSPACE": "BSPC",
    "KC_COMMA": "COMMA", "KC_DOT": "DOT", "KC_MINUS": "MINUS", "KC_SLASH": "SLASH",
    "KC_SCOLON": "SEMI", "KC_QUOTE": "SQT", "KC_LBRACKET": "LBKT", "KC_RBRACKET": "RBKT",
    "KC_NONUS_HASH": "NON_US_HASH", "KC_RO": "INTERNATIONAL_1",
    "KC_LCTRL": "LCTRL", "KC_LALT": "LALT", "KC_LGUI": "LGUI", "KC_LSHIFT": "LSHIFT",
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
    if code.startswith("TO(") and code.endswith(")"):
        return f"&to {int(code[3:-1])}"
    if code.startswith("M") and code[1:].isdigit():
        return f"&m{int(code[1:])}"
    w = wrapped(code)
    if w:
        return f"&kp {w}"
    raise SystemExit(f"未対応のキーコード: {code}")


# 修飾キー付きのキーコード（LSFT(KC_1) など）→ ZMK の LS(N1) など
WRAP = {"LSFT": ["LS"], "LCTL": ["LC"], "LALT": ["LA"], "LGUI": ["LG"], "SGUI": ["LS", "LG"],
        "RSFT": ["RS"], "RCTL": ["RC"], "RALT": ["RA"], "RGUI": ["RG"]}


def wrapped(code):
    if "(" not in code or not code.endswith(")"):
        return None
    head, inner = code[:code.index("(")], code[code.index("(") + 1:-1]
    if head not in WRAP:
        return None
    inner_z = wrapped(inner) or SIMPLE.get(inner)
    if inner_z is None:
        raise SystemExit(f"未対応のキーコード: {code}")
    for m in reversed(WRAP[head]):
        inner_z = f"{m}({inner_z})"
    return inner_z


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
    # レイヤー 0〜4 では apply_gen2 が左右を ←→・⌘C/⌘V に上書きする（REQ-193）。
    #   左手: 外側の列の上段 → 左スイッチの「左」(45)、中段 → 左スイッチの「右」(43)
    #   右手: 外側の列の上段 → 右スイッチの「右」(50)、中段 → 右スイッチの「左」(48)
    #   （どちらの手も、外側へ倒すと上段、内側へ倒すと中段）
    #   下段は、そのレイヤーのエンコーダーの回転が空き（KC_NO）なら 5方向スイッチの「下」に置く（REQ-194。
    #   L5 の TO(6) のため）。回転に割当があるときは置けないので、dropped に記録する。
    b[45] = conv(vil_layer[0][0])
    b[43] = conv(vil_layer[1][0])
    b[50] = conv(vil_layer[4][0])
    b[48] = conv(vil_layer[5][0])
    for bottom, down, ccw in ((vil_layer[2][0], 44, l_ccw), (vil_layer[6][0], 49, r_ccw)):
        if bottom in ("KC_NO", -1):
            continue
        if ccw in ("KC_NO", -1) and b[down] == "&none":
            b[down] = conv(bottom)
        else:
            DROPPED.append((idx, f"外側の列の下段 {bottom}", "5方向スイッチの下が回転の割当で埋まっている"))
    return b


DROPPED = []   # (レイヤー, .vil 側のキー, 置かなかった理由)


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
       "&sys_reset", "&bootloader", "&bt BT_CLR", "&bt BT_CLR_ALL", "&bt BT_SEL 4"]
    + ["&kp F11", "&kp F12", "&kp F13", "&kp F14", "&kp F15",
       "&zip_dyn_scale ZDS_XY ZDS_INC", "&zip_dyn_scale ZDS_XY ZDS_DEC",
       "&zip_dyn_scale ZDS_SC ZDS_INC", "&zip_dyn_scale ZDS_SC ZDS_DEC",
       "&zip_dyn_scale ZDS_ALL ZDS_RST"]
    + ["&trans"] * 22
)

LAYER_NAMES = [
    ("BASE", "Base"), ("NUM", "Num"), ("NAV", "Nav"), ("FUNC", "Fn"), ("MOUSE", "Mouse"),
    ("L5", "QWERTY"), ("L6", "Kana2"), ("L7", "L7"), ("L8", "L8"), ("L9", "L9"), ("SYSTEM", "System"),
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


# Gen2 側の決めごと（REQ-192・REQ-193）。.vil を正本にしつつ、Gen2 固有の部分はこちらを優先する（REQ-194）。
GEN2_FIVE_WAY = {          # レイヤー 0〜4 の 5方向スイッチ（押し込み 42・51 は .vil のまま）
    45: "&kp LEFT", 43: "&kp RIGHT",              # 左手の左右 = ← →（REQ-193）
    48: "&kp LG(C)", 50: "&kp LG(V)",             # 右手の左右 = コピー・ペースト（REQ-193）
    46: "&kp C_BRI_UP", 44: "&kp C_BRI_DN",       # 左手の上下 = 輝度（REQ-192 で決めた割当。REQ-194 の .vil とは異なる）
    47: "&kp C_VOL_UP", 49: "&kp C_VOL_DN",       # 右手の上下 = 音量
}
# 右下段の中指・薬指（39・40）が空き（.vil で KC_NO）なら Delete と 戻る を置く（REQ-193 の仮置きを続ける）
GEN2_FILL_EMPTY = {39: "&kp DEL", 40: "&kp C_AC_BACK"}
GEN2_FILL_LAYERS = (0, 2, 3, 4)


def apply_gen2(layers):
    for i in range(5):                       # 5方向スイッチの割当を決めたレイヤー 0〜4
        b = layers[i]
        for p, binding in GEN2_FIVE_WAY.items():
            if b[p] not in ("&none", binding):
                DROPPED.append((i, f"位置 {p} の {b[p]}", f"5方向スイッチの決めごと（{binding}）を優先"))
            b[p] = binding
    for i in GEN2_FILL_LAYERS:
        for p, binding in GEN2_FILL_EMPTY.items():
            if layers[i][p] == "&none":
                layers[i][p] = binding
    return layers


def zmk_combos(vil, gen2_layers):
    """.vil のコンボを、レイヤー 0 の Gen2 位置に置き換える。"""
    timeout = int(vil.get("settings", {}).get("2", 50))     # QMK 設定 2 = Combo time out
    vl0 = vil["layout"][0]
    out = []
    for n, c in enumerate(vil.get("combo", [])):
        keys, result = [k for k in c[:4] if k != "KC_NO"], c[4]
        if not keys:
            continue
        positions = []
        for k in keys:
            # .vil のコンボはキーコードで指定する。レイヤー 0 で同じキーを探す
            # （mod-tap は置く側で ht_l / ht_r が変わるので、behavior 名ではなく引数で比べる）
            want = conv(k, None)
            beh, args = want.split()[0], want.split()[1:]
            same_beh = ("&ht_l", "&ht_r") if beh in ("&ht_l", "&ht_r") else (beh,)
            found = [q for q in range(42) if gen2_layers[0][q].split()[0] in same_beh
                     and gen2_layers[0][q].split()[1:] == args]
            if len(found) != 1:
                raise SystemExit(f"コンボ {n} のキー {k} の位置が決まらない: {found}")
            positions.append(found[0])
        out.append({"name": f"combo_{n}", "positions": positions, "binding": conv(result), "timeout": timeout,
                    "keys": keys, "result": result})
    return out


def zmk_macros(vil):
    out = []
    for n, m in enumerate(vil.get("macro", [])):
        if not m:
            continue
        steps = []
        for act in m:
            kind, codes = act[0], act[1:]
            z = " ".join(f"&kp {SIMPLE[c]}" for c in codes)
            steps.append({"down": f"<&macro_press {z}>", "tap": f"<&macro_tap {z}>",
                          "up": f"<&macro_release {z}>"}[kind])
        out.append({"name": f"m{n}", "steps": steps, "src": m})
    return out


# ---- 接続先 OS で変わる割当（REQ-195）----------------------------------------------------------
# Bluetooth プロファイル 4・5（ZMK の BT_SEL 3・4）は Windows 用、1〜3 と USB は Mac 用。
# .vil 由来の Mac の割当のうち、Windows で意味が変わるものを os-morph（src/behaviors/behavior_os_morph.c）に包む。
# 修飾キーの物理位置は変えず、送るキーコードを変える（⌘ の位置は Windows では Ctrl、Ctrl の位置は Win キー）。
#   (Mac の割当, Windows の割当, os-morph の名前, 説明)
OS_MORPHS = [
    ("&kp LGUI", "&kp LCTRL", "os_cmd", "⌘ → Ctrl（⌘ の位置で Windows のショートカット）"),
    ("&kp LCTRL", "&kp LGUI", "os_ctrl", "Ctrl → Win キー"),
    ("&kp LG(Z)", "&kp LC(Z)", "os_undo", "取り消し ⌘Z → Ctrl+Z"),
    ("&kp LG(X)", "&kp LC(X)", "os_cut", "カット ⌘X → Ctrl+X"),
    ("&kp LG(C)", "&kp LC(C)", "os_copy", "コピー ⌘C → Ctrl+C"),
    ("&kp LG(V)", "&kp LC(V)", "os_paste", "ペースト ⌘V → Ctrl+V"),
    ("&kp LS(LG(Z))", "&kp LC(Y)", "os_redo", "やり直し ⇧⌘Z → Ctrl+Y"),
    ("&kp LANG2", "&kp INTERNATIONAL_5", "os_eisu", "英数 → 無変換（Windows の IME オフ。MS-IME の設定が要る）"),
    ("&kp LANG1", "&kp INTERNATIONAL_4", "os_kana", "かな → 変換（Windows の IME オン。MS-IME の設定が要る）"),
    ("&kp LC(LEFT)", "&kp LC(LG(LEFT))", "os_desk_l", "左の操作スペース ⌃← → 左の仮想デスクトップ Win+Ctrl+←"),
    ("&kp LC(RIGHT)", "&kp LC(LG(RIGHT))", "os_desk_r", "右の操作スペース ⌃→ → 右の仮想デスクトップ Win+Ctrl+→"),
    ("&kp LC(UP)", "&kp LG(TAB)", "os_overview", "Mission Control ⌃↑ → タスクビュー Win+Tab"),
    ("&kp LC(DOWN)", "&kp LG(D)", "os_app_win", "アプリケーションウインドウ ⌃↓ → デスクトップを表示 Win+D"),
    ("&kp LC(LG(D))", "&mkp MCLK", "os_lookup", "調べる ⌃⌘D → 中クリック（Gen2 標準の Windows 向け割当）"),
    ("&m0", "&kp LG(LS(S))", "os_shot", "マクロ M0（⌃⇧⌘＋テンキー4）→ 画面の切り取り Win+Shift+S"),
]
OS_BY_MAC = {mac: (win, name, note) for mac, win, name, note in OS_MORPHS}
# レイヤータップ（&lt）のタップ側が OS で変わるものは、タップに os-morph を持つ hold-tap に置き換える
OS_LT = {"LANG2": "eisu", "LANG1": "kana"}


def apply_os(layers):
    """Mac の割当のうち Windows で変わるものを os-morph に置き換える。使った os-morph の名前を返す。"""
    used_os, used_lt = set(), set()
    for b in layers:
        for p, binding in enumerate(b):
            if binding in OS_BY_MAC:
                win, name, _ = OS_BY_MAC[binding]
                b[p] = "&" + name
                used_os.add(name)
                continue
            parts = binding.split()
            if parts[0] == "&lt" and parts[2] in OS_LT:
                key = OS_LT[parts[2]]
                b[p] = f"&lt_{key} {parts[1]} 0"
                used_os.add("os_" + key)
                used_lt.add(key)
                continue
            # Mac 専用のキーコードが包まれずに残っていたら止める（OS_MORPHS に足すこと）
            if any(t in binding for t in ("LG(", "LANG1", "LANG2", "&m0")) or binding.startswith("&ht") and "LANG" in binding:
                raise SystemExit(f"Windows での扱いが決まっていない割当: {binding}（OS_MORPHS に足すこと）")
    return used_os, used_lt


def main(vil_path, out_path):
    vil = json.load(open(vil_path, encoding="utf-8"))
    layers = vil["layout"]
    enc = vil["encoder_layout"]
    used_td = [t for t in vil.get("tap_dance", []) if any(x != "KC_NO" for x in t[:4])]
    if used_td or vil.get("key_override") or vil.get("alt_repeat_key"):
        raise SystemExit("tap_dance / key_override / alt_repeat_key に使用中のものがある。変換規則を足すこと")

    all_layers = []
    for i, vl in enumerate(layers):
        b = gen2_layer(vl, enc, i)
        tp = TP_BASE if i == 0 else TP_TRANS
        all_layers.append(b + tp)
    apply_gen2(all_layers)
    all_layers.append(SYSTEM + TP_TRANS)
    combos = zmk_combos(vil, all_layers)
    macros = zmk_macros(vil)
    used_os, used_lt = apply_os(all_layers)

    blocks = []
    for (node, disp), b in zip(LAYER_NAMES, all_layers):
        assert len(b) == 68, (node, len(b))
        blocks.append(
            f"        {node.lower()}_layer {{\n"
            f"            display-name = \"{disp}\";\n"
            f"            bindings = <\n{fmt_rows(b)}\n            >;\n"
            f"        }};"
        )

    macro_txt = "".join(
        f"\n        /* .vil のマクロ M{m['name'][1:]}: {' → '.join(a[0] + ' ' + '+'.join(a[1:]) for a in m['src'])} */\n"
        f"        {m['name']}: macro_{m['name']} {{\n"
        f"            compatible = \"zmk,behavior-macro\";\n"
        f"            #binding-cells = <0>;\n"
        f"            bindings\n                = " + "\n                , ".join(m["steps"]) + ";\n"
        f"        }};\n" for m in macros)
    combo_txt = "".join(
        f"\n        /* .vil のコンボ {c['name'][6:]}: {' + '.join(c['keys'])} → {c['result']} */\n"
        f"        {c['name']} {{\n"
        f"            timeout-ms = <{c['timeout']}>;\n"
        f"            key-positions = <{' '.join(map(str, c['positions']))}>;\n"
        f"            bindings = <{c['binding']}>;\n"
        f"            layers = <BASE>;\n"
        f"        }};\n" for c in combos)
    os_txt = "".join(
        f"\n        /* {note} */\n"
        f"        {name}: {name} {{\n"
        f"            compatible = \"lalapad,behavior-os-morph\";\n"
        f"            #binding-cells = <0>;\n"
        f"            bindings = <{mac}>, <{win}>;\n"
        f"        }};\n" for mac, win, name, note in OS_MORPHS if name in used_os)
    lt_txt = "".join(
        f"\n        /* &lt と同じ設定で、タップが os_{key}（Mac={'英数' if key == 'eisu' else 'かな'}／Windows={'無変換' if key == 'eisu' else '変換'}） */\n"
        f"        lt_{key}: lt_{key} {{\n"
        f"            compatible = \"zmk,behavior-hold-tap\";\n"
        f"            #binding-cells = <2>;\n"
        f"            flavor = \"balanced\";\n"
        f"            tapping-term-ms = <250>;\n"
        f"            quick-tap-ms = <250>;\n"
        f"            require-prior-idle-ms = <120>;\n"
        f"            bindings = <&mo>, <&os_{key}>;\n"
        f"        }};\n" for key in sorted(used_lt))
    text = (TEMPLATE.replace("@@LAYERS@@", "\n\n".join(blocks))
            .replace("@@MACROS@@", macro_txt + os_txt + lt_txt).replace("@@COMBOS@@", combo_txt))
    open(out_path, "w", encoding="utf-8").write(text)
    print(f"wrote {out_path}: {len(all_layers)} layers, {len(combos)} combos, {len(macros)} macros, "
          f"{len(used_os)} os-morphs, {len(used_lt)} os layer-taps")
    for i, what, why in DROPPED:
        print(f"  置かなかった: L{i} {what}（{why}）")


TEMPLATE = r"""/*
 * LaLapad Gen2 キーマップ — Cornix の Cornix_20261126.vil（10レイヤー）から起こしたもの
 * （REQ-189 で作成、REQ-192・REQ-193 の Gen2 側の決めごと、REQ-194 で .vil を差し替え）
 *
 * 正本は docs/cornix_20261126.vil と tools/vil2zmk.py（このファイルは生成物。手で直さず、再生成する）。
 *   python3 tools/vil2zmk.py docs/cornix_20261126.vil config/lalapadgen2.keymap
 *   python3 tools/gen_visualizer.py
 *
 * レイヤー: 0 Base(大西) / 1 Num / 2 Nav / 3 Fn / 4 Mouse / 5 QWERTY / 6 Kana2（別のカナ配列）/ 7-9 空き / 10 System
 *   - 1 と 2 を同時に押すと 10 System（Gen2 標準の Num+Nav→System と同じ仕組み）
 *   - トラックパッドの低速モードは shield 側で layer 1・2 に掛かる（Gen2 標準のまま）
 *   - 左下段の修飾キーは .vil どおり（L0・L5・L6 は ⌘・Opt・Ctrl、L1〜L4 は Ctrl・Opt・⌘）
 *   - 右下段は .vil どおり Esc。空いている中指・薬指に Delete・戻る（REQ-193 の仮置き）
 *   - 5方向スイッチ（L0〜L4）: 左右＝←→／⌘C・⌘V、上下＝輝度／音量（REQ-192・193）、押し込みは .vil どおり
 *   - トラックパッドのジェスチャーは macOS の作法（⌃←/⌃→・Mission Control など）
 *   - コンボ・マクロは .vil の定義どおり（Shift の親指＋? で !、M0）
 *   - 接続先 OS で変わる割当（REQ-195）: Bluetooth プロファイル 4・5（BT_SEL 3・4）は Windows 用、
 *     1〜3 と USB は Mac 用。os_* の behavior（src/behaviors/behavior_os_morph.c）が押した瞬間に選ぶ。
 *     bindings の 1 番目が Mac 用（.vil どおり）、2 番目が Windows 用。System レイヤーに BT 5（BT_SEL 4）を追加
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
@@MACROS@@    };

    combos {
        compatible = "zmk,combos";
@@COMBOS@@    };

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
