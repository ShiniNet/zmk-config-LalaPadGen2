/*
 * Follow the selected BLE profile: profiles in LALAPAD_OS_LAYER_MAC_PROFILES
 * turn on the Mac base layer, every other profile turns it off (Windows).
 * USB output does not change the layer; it follows the selected BT profile.
 * &tog MAC_DEFAULT_LAYER in the keymap overrides it until the next profile change.
 */

#include <zephyr/kernel.h>
#include <zephyr/init.h>
#include <zephyr/logging/log.h>

#include <zmk/ble.h>
#include <zmk/keymap.h>
#include <zmk/event_manager.h>
#include <zmk/events/ble_active_profile_changed.h>

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

static void apply_profile(int index) {
    zmk_keymap_layer_id_t mac = zmk_keymap_layer_index_to_id(CONFIG_LALAPAD_OS_LAYER_MAC_LAYER);

    if (mac == ZMK_KEYMAP_LAYER_ID_INVAL) {
        LOG_WRN("os_layer: Mac layer %d not found", CONFIG_LALAPAD_OS_LAYER_MAC_LAYER);
        return;
    }

    bool want_mac = index >= 0 && index < 32 && (CONFIG_LALAPAD_OS_LAYER_MAC_PROFILES & BIT(index));

    LOG_INF("os_layer: profile %d -> %s", index, want_mac ? "Mac" : "Win");
    if (want_mac) {
        zmk_keymap_layer_activate(mac);
    } else {
        zmk_keymap_layer_deactivate(mac);
    }
}

static void apply_work_cb(struct k_work *work) { apply_profile(zmk_ble_active_profile_index()); }

static K_WORK_DELAYABLE_DEFINE(apply_work, apply_work_cb);

static int os_layer_listener(const zmk_event_t *eh) {
    if (as_zmk_ble_active_profile_changed(eh) != NULL) {
        k_work_reschedule(&apply_work, K_NO_WAIT);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(lalapad_os_layer, os_layer_listener);
ZMK_SUBSCRIPTION(lalapad_os_layer, zmk_ble_active_profile_changed);

/* settings_load() runs in main() after SYS_INIT, so apply the restored profile a bit later. */
static int os_layer_init(void) {
    k_work_reschedule(&apply_work, K_MSEC(CONFIG_LALAPAD_OS_LAYER_BOOT_DELAY_MS));
    return 0;
}

SYS_INIT(os_layer_init, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
