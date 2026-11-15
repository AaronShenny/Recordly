//! Release priority is authenticated separately from the installer. Neither a
//! modified feed nor a local cache can turn arbitrary metadata into policy.
use base64::{engine::general_purpose::STANDARD, Engine};
use minisign_verify::{PublicKey, Signature};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const SUPPORT: &str = "extapano@gmail.com";
pub const MAX_ATTEMPTS: u8 = 3;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ReleasePolicy {
    pub schema_version: u8,
    pub version: String,
    pub priority: String,
    pub installer_url: String,
    pub installer_signature: String,
}

pub fn repository(feed: &str) -> Result<&str, String> {
    let repo = feed.strip_prefix("https://github.com/")
        .and_then(|s| s.strip_suffix("/releases/latest/download/latest.json"))
        .ok_or("Updates must use the configured GitHub Releases feed.")?;
    let parts: Vec<_> = repo.split('/').collect();
    if parts.len() != 2 || parts.iter().any(|p| p.is_empty() || *p == "." || *p == ".." ||
        !p.bytes().all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))) {
        return Err("Invalid GitHub Releases repository.".into());
    }
    Ok(repo)
}

fn version_parts(version: &str) -> Result<(u64, u64, u64), String> {
    let fields: Vec<_> = version.split('.').collect();
    if fields.len() != 3 || fields.iter().any(|s| s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) ||
        (s.len() > 1 && s.starts_with('0'))) { return Err("Invalid stable release version.".into()); }
    Ok((fields[0].parse().map_err(|_| "Invalid version.")?,
        fields[1].parse().map_err(|_| "Invalid version.")?,
        fields[2].parse().map_err(|_| "Invalid version.")?))
}

pub fn newer(version: &str, installed: &str) -> bool {
    match (version_parts(version), version_parts(installed)) { (Ok(a), Ok(b)) => a > b, _ => false }
}

/// Only application-owned installers at/below the RUNNING version are obsolete.
/// Retain staged newer versions; never touch workspaces or unrecognized files.
pub fn prune_cache(cache: &std::path::Path, installed: &str) {
    let Ok(current) = version_parts(installed) else { return; };
    let Ok(entries) = std::fs::read_dir(cache) else { return; };
    for entry in entries.take(64).flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        let obsolete = name.strip_prefix("Recordly-").and_then(|s| s.strip_suffix("-verified.exe"))
            .and_then(|s| version_parts(s).ok()).is_some_and(|v| v <= current);
        if (obsolete || name == "download.part") && entry.file_type().is_ok_and(|t| t.is_file()) {
            // Windows can still hold an old installer open. Retry next check;
            // failed nonessential cleanup must not block student work.
            let _ = std::fs::remove_file(entry.path());
        }
    }
}

pub fn installer_url(repo: &str, version: &str, url: &str) -> Result<(), String> {
    version_parts(version)?;
    if !["update", "setup"].iter().any(|kind|
        url == format!("https://github.com/{repo}/releases/download/v{version}/Recordly-{version}-x64-{kind}.exe")) {
        return Err("The update installer must belong to this version in the configured GitHub repository.".into());
    }
    Ok(())
}

pub fn verify_bytes(bytes: &[u8], public_key: &str, signature: &str, version: &str) -> Result<(), String> {
    let decode_text = |value: &str| -> Result<String, String> {
        if value.len() > 16_384 { return Err("Signing data is too large.".into()); }
        String::from_utf8(STANDARD.decode(value.trim()).map_err(|_| "Invalid signing data.")?)
            .map_err(|_| "Invalid signing data.".into())
    };
    let key = PublicKey::decode(&decode_text(public_key)?).map_err(|_| "Invalid update public key.")?;
    let decoded = decode_text(signature)?;
    let bound = decoded.lines().find_map(|s| s.strip_prefix("trusted comment: "))
        .and_then(|s| s.split('\t').find_map(|field| field.strip_prefix("version:")));
    if bound != Some(version) { return Err("Update signature version mismatch.".into()); }
    let sig = Signature::decode(&decoded).map_err(|_| "Invalid update signature.")?;
    key.verify(bytes, &sig, false).map_err(|_| "Update signature verification failed.".into())
}

pub fn signed_policy(envelope: &Value, public_key: &str, repo: &str) -> Result<ReleasePolicy, String> {
    let payload = envelope["payload"].as_str().filter(|s| s.len() <= 48_000).ok_or("Invalid update priority payload.")?;
    let bytes = STANDARD.decode(payload).map_err(|_| "Invalid update priority encoding.")?;
    let policy: ReleasePolicy = serde_json::from_slice(&bytes).map_err(|_| "Invalid update priority policy.")?;
    if policy.schema_version != 1 || !["normal", "high"].contains(&policy.priority.as_str()) {
        return Err("Unsupported update priority policy.".into());
    }
    installer_url(repo, &policy.version, &policy.installer_url)?;
    verify_bytes(&bytes, public_key, envelope["signature"].as_str().ok_or("Missing priority signature.")?, &policy.version)?;
    Ok(policy)
}

pub fn priority(raw: &Value, public_key: &str, repo: &str, version: &str, url: &str, signature: &str) -> Result<String, String> {
    installer_url(repo, version, url)?;
    // Legacy signed releases remain installable, but unsigned priority metadata
    // must never promote them to a startup-blocking update.
    let Some(envelope) = raw.get("recordly") else { return Ok("normal".into()); };
    let policy = signed_policy(envelope, public_key, repo)?;
    if policy.version != version || policy.installer_url != url || policy.installer_signature != signature {
        return Err("Update priority did not match the announced installer.".into());
    }
    Ok(policy.priority)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_github_release_feeds_and_same_repository_version_assets_are_accepted() {
        assert_eq!(repository("https://github.com/owner/Recordly/releases/latest/download/latest.json").unwrap(), "owner/Recordly");
        for feed in ["http://github.com/o/r/releases/latest/download/latest.json", "https://github.com.evil/o/r/releases/latest/download/latest.json",
            "https://github.com/o/../releases/latest/download/latest.json", "https://user@github.com/o/r/releases/latest/download/latest.json",
            "https://github.com/o/r/actions/artifacts/12"] { assert!(repository(feed).is_err()); }
        assert!(installer_url("o/r", "0.3.1", "https://github.com/o/r/releases/download/v0.3.1/Recordly-0.3.1-x64-update.exe").is_ok());
        for url in ["https://evil/a.exe", "https://github.com/other/r/releases/download/v0.3.1/Recordly-0.3.1-x64-update.exe",
            "https://github.com/o/r/releases/download/v0.3.0/Recordly-0.3.1-x64-update.exe"] {
            assert!(installer_url("o/r", "0.3.1", url).is_err());
        }
    }
    #[test]
    fn versions_are_numeric_and_never_downgraded() {
        assert!(newer("0.3.10", "0.3.9"));
        for v in ["0.3.9", "0.3.8", "0.03.10", "0.4.0-beta", "../4.0"] { assert!(!newer(v, "0.3.9")); }
    }
    #[test]
    fn cache_cleanup_retains_staged_updates_and_all_unrecognized_or_student_files() {
        let root = std::env::temp_dir().join(format!("recordly-cache-test-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&root).unwrap();
        for name in ["Recordly-0.3.0-verified.exe", "Recordly-0.4.0-verified.exe",
            "Recordly-0.4.1-verified.exe", "student.docx", "download.part"] {
            std::fs::write(root.join(name), b"fixture").unwrap();
        }
        prune_cache(&root, "0.4.0");
        assert!(!root.join("Recordly-0.3.0-verified.exe").exists());
        assert!(!root.join("Recordly-0.4.0-verified.exe").exists());
        assert!(!root.join("download.part").exists());
        assert!(root.join("Recordly-0.4.1-verified.exe").exists());
        assert!(root.join("student.docx").exists());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn malformed_priority_and_keys_are_not_trusted() {
        assert!(signed_policy(&serde_json::json!({"payload":"invalid","signature":"invalid"}), "invalid", "o/r").is_err());
        assert!(verify_bytes(b"anything", "invalid", "invalid", "0.3.1").is_err());
        assert!(signed_policy(&serde_json::json!({"payload":"x".repeat(48_001),"signature":""}), "", "o/r").is_err());
    }
    #[test]
    fn signed_policy_and_installer_are_cross_verified_and_tampering_is_rejected() {
        let fixture: Value = serde_json::from_str(include_str!("../tests/fixtures/update-policy.json")).unwrap();
        let key = fixture["key"].as_str().unwrap();
        let envelope = &fixture["recordly"];
        let policy = signed_policy(envelope, key, "fixture/Recordly").unwrap();
        assert_eq!(policy.priority, "high");
        assert_eq!(priority(&serde_json::json!({"recordly":envelope}), key, "fixture/Recordly",
            &policy.version, &policy.installer_url, &policy.installer_signature).unwrap(), "high");
        assert!(verify_bytes(fixture["installer"].as_str().unwrap().as_bytes(), key, &policy.installer_signature, "0.4.0").is_ok());
        assert!(verify_bytes(b"modified installer", key, &policy.installer_signature, "0.4.0").is_err());
        assert!(verify_bytes(fixture["installer"].as_str().unwrap().as_bytes(), key, &policy.installer_signature, "0.4.1").is_err());
        assert!(signed_policy(envelope, key, "different/repository").is_err());
        assert!(priority(&serde_json::json!({"recordly":envelope}), key, "fixture/Recordly",
            &policy.version, &policy.installer_url, "swapped signature").is_err());
        let mut modified = policy.clone();
        modified.priority = "normal".into();
        let mut tampered = envelope.clone();
        tampered["payload"] = Value::String(STANDARD.encode(serde_json::to_vec(&modified).unwrap()));
        assert!(signed_policy(&tampered, key, "fixture/Recordly").is_err());
    }
}
