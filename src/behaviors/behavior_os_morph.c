/*
 * os-morph: 接続先 OS で割当を切り替える behavior（REQ-195）
 *
 *   bindings = <Mac 用>, <Windows 用>;
 *
 * キーを押した瞬間に、いま選ばれている接続先（ZMK の endpoint）を見て、どちらを押すか決める。
 *   - Bluetooth で、プロファイル番号が CONFIG_ZMK_BEHAVIOR_OS_MORPH_WIN_PROFILES に含まれる → Windows 用
 *   - それ以外（Bluetooth のプロファイル 1〜3、USB）→ Mac 用
 * 押したときに選んだ割当を位置ごとに覚えておき、離すときは同じ割当を離す
 * （押している途中で接続先が変わっても、押しっぱなしのキーが残らない）。
 *
 * 作りは ZMK v0.3 の mod-morph（app/src/behaviors/behavior_mod_morph.c）に倣った。
 */

#define DT_DRV_COMPAT lalapad_behavior_os_morph

#include <zephyr/device.h>
#include <drivers/behavior.h>
#include <zephyr/logging/log.h>
#include <zmk/behavior.h>
#include <zmk/endpoints.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

#define OS_MORPH_SLOTS 8 /* 同じ os-morph を同時に押しておける数（位置の数） */

struct behavior_os_morph_config {
    struct zmk_behavior_binding mac_binding;
    struct zmk_behavior_binding win_binding;
};

struct os_morph_slot {
    bool used;
    uint32_t position;
    const struct zmk_behavior_binding *binding;
};

struct behavior_os_morph_data {
    struct os_morph_slot slots[OS_MORPH_SLOTS];
};

static bool os_morph_use_windows(void) {
    struct zmk_endpoint_instance ep = zmk_endpoints_selected();

    if (ep.transport != ZMK_TRANSPORT_BLE) {
        return false;
    }
    if (ep.ble.profile_index < 0 || ep.ble.profile_index >= 32) {
        return false;
    }
    return (CONFIG_ZMK_BEHAVIOR_OS_MORPH_WIN_PROFILES >> ep.ble.profile_index) & 1U;
}

static int on_os_morph_binding_pressed(struct zmk_behavior_binding *binding,
                                       struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_os_morph_config *cfg = dev->config;
    struct behavior_os_morph_data *data = dev->data;
    const struct zmk_behavior_binding *chosen =
        os_morph_use_windows() ? &cfg->win_binding : &cfg->mac_binding;

    for (int i = 0; i < OS_MORPH_SLOTS; i++) {
        if (!data->slots[i].used) {
            data->slots[i].used = true;
            data->slots[i].position = event.position;
            data->slots[i].binding = chosen;
            return zmk_behavior_invoke_binding(chosen, event, true);
        }
    }

    LOG_ERR("os-morph: too many keys held at once");
    return -ENOMEM;
}

static int on_os_morph_binding_released(struct zmk_behavior_binding *binding,
                                        struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    struct behavior_os_morph_data *data = dev->data;

    for (int i = 0; i < OS_MORPH_SLOTS; i++) {
        if (data->slots[i].used && data->slots[i].position == event.position) {
            const struct zmk_behavior_binding *pressed = data->slots[i].binding;
            data->slots[i].used = false;
            return zmk_behavior_invoke_binding(pressed, event, false);
        }
    }

    LOG_WRN("os-morph: released without a matching press (position %u)",
            (unsigned int)event.position);
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_os_morph_driver_api = {
    .binding_pressed = on_os_morph_binding_pressed,
    .binding_released = on_os_morph_binding_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

#define OS_MORPH_ENTRY(idx, node)                                                                  \
    {                                                                                              \
        .behavior_dev = DEVICE_DT_NAME(DT_INST_PHANDLE_BY_IDX(node, bindings, idx)),               \
        .param1 = COND_CODE_0(DT_INST_PHA_HAS_CELL_AT_IDX(node, bindings, idx, param1), (0),       \
                              (DT_INST_PHA_BY_IDX(node, bindings, idx, param1))),                  \
        .param2 = COND_CODE_0(DT_INST_PHA_HAS_CELL_AT_IDX(node, bindings, idx, param2), (0),       \
                              (DT_INST_PHA_BY_IDX(node, bindings, idx, param2))),                  \
    }

#define OS_MORPH_INST(n)                                                                           \
    BUILD_ASSERT(DT_INST_PROP_LEN(n, bindings) == 2,                                               \
                 "os-morph needs exactly two bindings: <mac>, <windows>");                     \
    static const struct behavior_os_morph_config behavior_os_morph_config_##n = {                  \
        .mac_binding = OS_MORPH_ENTRY(0, n),                                                       \
        .win_binding = OS_MORPH_ENTRY(1, n),                                                       \
    };                                                                                             \
    static struct behavior_os_morph_data behavior_os_morph_data_##n = {};                          \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, &behavior_os_morph_data_##n,                            \
                            &behavior_os_morph_config_##n, POST_KERNEL,                            \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &behavior_os_morph_driver_api);

DT_INST_FOREACH_STATUS_OKAY(OS_MORPH_INST)

#endif /* DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT) */
