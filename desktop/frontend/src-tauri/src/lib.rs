// jr-dashboard Tauri shell.
//
// Responsibilities:
//   - On app start, spawn the FastAPI sidecar
//       * dev (debug)    : run the project's venv python on api/main.py
//       * release        : run the bundled jr-api.exe inside resources/jr-api/
//   - Forward stdout/stderr lines to Tauri logs
//   - On app exit, kill the sidecar child process

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::io::{BufRead, BufReader};
use std::thread;
use tauri::{Manager, RunEvent};

struct Sidecar(Mutex<Option<Child>>);

fn spawn_sidecar_dev() -> std::io::Result<Child> {
    // Hard-coded dev path. Override with JR_DEV_PYTHON / JR_DEV_API env vars.
    let py = std::env::var("JR_DEV_PYTHON")
        .unwrap_or_else(|_| "D:/PM/jr/.venv/Scripts/python.exe".to_string());
    let api = std::env::var("JR_DEV_API")
        .unwrap_or_else(|_| "D:/PM/jr/desktop/api/main.py".to_string());
    log::info!("spawn sidecar (dev): {} {}", py, api);
    Command::new(&py)
        .arg(&api)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

fn spawn_sidecar_release(app: &tauri::AppHandle) -> std::io::Result<Child> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::NotFound, e.to_string()))?;
    let exe = resource_dir.join("jr-api").join("jr-api.exe");
    log::info!("spawn sidecar (release): {:?}", exe);
    Command::new(&exe)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

fn pipe_logs(mut child: Child) -> Child {
    if let Some(out) = child.stdout.take() {
        thread::spawn(move || {
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                log::info!("[sidecar] {}", line);
            }
        });
    }
    if let Some(err) = child.stderr.take() {
        thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                log::info!("[sidecar/err] {}", line);
            }
        });
    }
    child
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let context = tauri::generate_context!();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())
        .manage(Sidecar(Mutex::new(None)))
        .setup(|app| {
            let result = if cfg!(debug_assertions) {
                spawn_sidecar_dev()
            } else {
                spawn_sidecar_release(&app.handle())
            };
            match result {
                Ok(child) => {
                    let child = pipe_logs(child);
                    let state: tauri::State<Sidecar> = app.state();
                    *state.0.lock().unwrap() = Some(child);
                    log::info!("FastAPI sidecar started");
                }
                Err(e) => {
                    log::error!("failed to start sidecar: {}", e);
                }
            }
            Ok(())
        })
        .build(context)
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            log::info!("exit: killing sidecar");
            let child_opt: Option<Child> = {
                let state: tauri::State<Sidecar> = app_handle.state();
                let mut guard = state.0.lock().unwrap();
                guard.take()
            };
            if let Some(mut child) = child_opt {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
