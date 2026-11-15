use serde::Deserialize;
use serde_json::{json, Value};
use std::{fs, path::Path, process::{Command, Stdio}, os::windows::process::CommandExt, time::Duration, sync::{Arc, Mutex}};
use tauri_plugin_updater::{Update, UpdaterExt};
use record_maker_native::update_policy::{self, MAX_ATTEMPTS, SUPPORT};

pub struct Updates {
    downloaded: Option<(Update, std::path::PathBuf)>,
    pending: Option<Update>,
    priority: String,
    public_key: String,
    progress: Arc<Mutex<Value>>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Configuration {
    feed: Option<String>,
    public_key: Option<String>,
    #[serde(default)]
    publisher_names: Vec<String>,
}
impl Updates {
    pub fn new(progress: Arc<Mutex<Value>>) -> Self {
        Self { downloaded: None, pending: None, priority: "normal".into(), public_key: String::new(), progress }
    }
    fn publish(&self, mut value: Value) -> Value {
        value["priority"] = json!(self.priority);
        if let Ok(mut progress) = self.progress.lock() { *progress = value.clone(); }
        value
    }
    pub fn failure(&self, message: &str) -> Value {
        self.publish(json!({"state":"error","message":format!("{message} You can continue working. If this keeps happening, contact {SUPPORT}."),
            "support":SUPPORT,"canContinue":true}))
    }
    fn configuration(resources: &Path) -> Result<Configuration, String> {
        let bytes = fs::read(resources.join("config/release-config.json")).map_err(|_| "Update configuration is missing.")?;
        serde_json::from_slice(&bytes).map_err(|_| "Update configuration is invalid.".into())
    }
    /// Metadata only. No Node, Drive hydration or Python is started here.
    pub fn prepare(&mut self, app: &tauri::AppHandle, resources: &Path, cache: &Path) -> Result<Value, String> {
        // Called under the updater/instance locks; no other download can own a
        // partial file. Frequent upgrades must not accumulate old installers.
        update_policy::prune_cache(cache, &app.package_info().version.to_string());
        if let Some((update, _)) = &self.downloaded {
            return Ok(self.publish(json!({"state":"downloaded","version":update.version,"message":"Update verified. Restart when your work is saved."})));
        }
        if let Some(update) = &self.pending {
            return Ok(self.publish(json!({"state":"available","version":update.version,"message":"A Recordly update is available."})));
        }
        let config = Self::configuration(resources)?;
        let Some(feed) = config.feed.as_deref().filter(|s| !s.is_empty()) else {
            return Ok(self.publish(json!({"state":"disabled","message":"Automatic updates are not configured for this build."})));
        };
        let repo = update_policy::repository(feed)?;
        let url = tauri::Url::parse(&feed).map_err(|_| "Invalid update feed.")?;
        if url.scheme() != "https" || !url.username().is_empty() || url.password().is_some() ||
            config.publisher_names.is_empty() || config.public_key.as_ref().is_none_or(|s| s.is_empty()) {
            return Err("Updates require HTTPS, a Tauri verification key and a Windows publisher policy.".into());
        }
        let public_key = config.public_key.as_deref().unwrap();
        self.public_key = public_key.to_owned();
        // Only authenticated, newer cached policy may retain startup urgency.
        if fs::metadata(cache.join("priority.json")).is_ok_and(|m| m.len() <= 64_000) {
            if let Ok(bytes) = fs::read(cache.join("priority.json")) {
                if let Ok(envelope) = serde_json::from_slice::<Value>(&bytes) {
                    if let Ok(policy) = update_policy::signed_policy(&envelope, public_key, repo) {
                        if update_policy::newer(&policy.version, &app.package_info().version.to_string()) { self.priority = policy.priority; }
                    }
                }
            }
        }
        self.publish(json!({"state":"checking","message":"Checking GitHub Releases…"}));
        let updater = app.updater_builder().pubkey(public_key).endpoints(vec![url])
            .map_err(|_| "Invalid update endpoint.")?.timeout(Duration::from_secs(3))
            .build().map_err(|_| "Could not initialize signed updates.")?;
        let update = tauri::async_runtime::block_on(updater.check()).map_err(|_| "Could not check for updates. Your current app is unchanged.")?;
        let Some(mut update) = update else {
            self.priority = "normal".into();
            return Ok(self.publish(json!({"state":"current","message":"You have the latest version."})));
        };
        self.priority = update_policy::priority(&update.raw_json, public_key, repo,
            &update.version, update.download_url.as_str(), &update.signature)?;
        if let Some(envelope) = update.raw_json.get("recordly") {
            fs::create_dir_all(cache).map_err(|_| "Could not save update metadata.")?;
            fs::write(cache.join("priority.json"), serde_json::to_vec(envelope).map_err(|_| "Invalid priority metadata.")?)
                .map_err(|_| "Could not save update metadata.")?;
        }
        update.timeout = Some(Duration::from_secs(if self.priority == "high" { 90 } else { 900 }));
        let version = update.version.clone();
        self.pending = Some(update);
        Ok(self.publish(json!({"state":"available","version":version,"message":"A Recordly update is available."})))
    }
    fn download_once(&mut self, resources: &Path, cache: &Path, attempt: u8) -> Result<Value, String> {
        let config = Self::configuration(resources)?;
        let update = self.pending.as_ref().ok_or("No update is available to download.")?;
        let public_key = config.public_key.as_deref().ok_or("Update verification is not configured.")?;
        fs::create_dir_all(cache).map_err(|_| "Could not cache the update.")?;
        let filename = cache.join(format!("Recordly-{}-verified.exe", update.version));
        let progress = self.progress.clone();
        let priority = self.priority.clone();
        let version = update.version.clone();
        self.publish(json!({"state":"downloading","version":version,"attempt":attempt,"maxAttempts":MAX_ATTEMPTS,
            "downloaded":0,"message":"Downloading the update from GitHub Releases…"}));
        let cached = fs::metadata(&filename).ok().filter(|m| m.len() <= 1024 * 1024 * 1024)
            .and_then(|_| fs::read(&filename).ok())
            .is_some_and(|bytes| update_policy::verify_bytes(&bytes, public_key, &update.signature, &update.version).is_ok());
        if !cached {
            let mut received = 0u64;
            let mut last_progress = std::time::Instant::now();
            let bytes = tauri::async_runtime::block_on(update.download(move |chunk, total| {
                received += chunk as u64;
                if last_progress.elapsed() < Duration::from_millis(200) { return; }
                last_progress = std::time::Instant::now();
                if let Ok(mut state) = progress.lock() {
                    *state = json!({"state":"downloading","priority":priority,"version":version,"attempt":attempt,
                        "maxAttempts":MAX_ATTEMPTS,"downloaded":received,"total":total,"message":"Downloading from GitHub Releases…"});
                }
            }, || {})).map_err(|_| "The download or its update signature could not be verified.")?;
            let staged = cache.join("download.part");
            fs::write(&staged, &bytes).map_err(|_| "Could not cache the update.")?;
            if filename.exists() { fs::remove_file(&filename).map_err(|_| "Could not replace an invalid cached update.")?; }
            fs::rename(staged, &filename).map_err(|_| "Could not finish caching the update.")?;
        }
        self.publish(json!({"state":"verifying","version":update.version,"attempt":attempt,
            "message":"Verifying the Windows publisher…"}));
        if !publisher_verified(&filename, &config.publisher_names)? {
            let _ = fs::remove_file(&filename);
            return Err("The Windows update signature or publisher did not match. Nothing was installed.".into());
        }
        self.downloaded = Some((self.pending.take().unwrap(), filename));
        Ok(self.publish(json!({"state":"downloaded","version":self.downloaded.as_ref().unwrap().0.version,
            "message":"Update downloaded and verified. Save your work, then install and restart."})))
    }
    pub fn check(&mut self, app: &tauri::AppHandle, resources: &Path, cache: &Path) -> Result<Value, String> {
        for attempt in 1..=MAX_ATTEMPTS {
            let result = self.prepare(app, resources, cache).and_then(|status| {
                if status["state"] == "available" { self.download_once(resources, cache, attempt) } else { Ok(status) }
            });
            match result {
                Ok(status) => return Ok(status),
                Err(_) if attempt < MAX_ATTEMPTS => {
                    self.publish(json!({"state":"retrying","attempt":attempt,"maxAttempts":MAX_ATTEMPTS,
                        "message":"The update was unavailable or could not be verified. Retrying…"}));
                    std::thread::sleep(Duration::from_secs(u64::from(attempt) * 2));
                }
                Err(_) => return Ok(self.failure("The update could not be downloaded and verified after three attempts.")),
            }
        }
        unreachable!()
    }
    pub fn install(&mut self) -> Result<Value, String> {
        let (update, file) = self.downloaded.take().ok_or("No verified update is downloaded.")?;
        self.publish(json!({"state":"installing","version":update.version,"message":"Installing the verified update. Recordly will restart…"}));
        let result = (|| {
            let bytes = fs::read(&file).map_err(|_| "The cached update is unavailable. Check for updates again.")?;
            // Independently recheck the EXACT bytes passed to the installer.
            // Do not rely on download-time verification or SDK implementation details.
            update_policy::verify_bytes(&bytes, &self.public_key, &update.signature, &update.version)?;
            update.install(bytes).map_err(|_| "The update could not be installed. Existing app files were preserved.")?;
            Ok(Value::Null)
        })();
        if result.is_err() {
            self.pending = Some(update);
            self.failure("Installation did not finish. No unverified package was installed.");
        }
        result
    }
}

fn publisher_verified(file: &Path, names: &[String]) -> Result<bool, String> {
    use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject, JobObjectExtendedLimitInformation,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
    if handle.is_null() { return Err("Could not supervise Windows signature verification.".into()); }
    let job = unsafe { OwnedHandle::from_raw_handle(handle) };
    let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if unsafe { SetInformationJobObject(job.as_raw_handle(), JobObjectExtendedLimitInformation,
        &limits as *const _ as *const _, std::mem::size_of_val(&limits) as u32) } == 0 {
        return Err("Could not supervise Windows signature verification.".into());
    }
    let windows = std::env::var_os("SystemRoot").ok_or("Windows signature verification is unavailable.")?;
    let executable = Path::new(&windows).join("System32/WindowsPowerShell/v1.0/powershell.exe");
    let script = "$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath $env:CRM_UPDATE_FILE; if($s.Status -ne 'Valid'){exit 2}; $n=$s.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false); $allowed=ConvertFrom-Json $env:CRM_UPDATE_PUBLISHERS; if($allowed -ccontains $n){exit 0}; exit 3";
    let mut child = Command::new(executable).args(["-NoProfile","-NonInteractive","-Command",script])
        .env("CRM_UPDATE_FILE", file).env("CRM_UPDATE_PUBLISHERS", serde_json::to_string(names).unwrap())
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).creation_flags(0x08000000)
        .spawn().map_err(|_| "Windows signature verification could not start.")?;
    if unsafe { AssignProcessToJobObject(job.as_raw_handle(), child.as_raw_handle()) } == 0 {
        let _ = child.kill(); let _ = child.wait();
        return Err("Could not supervise Windows signature verification.".into());
    }
    let start = std::time::Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|_| "Windows signature verification failed.")? { return Ok(status.success()); }
        if start.elapsed() > Duration::from_secs(30) { let _ = child.kill(); let _ = child.wait(); return Err("Windows signature verification timed out.".into()); }
        std::thread::sleep(Duration::from_millis(50));
    }
}
