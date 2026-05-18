// jr-dashboard Tauri shell.
//
// Responsibilities:
//   - On app start, spawn the FastAPI sidecar
//       * dev (debug)    : run the project's venv python on api/main.py
//       * release        : run the bundled jr-api.exe inside resources/jr-api/
//   - Forward stdout/stderr lines to Tauri logs
//   - Watchdog: if sidecar dies, respawn it (unless we're shutting down)
//   - On app exit, kill the sidecar child process

use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::io::{BufRead, BufReader};
use std::thread;
use std::time::Duration;
use tauri::{Manager, RunEvent};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

/// Build a Command that won't pop a console window on Windows.
fn no_console_cmd<P: AsRef<std::ffi::OsStr>>(program: P) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

struct Sidecar(Mutex<Option<Child>>);
static SHUTTING_DOWN: AtomicBool = AtomicBool::new(false);

fn spawn_sidecar_dev() -> std::io::Result<Child> {
    let py = std::env::var("JR_DEV_PYTHON")
        .unwrap_or_else(|_| "D:/PM/jr/.venv/Scripts/python.exe".to_string());
    let api = std::env::var("JR_DEV_API")
        .unwrap_or_else(|_| "D:/PM/jr/desktop/api/main.py".to_string());
    log::info!("spawn sidecar (dev): {} {}", py, api);
    no_console_cmd(&py)
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
    no_console_cmd(&exe)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
}

fn spawn_for_current_mode(app: &tauri::AppHandle) -> std::io::Result<Child> {
    if cfg!(debug_assertions) { spawn_sidecar_dev() } else { spawn_sidecar_release(app) }
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

fn start_watchdog(app: tauri::AppHandle) {
    thread::spawn(move || {
        let mut consecutive_failures = 0;
        loop {
            thread::sleep(Duration::from_secs(5));
            if SHUTTING_DOWN.load(Ordering::SeqCst) {
                return;
            }

            // Check current child status
            let dead_or_missing = {
                let state: tauri::State<Sidecar> = app.state();
                let mut guard = state.0.lock().unwrap();
                match guard.as_mut() {
                    Some(child) => match child.try_wait() {
                        Ok(Some(status)) => {
                            log::warn!("sidecar exited with {:?} — respawning", status);
                            *guard = None;
                            true
                        }
                        Ok(None) => false,
                        Err(e) => {
                            log::warn!("watchdog try_wait error: {}", e);
                            false
                        }
                    },
                    None => true,
                }
            };

            if !dead_or_missing {
                consecutive_failures = 0;
                continue;
            }

            // Back off after repeated failures to avoid hot loop
            if consecutive_failures >= 5 {
                log::error!("sidecar has failed {} times in a row — pausing watchdog 60s", consecutive_failures);
                thread::sleep(Duration::from_secs(60));
            }

            match spawn_for_current_mode(&app) {
                Ok(child) => {
                    let child = pipe_logs(child);
                    let state: tauri::State<Sidecar> = app.state();
                    *state.0.lock().unwrap() = Some(child);
                    log::info!("sidecar respawned by watchdog");
                    consecutive_failures = 0;
                }
                Err(e) => {
                    log::error!("watchdog: failed to respawn sidecar: {}", e);
                    consecutive_failures += 1;
                }
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let context = tauri::generate_context!();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())
        .manage(Sidecar(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            match spawn_for_current_mode(&handle) {
                Ok(child) => {
                    let child = pipe_logs(child);
                    let state: tauri::State<Sidecar> = app.state();
                    *state.0.lock().unwrap() = Some(child);
                    log::info!("FastAPI sidecar started");
                }
                Err(e) => {
                    log::error!("failed to start sidecar: {} — watchdog will retry", e);
                }
            }
            start_watchdog(handle);
            Ok(())
        })
        .build(context)
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            SHUTTING_DOWN.store(true, Ordering::SeqCst);
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
