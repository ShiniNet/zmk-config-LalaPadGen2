# 大西配列（Cornix .vil 由来）の LaLapad Gen2 キーマップ

- キーマップの正本: `config/lalapadgen2.keymap`
- 変換元と対応表: `docs/ohnishi_cornix.vil` / `docs/REQ-189_対応表.md`
- ビジュアライザー: `docs/lalapadgen2_visualizer.html`

キーマップを直したら、ビジュアライザーを作り直す:

    python3 tools/gen_visualizer.py

（`tools/vil2zmk.py` は最初の変換に使ったもの。再実行するとキーマップが .vil から作り直されて上書きされる）
