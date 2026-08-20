use std::{
    env, fs,
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::{anyhow, Context, Result};

pub const TASK_NAME: &str = "WorkPulseChecker-Keepalive";

fn escape_xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// 環境変数から得たドメインとユーザー名を `DOMAIN\user` 形式にまとめる。
/// ドメインが無いローカルアカウントではユーザー名だけを使う。
pub fn format_user_id(domain: Option<&str>, user: &str) -> String {
    match domain {
        Some(domain) if !domain.is_empty() => format!("{domain}\\{user}"),
        _ => user.to_string(),
    }
}

/// `schtasks /Create /XML` に渡すタスク定義。
/// LogonTrigger に Duration 無しの Repetition を持たせることで、
/// 「ログオン時に起動」と「5分ごとの生存確認」を1トリガーで兼ねる。
pub fn build_task_xml(exe_path: &str, user_id: &str) -> String {
    let exe_path = escape_xml(exe_path);
    let user_id = escape_xml(user_id);

    format!(
        r#"<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Work Pulse Checker keepalive</Description>
    <URI>\{TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user_id}</UserId>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{exe_path}</Command>
    </Exec>
  </Actions>
</Task>
"#
    )
}

/// コンソールウィンドウを出さずに子プロセスを起動するためのフラグ。
/// 付けないと起動のたびに黒い窓が一瞬光る。
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const LEGACY_RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
const LEGACY_RUN_VALUE: &str = "Work Pulse Checker";

fn quiet_command(program: &str) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

fn current_user_id() -> Result<String> {
    let user = env::var("USERNAME").context("USERNAME is not set")?;
    let domain = env::var("USERDOMAIN").ok();
    Ok(format_user_id(domain.as_deref(), &user))
}

fn temp_xml_path() -> PathBuf {
    env::temp_dir().join(format!("{TASK_NAME}-{}.xml", std::process::id()))
}

/// schtasks /XML は UTF-8 のファイルを読めない環境があるため UTF-16LE + BOM で書く。
fn write_utf16le_with_bom(path: &Path, content: &str) -> Result<()> {
    let mut bytes = vec![0xFF, 0xFE];
    for unit in content.encode_utf16() {
        bytes.extend_from_slice(&unit.to_le_bytes());
    }
    fs::write(path, bytes)?;
    Ok(())
}

/// タスクを望ましい状態に一致させる。
pub fn reconcile(desired_enabled: bool) -> Result<()> {
    if desired_enabled {
        register()
    } else {
        unregister()
    }
}

/// 毎回 /F で上書き登録する。こうすることで exe パスが常に現在のパスへ追従し、
/// 旧レジストリ方式で起きていた「古いパスが固着して起動しない」状態を構造的に防ぐ。
fn register() -> Result<()> {
    let exe_path = env::current_exe().context("failed to resolve the current executable")?;
    let xml = build_task_xml(&exe_path.to_string_lossy(), &current_user_id()?);
    let xml_path = temp_xml_path();
    write_utf16le_with_bom(&xml_path, &xml)?;

    let status = quiet_command("schtasks")
        .args(["/Create", "/TN", TASK_NAME, "/XML"])
        .arg(&xml_path)
        .arg("/F")
        .status()
        .context("failed to run schtasks /Create");
    let _ = fs::remove_file(&xml_path);

    let status = status?;
    if !status.success() {
        return Err(anyhow!("schtasks /Create exited with {status}"));
    }

    Ok(())
}

/// 未登録なら schtasks は非ゼロで終わるが、登録されていない状態が望みなので成功扱いにする。
fn unregister() -> Result<()> {
    let _ = quiet_command("schtasks")
        .args(["/Delete", "/TN", TASK_NAME, "/F"])
        .status();
    Ok(())
}

/// tauri-plugin-autostart が残した旧レジストリ値を消す。
/// 値が無いときも reg は非ゼロで終わるため、結果を捨てることで冪等にする。
pub fn remove_legacy_run_key() {
    let _ = quiet_command("reg")
        .args(["delete", LEGACY_RUN_KEY, "/v", LEGACY_RUN_VALUE, "/f"])
        .status();
}

#[cfg(test)]
mod tests {
    use super::{build_task_xml, format_user_id};

    const EXE: &str = r"C:\Apps\work-pulse-checker.exe";
    const USER: &str = r"CONTOSO\taro";

    #[test]
    fn embeds_the_executable_path_and_the_user() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains(r"<Command>C:\Apps\work-pulse-checker.exe</Command>"));
        assert!(xml.contains(r"<UserId>CONTOSO\taro</UserId>"));
    }

    #[test]
    fn repeats_every_five_minutes_without_a_duration() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<Interval>PT5M</Interval>"));
        assert!(!xml.contains("<Duration>"));
    }

    #[test]
    fn never_expires_and_ignores_duplicate_launches() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>"));
        assert!(xml.contains("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"));
    }

    #[test]
    fn runs_without_elevation_using_an_interactive_token() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<LogonType>InteractiveToken</LogonType>"));
        assert!(xml.contains("<RunLevel>LeastPrivilege</RunLevel>"));
    }

    #[test]
    fn keeps_running_on_battery() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"));
        assert!(xml.contains("<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"));
    }

    #[test]
    fn escapes_xml_special_characters() {
        let xml = build_task_xml(r"C:\a & b\<x>.exe", r"CON&TOSO\taro");

        assert!(xml.contains(r"<Command>C:\a &amp; b\&lt;x&gt;.exe</Command>"));
        assert!(xml.contains(r"<UserId>CON&amp;TOSO\taro</UserId>"));
        assert!(!xml.contains("& b"));
    }

    #[test]
    fn qualifies_the_user_with_its_domain_when_present() {
        assert_eq!(format_user_id(Some("CONTOSO"), "taro"), r"CONTOSO\taro");
    }

    #[test]
    fn falls_back_to_the_bare_user_name() {
        assert_eq!(format_user_id(None, "taro"), "taro");
        assert_eq!(format_user_id(Some(""), "taro"), "taro");
    }

    #[test]
    fn writes_utf16le_with_a_byte_order_mark() {
        use super::write_utf16le_with_bom;
        use tempfile::tempdir;

        let dir = tempdir().unwrap();
        let path = dir.path().join("task.xml");

        write_utf16le_with_bom(&path, "A<").unwrap();

        assert_eq!(
            std::fs::read(&path).unwrap(),
            vec![0xFF, 0xFE, b'A', 0x00, b'<', 0x00]
        );
    }
}
