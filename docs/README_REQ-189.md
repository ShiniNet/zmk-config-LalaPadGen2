# 大西配列（Cornix .vil 由来）の LaLapad Gen2 キーマップ

- 正本: `docs/cornix_20261126.vil`（稜太の Cornix の現行キーマップ、REQ-194）と `tools/vil2zmk.py`（Gen2 側の決めごと `apply_gen2` を含む）
- 生成物: `config/lalapadgen2.keymap`（手で直さず、下の手順で作り直す）
- 対応表: `docs/REQ-189_対応表.md`（REQ-194 の差分一覧を含む）
- ビジュアライザー: `docs/lalapadgen2_visualizer.html`
- 旧版の .vil（REQ-189〜193 で使った大西配列.vil）: `docs/ohnishi_cornix.vil`
- 接続先 OS で変わる割当（REQ-195）: Bluetooth プロファイル 4・5 は Windows 用、1〜3 と USB は Mac 用。
  behavior の実装は `src/behaviors/behavior_os_morph.c`（このリポジトリを Zephyr モジュールとして読み込む。`zephyr/module.yml`・`CMakeLists.txt`・`Kconfig`・`dts/bindings/`）。
  Windows 用の割当の表は `tools/vil2zmk.py` の `OS_MORPHS`

キーマップを作り直す:

    python3 tools/vil2zmk.py docs/cornix_20261126.vil config/lalapadgen2.keymap
    python3 tools/gen_visualizer.py

`vil2zmk.py` は、Gen2 側の決めごとで .vil のキーを上書きした箇所を「置かなかった」として一覧で出す。
