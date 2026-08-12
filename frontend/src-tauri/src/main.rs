#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    error::Error,
    fs,
    io::{self, Read, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use tauri::{App, Manager, RunEvent};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

const DESKTOP_API_HOST: &str = "127.0.0.1";
const DESKTOP_API_PORT: u16 = 8765;

#[derive(Default)]
struct RuntimeState(Mutex<Option<Child>>);

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

fn app_data_root(app: &App) -> Result<PathBuf, Box<dyn Error>> {
    let app_data_dir = app.path().app_data_dir()?;
    fs::create_dir_all(&app_data_dir)?;
    Ok(app_data_dir)
}

fn desktop_runtime_args(app: &App) -> Result<Vec<String>, Box<dyn Error>> {
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
        DESKTOP_API_PORT.to_string(),
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

fn spawn_runtime(app: &App) -> Result<Child, Box<dyn Error>> {
    let runtime_args = desktop_runtime_args(app)?;

    if let Some(explicit_runtime) = env::var_os("QUESTBOARD_DESKTOP_RUNTIME") {
        let mut command = Command::new(explicit_runtime);
        command
            .args(&runtime_args)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        isolate_runtime_process(&mut command);
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
                .args(["-m", "app.desktop_runtime"])
                .args(&runtime_args)
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit());
            isolate_runtime_process(&mut command);
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
        command
            .args(&runtime_args)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        isolate_runtime_process(&mut command);
        return Ok(command.spawn()?);
    }

    Err(io::Error::new(
        io::ErrorKind::NotFound,
        "Questboard desktop runtime not found. For development, run `make setup` first. For packaged builds, bundle a `questboard-runtime` sidecar or set QUESTBOARD_DESKTOP_RUNTIME.",
    )
    .into())
}

fn runtime_ready() -> bool {
    let mut stream = match std::net::TcpStream::connect((DESKTOP_API_HOST, DESKTOP_API_PORT)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(1)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
    if stream
        .write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.contains("\"status\":\"ok\"")
}

fn wait_for_runtime(timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if runtime_ready() {
            return true;
        }
        thread::sleep(Duration::from_millis(250));
    }
    false
}

fn kill_runtime(app: &tauri::AppHandle) {
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

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(RuntimeState::default())
        .setup(|app| {
            let child = spawn_runtime(app)?;
            if let Some(state) = app.try_state::<RuntimeState>() {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(child);
                }
            }

            // A cold, signed PyInstaller sidecar can spend more than 20s
            // loading pandas/scipy on macOS before Uvicorn binds its port.
            // Keep the window hidden while it boots, but do not abort a
            // healthy first launch merely because subsequent warm launches
            // are much faster.
            if !wait_for_runtime(Duration::from_secs(60)) {
                kill_runtime(&app.handle());
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Questboard desktop runtime did not become ready within 60 seconds.",
                )
                .into());
            }

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }

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
