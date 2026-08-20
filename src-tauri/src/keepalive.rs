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
}
