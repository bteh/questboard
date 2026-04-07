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

const DESKTOP_API_HOST: &str = "127.0.0.1";
const DESKTOP_API_PORT: u16 = 8765;

#[derive(Default)]
struct RuntimeState(Mutex<Option<Child>>);

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

    if let Some(explicit_runtime) = env::var_os("LAUNCHBOARD_DESKTOP_RUNTIME") {
        let mut command = Command::new(explicit_runtime);
        command
            .args(&runtime_args)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        return Ok(command.spawn()?);
    }

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
        return Ok(command.spawn()?);
    }

    let resource_dir = app.path().resource_dir()?;
    let packaged_runtime_candidates = [
        resource_dir.join("sidecars").join("launchboard-runtime"),
        resource_dir
            .join("sidecars")
            .join("launchboard-runtime.exe"),
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
        return Ok(command.spawn()?);
    }

    Err(io::Error::new(
        io::ErrorKind::NotFound,
        "Launchboard desktop runtime not found. For development, run `make setup` first. For packaged builds, bundle a `launchboard-runtime` sidecar or set LAUNCHBOARD_DESKTOP_RUNTIME.",
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
                let _ = child.kill();
                let _ = child.wait();
            }
            *child = None;
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .manage(RuntimeState::default())
        .setup(|app| {
            let child = spawn_runtime(app)?;
            if let Some(state) = app.try_state::<RuntimeState>() {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(child);
                }
            }

            if !wait_for_runtime(Duration::from_secs(20)) {
                kill_runtime(&app.handle());
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "Launchboard desktop runtime did not become ready within 20 seconds.",
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
        .expect("error while building Launchboard desktop");

    app.run(|app, event| match event {
        RunEvent::Exit | RunEvent::ExitRequested { .. } => {
            kill_runtime(app);
        }
        _ => {}
    });
}
