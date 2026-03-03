use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager,
};

/// Show a native OS notification.
#[tauri::command]
fn show_notification(app: tauri::AppHandle, title: String, body: String) -> Result<String, String> {
    app.emit("notification", serde_json::json!({"title": &title, "body": &body}))
        .map_err(|e| e.to_string())?;

    #[cfg(feature = "notification")]
    {
        use tauri_plugin_notification::NotificationExt;
        app.notification()
            .builder()
            .title(&title)
            .body(&body)
            .show()
            .map_err(|e| e.to_string())?;
    }

    Ok("ok".into())
}

/// Open a native file picker dialog and return the selected path.
#[tauri::command]
async fn open_file_dialog(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    let file = app
        .dialog()
        .file()
        .add_filter(
            "Documents",
            &["pdf", "txt", "md", "docx", "epub", "html", "json", "yaml", "csv"],
        )
        .add_filter("Code", &["py", "js", "ts", "rs", "go", "java"])
        .add_filter("All Files", &["*"])
        .blocking_pick_file();

    match file {
        Some(path) => Ok(Some(path.to_string())),
        None => Ok(None),
    }
}

/// Get audio devices — delegates to the Python API, returns the API URL.
#[tauri::command]
fn get_api_base_url() -> String {
    std::env::var("EMILY_API_URL").unwrap_or_else(|_| "http://127.0.0.1:8001".into())
}

/// Set the system tray tooltip/status text.
#[tauri::command]
fn set_tray_status(app: tauri::AppHandle, status: String) -> Result<(), String> {
    if let Some(tray) = app.tray_by_id("emily-tray") {
        tray.set_tooltip(Some(&status)).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let toggle_item = MenuItem::with_id(app, "toggle_listen", "Start Listening", true, None::<&str>)?;
    let open_item = MenuItem::with_id(app, "open_emily", "Open Emily", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&toggle_item, &open_item, &quit_item])?;

    TrayIconBuilder::with_id("emily-tray")
        .tooltip("Emily — Idle")
        .menu(&menu)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "toggle_listen" => {
                let _ = app.emit("tray-toggle-listen", ());
            }
            "open_emily" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            show_notification,
            open_file_dialog,
            get_api_base_url,
            set_tray_status,
        ])
        .setup(|app| {
            build_tray(app)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
