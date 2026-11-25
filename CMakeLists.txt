# 接続先 OS で割当を切り替える behavior（REQ-195）。キーマップを持つ側（split の central＝右手）だけで使う。
if ((NOT CONFIG_ZMK_SPLIT) OR CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
  target_sources_ifdef(CONFIG_ZMK_BEHAVIOR_OS_MORPH app PRIVATE src/behaviors/behavior_os_morph.c)
endif()
