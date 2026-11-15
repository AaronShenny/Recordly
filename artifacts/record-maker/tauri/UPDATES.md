# In-app updates from GitHub Releases

Recordly uses Tauri's updater. Student Drive storage is not an application-update
source. No production release is published automatically by this implementation.

## Student experience

- A native metadata check runs before the record screens, with a three-second
  network timeout. It does not start Node, Python, Word or Drive hydration.
- Normal releases download in the background after the desk opens. A notice
  offers **Install and restart**. Local drafts are flushed and Drive must
  acknowledge saved changes before the existing-account restart proceeds.
- High-priority releases download and verify before the record screens open.
  Startup shows progress and bounded retries, never an unexplained blank page.
  Existing accounts still use the same Drive-acknowledged restart path.
- A required update is **not a permanent lockout**. After failed attempts, show
  the error and `extapano@gmail.com`, then open the normal editable application.
  A failed download, invalid signature, offline connection or failed install
  never authorizes installation of unverified bytes or deletion of local work.
- Ordinary offline work stays available. The app cannot discover a new remote
  release while offline. A previously authenticated high-priority policy can
  trigger retries, but cannot prevent work indefinitely.
- While Recordly is open, background checks run every fifteen minutes, starting
  five seconds after the main screen reports readiness. There is no always-on
  background service or automatic download while the application is closed.

Download attempts are bounded: three tries, with two- and four-second retry
delays. High-priority downloads have a 90-second request timeout per attempt;
normal background downloads allow fifteen minutes. Windows publisher checking
has its own existing 30-second limit. These are upper bounds, not promises of
download speed; a high-priority update can exceed the ordinary startup target.
Completed cached installers are reused only after signature verification.
Partial files are never installed. Managed installers at or below the running
version are reclaimed so frequent updates do not accumulate large old packages.
Newer staged installers and all unrecognized files are retained.
Startup metadata retries apply only to a
previously authenticated high-priority update; ordinary unreachable feeds do
not add multiple sequential startup waits.

## Publishing a release

1. Commit the updater changes and choose a new stable version in `package.json`,
   Tauri configuration and Cargo. Create/protect the matching `vX.Y.Z` tag.
2. Configure the existing protected GitHub `recordly-release` environment:
   Google desktop registration, SignPath approval/configuration, the Tauri
   signing key/public key, approved Windows publisher names and licence review.
   Do not place private signing keys or Google credentials in source.
3. Run **Recordly signed release draft** for that tag and choose **normal** or
   **high** priority. These are the only accepted priority values.
4. The workflow signs the application/worker, then builds two NSIS installers:
   - `Recordly-X.Y.Z-x64-setup.exe`: full offline WebView2 first install/recovery.
   - `Recordly-X.Y.Z-x64-update.exe`: small WebView2 bootstrapper for upgrades.
     An existing compatible WebView2 runtime is retained; the bootstrapper can
     install it if missing, which requires internet.
   The SignPath installer artifact configuration must allow **both** filenames
   in the installer input artifact; do not silently leave one unsigned.
5. After Windows signing, the workflow signs the upgrade package and priority
   policy with the existing Tauri key, verifies both, and prepares a **draft**.
   Test the signed packages on Windows before approving publication.
6. Publish the approved GitHub Release with `latest.json`, its referenced
   upgrade installer, signatures, full offline installer and required source.
   Do not point clients at expiring/private GitHub Actions artifacts.

The feed is
`https://github.com/OWNER/REPOSITORY/releases/latest/download/latest.json`.
The installer must be the exact announced version under that same repository's
`releases/download/vX.Y.Z/` path. GitHub's asset/CDN HTTPS redirects are handled by
Tauri; arbitrary feed hosts, other repositories and artifact URLs are rejected.

## Authenticated priority and recovery

`latest.json` retains the standard Tauri fields for older clients. Its `recordly`
field adds a base64 payload and separate Tauri/minisign signature. The signed
payload binds schema version, app version, normal/high priority, installer URL
and installer signature. Changing just the unsigned JSON priority cannot create
a valid policy. Priority signatures and cached installer bytes are independently
checked using the pinned public key and authenticated version comment.

Both the package signature and approved Windows Authenticode publisher remain
required. The exact bytes handed to installation are reverified. The existing
Drive/account boundaries, instance lock, editable-draft guard and document-job
guard remain in place. The updater cache is separate from student workspaces.

Clients whose existing updater is disabled need one manual installation of an
updater-enabled build. Older enabled clients can receive it through their
existing updater, but cannot gain startup priority handling until that build is
installed. Keep the full installer as a repair path; do not assume automatic
rollback or that a package signature eliminates all Windows reputation prompts.

## Verification before a real rollout

Local checks cover policy/signature validation, GitHub path restrictions,
startup order, retry exhaustion, continued work after failure and Drive restart
guards. A Linux browser preview cannot install a Windows update.

On Windows, test two increasing signed versions, both installer variants,
normal/high updates, failed downloads, offline startup, invalid signatures,
pending Drive changes and the restart with real app data. Use a test repository
and test account before publishing a required release to students. No test
should overwrite a production release or use a production private signing key.
