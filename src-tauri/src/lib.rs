use tauri::Manager;
use tauri_nspanel::{
    tauri_panel, CollectionBehavior, ManagerExt, PanelLevel, StyleMask, WebviewWindowExt,
};

tauri_panel! {
    panel!(OverlayPanel {
        config: {
            can_become_key_window: true,
            is_floating_panel: true
        }
    })
}

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn show_panel(handle: tauri::AppHandle) {
    let panel = handle.get_webview_panel("main").unwrap();
    panel.show();
}

#[tauri::command]
fn hide_panel(handle: tauri::AppHandle) {
    let panel = handle.get_webview_panel("main").unwrap();
    panel.hide();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_nspanel::init())
        .invoke_handler(tauri::generate_handler![greet, show_panel, hide_panel])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();

            let panel = window.to_panel::<OverlayPanel>().unwrap();

            // Float above everything including fullscreen apps
            panel.set_level(PanelLevel::ScreenSaver.value());

            // Don't steal focus from the active app
            panel.set_style_mask(StyleMask::empty().nonactivating_panel().into());

            // Show on all spaces + over fullscreen apps
            panel.set_collection_behavior(
                CollectionBehavior::new()
                    .full_screen_auxiliary()
                    .can_join_all_spaces()
                    .into(),
            );

            panel.set_has_shadow(false);

            panel.show();

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
