#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    error::Error,
    fs::{self, File},
    io::{self, Read, Write},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{
    webview::PageLoadEvent, App, AppHandle, Manager, RunEvent, Url, WebviewUrl,
    WebviewWindowBuilder,
};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

const DESKTOP_API_HOST: &str = "127.0.0.1";
const PREFERRED_API_PORT: u16 = 8765;
const LAST_API_PORT: u16 = 8795;
const RUNTIME_READY_TIMEOUT: Duration = Duration::from_secs(60);

const SPLASH_HTML: &str = include_str!("../splash.html");

// The packaged webview bundle hard-codes http://127.0.0.1:8765 at build time
// (VITE_API_URL in desktop:build:web). When the runtime falls back to another
// port this script rewrites requests inside the webview, so the frontend
// bundle needs no rebuild and no knowledge of the fallback.
const PORT_REWRITE_SCRIPT: &str = r#"
(() => {
  const rewrite = (value) => String(value).replace(
    /^(https?:\/\/)(127\.0\.0\.1|localhost):8765(?=\/|$)/,
    "$1127.0.0.1:__QB_PORT__",
  );
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    if (typeof input === "string") return nativeFetch(rewrite(input), init);
    if (input instanceof Request) return nativeFetch(new Request(rewrite(input.url), input), init);
    return nativeFetch(input, init);
  };
  const NativeEventSource = window.EventSource;
  if (NativeEventSource) {
    const PatchedEventSource = function (url, config) {
      return new NativeEventSource(rewrite(url), config);
    };
    PatchedEventSource.prototype = NativeEventSource.prototype;
    PatchedEventSource.CONNECTING = NativeEventSource.CONNECTING;
    PatchedEventSource.OPEN = NativeEventSource.OPEN;
    PatchedEventSource.CLOSED = NativeEventSource.CLOSED;
    window.EventSource = PatchedEventSource;
  }
})();
"#;

#[derive(Default)]
struct RuntimeState(Mutex<Option<Child>>);

#[derive(Debug, PartialEq)]
enum WaitOutcome {
    Ready,
    RuntimeExited,
    TimedOut,
}

fn port_rewrite_script(port: u16) -> String {
    PORT_REWRITE_SCRIPT.replace("__QB_PORT__", &port.to_string())
}

// A bind probe, released immediately. The gap between this probe and the
// sidecar's own bind is covered by the nonce check and the child liveness
// check in wait_for_runtime.
fn pick_api_port(first: u16, last: u16) -> Option<u16> {
    (first..=last).find(|port| TcpListener::bind((DESKTOP_API_HOST, *port)).is_ok())
}

// RandomState seeds from OS randomness, so no rand dependency is needed. The
// nonce distinguishes this launch's sidecar from any other local process that
// answers on the chosen port; it is not a secret.
fn launch_nonce() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};

    let mut hasher = RandomState::new().build_hasher();
    hasher.write_u32(std::process::id());
    let first = hasher.finish();
    let mut hasher = RandomState::new().build_hasher();
    hasher.write_u64(first);
    format!("{first:016x}{:016x}", hasher.finish())
}

// The sidecar is spawned with QUESTBOARD_LAUNCH_NONCE and /health echoes it,
// so a healthy answer must carry THIS launch's nonce. A body without the
// field is some other process on the port; never attach to it.
fn health_response_ready(response: &str, nonce: &str) -> bool {
    if !response.contains("\"status\":\"ok\"") {
        return false;
    }
    response.contains(&format!("\"launch_nonce\":\"{nonce}\""))
}

fn isolate_runtime_process(command: &mut Command) {
    // PyInstaller's one-file bootloader starts the actual Python runtime as a
    // child process. Give the sidecar its own process group so quitting the
    // desktop shell can terminate both layers, including any scraper children.
    #[cfg(unix)]
    command.process_group(0);
}

#[cfg(debug_assertions)]
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .unwrap_or_else(|_| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("..")
        })
}

fn app_data_root(app: &AppHandle) -> Result<PathBuf, Box<dyn Error>> {
    let app_data_dir = app.path().app_data_dir()?;
    fs::create_dir_all(&app_data_dir)?;
    Ok(app_data_dir)
}

fn runtime_log_file(app: &AppHandle) -> Result<(File, PathBuf), Box<dyn Error>> {
    let logs_dir = app_data_root(app)?.join("logs");
    fs::create_dir_all(&logs_dir)?;
    let log_path = logs_dir.join("runtime.log");
    if log_path.exists() {
        let _ = fs::rename(&log_path, logs_dir.join("runtime.previous.log"));
    }
    let file = File::create(&log_path)?;
    Ok((file, log_path))
}

fn desktop_runtime_args(app: &AppHandle, port: u16) -> Result<Vec<String>, Box<dyn Error>> {
    let app_data_dir = app_data_root(app)?;
    let data_dir = app_data_dir.join("runtime-data");
    let workspace_dir = data_dir.join("workspaces");
    let resume_dir = app_data_dir.join("knowledge");
    let config_dir = app_data_dir.join("config");

    fs::create_dir_all(&workspace_dir)?;
    fs::create_dir_all(&resume_dir)?;
    fs::create_dir_all(&config_dir)?;

    Ok(vec![
        "--host".into(),
        DESKTOP_API_HOST.into(),
        "--port".into(),
        port.to_string(),
        "--data-dir".into(),
        data_dir.display().to_string(),
        "--workspace-storage-dir".into(),
        workspace_dir.display().to_string(),
        "--resume-dir".into(),
        resume_dir.display().to_string(),
        "--config-dir".into(),
        config_dir.display().to_string(),
        "--dev-origin".into(),
        "http://127.0.0.1:5173".into(),
    ])
}

fn configure_runtime_command(
    command: &mut Command,
    runtime_args: &[String],
    nonce: &str,
    log_file: &File,
) -> io::Result<()> {
    command
        .args(runtime_args)
        .env("QUESTBOARD_LAUNCH_NONCE", nonce)
        .stdout(Stdio::from(log_file.try_clone()?))
        .stderr(Stdio::from(log_file.try_clone()?));
    isolate_runtime_process(command);
    Ok(())
}

fn spawn_runtime(
    app: &AppHandle,
    port: u16,
    nonce: &str,
    log_file: &File,
) -> Result<Child, Box<dyn Error>> {
    let runtime_args = desktop_runtime_args(app, port)?;

    if let Some(explicit_runtime) = env::var_os("QUESTBOARD_DESKTOP_RUNTIME") {
        let mut command = Command::new(explicit_runtime);
        configure_runtime_command(&mut command, &runtime_args, nonce, log_file)?;
        return Ok(command.spawn()?);
    }

    // Source checkouts use the virtualenv only in debug builds. Release apps
    // always exercise the exact sidecar shipped in Contents/Resources, so a
    // developer machine cannot accidentally hide a broken friend build.
    #[cfg(debug_assertions)]
    {
        let repo_root = repo_root();
        let dev_python_candidates = [
            repo_root.join(".venv").join("bin").join("python"),
            repo_root.join(".venv").join("Scripts").join("python.exe"),
        ];
        if let Some(dev_python) = dev_python_candidates
            .iter()
            .find(|candidate| candidate.exists())
        {
            let mut command = Command::new(dev_python);
            command
                .current_dir(repo_root.join("backend"))
                .env("PYTHONPATH", "../src")
                .args(["-m", "app.desktop_runtime"]);
            configure_runtime_command(&mut command, &runtime_args, nonce, log_file)?;
            return Ok(command.spawn()?);
        }
    }

    let resource_dir = app.path().resource_dir()?;
    let packaged_runtime_candidates = [
        resource_dir.join("sidecars").join("questboard-runtime"),
        resource_dir.join("sidecars").join("questboard-runtime.exe"),
    ];
    if let Some(packaged_runtime) = packaged_runtime_candidates
        .iter()
        .find(|candidate| candidate.exists())
    {
        let mut command = Command::new(packaged_runtime);
        configure_runtime_command(&mut command, &runtime_args, nonce, log_file)?;
        return Ok(command.spawn()?);
    }

    Err(io::Error::new(
        io::ErrorKind::NotFound,
        "Questboard desktop runtime not found. For development, run `make setup` first. For packaged builds, bundle a `questboard-runtime` sidecar or set QUESTBOARD_DESKTOP_RUNTIME.",
    )
    .into())
}

fn runtime_ready(port: u16, nonce: &str) -> bool {
    let mut stream = match std::net::TcpStream::connect((DESKTOP_API_HOST, port)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
    let request = format!(
        "GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Questboard-Launch-Nonce: {nonce}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    health_response_ready(&response, nonce)
}

fn runtime_exited(app: &AppHandle) -> bool {
    let Some(state) = app.try_state::<RuntimeState>() else {
        return false;
    };
    let Ok(mut guard) = state.0.lock() else {
        return false;
    };
    match guard.as_mut() {
        Some(child) => matches!(child.try_wait(), Ok(Some(_))),
        None => false,
    }
}

fn wait_for_runtime(app: &AppHandle, port: u16, nonce: &str, timeout: Duration) -> WaitOutcome {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        // Exit check first: if our sidecar died, whatever answers on the port
        // is not ours, so do not attach to it.
        if runtime_exited(app) {
            return WaitOutcome::RuntimeExited;
        }
        if runtime_ready(port, nonce) {
            return WaitOutcome::Ready;
        }
        thread::sleep(Duration::from_millis(250));
    }
    WaitOutcome::TimedOut
}

fn kill_runtime(app: &AppHandle) {
    if let Some(state) = app.try_state::<RuntimeState>() {
        if let Ok(mut child) = state.0.lock() {
            if let Some(child) = child.as_mut() {
                terminate_runtime_process(child);
            }
            *child = None;
        }
    }
}

fn terminate_runtime_process(child: &mut Child) {
    #[cfg(unix)]
    {
        let process_group = child.id() as i32;
        // Negative PID targets the complete process group. SIGTERM gives
        // Uvicorn a chance to close SQLite cleanly before the hard deadline.
        unsafe {
            libc::kill(-process_group, libc::SIGTERM);
        }
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            let parent_exited = child.try_wait().ok().flatten().is_some();
            let group_alive = unsafe { libc::kill(-process_group, 0) == 0 };
            if parent_exited && !group_alive {
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        unsafe {
            libc::kill(-process_group, libc::SIGKILL);
        }
    }

    // This is also the complete implementation on Windows, where Child::kill
    // handles the directly spawned runtime executable.
    let _ = child.kill();
    let _ = child.wait();
}

// Must run off the main thread: blocking_show parks the calling thread while
// the dialog itself runs on the main thread, so the user always sees the
// failure before the process exits. No panic path remains in a release build.
fn fail_launch(app: &AppHandle, headline: &str, log_path: Option<&Path>) {
    kill_runtime(app);
    let mut message = format!("{headline}\n\nQuit and reopen Questboard to try again.");
    if let Some(path) = log_path {
        message.push_str(&format!("\n\nIf it keeps happening, this log says why:\n{}", path.display()));
    }
    app.dialog()
        .message(message)
        .title("Questboard could not start")
        .kind(MessageDialogKind::Error)
        .blocking_show();
    app.exit(1);
}

fn close_splash(app: &AppHandle) {
    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.close();
    }
}

fn show_splash(app: &App) {
    let url = if cfg!(windows) {
        "http://qbsplash.localhost/"
    } else {
        "qbsplash://localhost/"
    };
    let splash = WebviewWindowBuilder::new(
        app,
        "splash",
        WebviewUrl::CustomProtocol(Url::parse(url).expect("static splash url")),
    )
    .title("Questboard")
    .inner_size(380.0, 200.0)
    .resizable(false)
    .decorations(false)
    .center()
    .build();
    if let Err(error) = splash {
        // Not fatal: the main window still appears once the runtime is ready.
        eprintln!("questboard: splash window failed: {error}");
    }
}

fn attach_main_window(app: &AppHandle, port: u16, log_path: PathBuf) {
    let handle = app.clone();
    let dispatched = app.run_on_main_thread(move || {
        let Some(window_config) = handle
            .config()
            .app
            .windows
            .iter()
            .find(|window| window.label == "main")
            .cloned()
        else {
            main_window_failed(&handle, "main window config missing", &log_path);
            return;
        };

        let builder = match WebviewWindowBuilder::from_config(&handle, &window_config) {
            Ok(builder) => builder,
            Err(error) => {
                main_window_failed(&handle, &error.to_string(), &log_path);
                return;
            }
        };
        let builder = if port == PREFERRED_API_PORT {
            builder
        } else {
            builder.initialization_script(port_rewrite_script(port))
        };
        // Reveal on the finished load so the swap from splash to app never
        // shows a blank webview.
        let builder = builder.on_page_load(|window, payload| {
            if matches!(payload.event(), PageLoadEvent::Finished) {
                let _ = window.show();
                let _ = window.set_focus();
                close_splash(window.app_handle());
            }
        });

        match builder.build() {
            Ok(window) => {
                // If the load event never fires, show anyway rather than sit
                // invisible forever.
                thread::spawn(move || {
                    thread::sleep(Duration::from_secs(5));
                    if !window.is_visible().unwrap_or(true) {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                    close_splash(window.app_handle());
                });
            }
            Err(error) => main_window_failed(&handle, &error.to_string(), &log_path),
        }
    });
    if dispatched.is_err() {
        app.exit(1);
    }
}

fn main_window_failed(app: &AppHandle, error: &str, log_path: &Path) {
    eprintln!("questboard: main window failed: {error}");
    let handle = app.clone();
    let log_path = log_path.to_path_buf();
    // fail_launch blocks on a dialog, which is not allowed on the main thread.
    thread::spawn(move || {
        fail_launch(
            &handle,
            "Questboard's window could not be created.",
            Some(&log_path),
        );
    });
}

fn boot_runtime(app: AppHandle) {
    let Some(port) = pick_api_port(PREFERRED_API_PORT, LAST_API_PORT) else {
        fail_launch(
            &app,
            "Every port Questboard can use (8765 to 8795) is taken by other software on this Mac.",
            None,
        );
        return;
    };

    let (log_file, log_path) = match runtime_log_file(&app) {
        Ok(log) => log,
        Err(error) => {
            eprintln!("questboard: cannot create runtime log: {error}");
            fail_launch(&app, "Questboard could not write to its data folder.", None);
            return;
        }
    };

    let nonce = launch_nonce();
    match spawn_runtime(&app, port, &nonce, &log_file) {
        Ok(child) => {
            if let Some(state) = app.try_state::<RuntimeState>() {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(child);
                }
            }
        }
        Err(error) => {
            let _ = writeln!(&log_file, "questboard: runtime spawn failed: {error}");
            fail_launch(
                &app,
                "Questboard's background service failed to launch.",
                Some(&log_path),
            );
            return;
        }
    }

    // A cold, signed PyInstaller sidecar can spend more than 20s loading
    // pandas/scipy on macOS before Uvicorn binds its port. The splash stays
    // up while it boots; a healthy first launch is never aborted merely
    // because warm launches are much faster.
    match wait_for_runtime(&app, port, &nonce, RUNTIME_READY_TIMEOUT) {
        WaitOutcome::Ready => attach_main_window(&app, port, log_path),
        WaitOutcome::RuntimeExited => fail_launch(
            &app,
            "Questboard's background service stopped unexpectedly while starting.",
            Some(&log_path),
        ),
        WaitOutcome::TimedOut => fail_launch(
            &app,
            "Questboard's background service did not respond within 60 seconds.",
            Some(&log_path),
        ),
    }
}

/// Stop the backend before an update overwrites the app bundle.
///
/// The runtime holds an open SQLite file and a listening port; leaving it
/// to die on its own during the relaunch races the new instance for both.
#[tauri::command]
fn shutdown_runtime_for_update(app: AppHandle) {
    kill_runtime(&app);
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![shutdown_runtime_for_update])
        .manage(RuntimeState::default())
        .register_uri_scheme_protocol("qbsplash", |_ctx, _request| {
            tauri::http::Response::builder()
                .header("Content-Type", "text/html; charset=utf-8")
                .body(SPLASH_HTML.as_bytes().to_vec())
                .unwrap()
        })
        .setup(|app| {
            show_splash(app);
            // The readiness wait must not block setup: the splash cannot
            // paint until the event loop runs.
            let handle = app.handle().clone();
            thread::spawn(move || boot_runtime(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Questboard desktop");

    app.run(|app, event| match event {
        RunEvent::Exit | RunEvent::ExitRequested { .. } => {
            kill_runtime(app);
        }
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    const OK_PLAIN: &str =
        "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{\"status\":\"ok\"}";

    #[test]
    fn health_ready_rejects_ok_without_nonce_echo() {
        // The bundled backend always echoes its launch nonce; a plain ok is
        // some other process holding the port, and attaching to it wires the
        // window to a stranger's database.
        assert!(!health_response_ready(OK_PLAIN, "abc123"));
    }

    #[test]
    fn health_ready_requires_matching_nonce_when_echoed() {
        let response = "HTTP/1.1 200 OK\r\n\r\n{\"status\":\"ok\",\"launch_nonce\":\"abc123\"}";
        assert!(health_response_ready(response, "abc123"));
    }

    #[test]
    fn health_ready_rejects_another_launches_nonce() {
        // Two Questboard instances racing for one port: the loser must not
        // adopt the winner's backend.
        let response = "HTTP/1.1 200 OK\r\n\r\n{\"status\":\"ok\",\"launch_nonce\":\"other99\"}";
        assert!(!health_response_ready(response, "abc123"));
    }

    #[test]
    fn health_ready_rejects_non_ok_status() {
        let response = "HTTP/1.1 200 OK\r\n\r\n{\"status\":\"degraded\"}";
        assert!(!health_response_ready(response, "abc123"));
    }

    #[test]
    fn pick_port_prefers_first_free() {
        let probe = TcpListener::bind((DESKTOP_API_HOST, 0)).unwrap();
        let port = probe.local_addr().unwrap().port();
        drop(probe);
        assert_eq!(pick_api_port(port, port), Some(port));
    }

    #[test]
    fn pick_port_skips_occupied() {
        let held = TcpListener::bind((DESKTOP_API_HOST, 0)).unwrap();
        let busy = held.local_addr().unwrap().port();
        let picked = pick_api_port(busy, busy.saturating_add(20));
        assert_ne!(picked, Some(busy));
    }

    #[test]
    fn pick_port_none_when_range_busy() {
        let held = TcpListener::bind((DESKTOP_API_HOST, 0)).unwrap();
        let busy = held.local_addr().unwrap().port();
        assert_eq!(pick_api_port(busy, busy), None);
    }

    #[test]
    fn nonces_are_unique_hex() {
        let a = launch_nonce();
        let b = launch_nonce();
        assert_ne!(a, b);
        assert_eq!(a.len(), 32);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn rewrite_script_substitutes_port() {
        let script = port_rewrite_script(8767);
        assert!(script.contains("127.0.0.1:8767"));
        assert!(!script.contains("__QB_PORT__"));
    }
}
