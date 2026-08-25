use anyhow::{Context, Result};
use windows::{
    core::PWSTR,
    Win32::{
        Foundation::{CloseHandle, HWND, LPARAM, MAX_PATH, RECT, WPARAM},
        Graphics::Gdi::{
            GetMonitorInfoW, MonitorFromWindow, HMONITOR, MONITORINFO, MONITOR_DEFAULTTONEAREST,
        },
        System::Threading::{
            OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
            PROCESS_QUERY_LIMITED_INFORMATION,
        },
        UI::WindowsAndMessaging::{
            GetForegroundWindow, GetWindowRect, GetWindowThreadProcessId, IsWindowVisible,
            SendMessageTimeoutW, SMTO_ABORTIFHUNG, WM_GETTEXT, WM_GETTEXTLENGTH,
        },
    },
};

use crate::models::ActiveWindowInfo;

/// 応答しないウィンドウへ問い合わせても呼び出し元スレッドを道連れにしないための上限。
/// `GetWindowTextW` はドキュメント上「他プロセスのウィンドウなら送信しない」とされるが、
/// 実機ではサブクラス化されたウィンドウ等で内部的に `WM_GETTEXT` を送ってしまい
/// ハングすることが知られている。タイムアウト付きの `SendMessageTimeoutW` に
/// 置き換えることで、対象がハングしていてもサンプラースレッド自体は生き続ける。
const WINDOW_MESSAGE_TIMEOUT_MS: u32 = 300;

pub fn active_window() -> Result<Option<ActiveWindowInfo>> {
    let hwnd = unsafe { GetForegroundWindow() };
    if hwnd.0.is_null() || !unsafe { IsWindowVisible(hwnd) }.as_bool() {
        return Ok(None);
    }

    let title = read_window_title(hwnd)?;
    let process_name = read_process_name(hwnd)?;

    Ok(Some(ActiveWindowInfo {
        window_title: title,
        process_name,
        is_fullscreen: is_fullscreen_window(hwnd)?,
    }))
}

/// `SMTO_ABORTIFHUNG` 付きで `WM_GETTEXTLENGTH`/`WM_GETTEXT` を送る。
/// 対象ウィンドウが応答しない場合は `uTimeout` で打ち切られ 0 が返るため、
/// `GetForegroundWindow` が返した瞬間だけハングしているウィンドウを掴んでも
/// サンプラースレッドがブロックされたまま残ることはない。
fn read_window_title(hwnd: HWND) -> Result<String> {
    let length = send_message_timeout(hwnd, WM_GETTEXTLENGTH, WPARAM(0), LPARAM(0))?;
    if length <= 0 {
        return Ok(String::new());
    }

    let mut buffer = vec![0u16; length as usize + 1];
    let copied = send_message_timeout(
        hwnd,
        WM_GETTEXT,
        WPARAM(buffer.len()),
        LPARAM(buffer.as_mut_ptr() as isize),
    )?;
    let copied = (copied.max(0) as usize).min(buffer.len());

    Ok(String::from_utf16_lossy(&buffer[..copied])
        .trim()
        .to_string())
}

/// タイムアウト付きで `SendMessageTimeoutW` を呼び出し、失敗・タイムアウトを 0 として扱う。
fn send_message_timeout(hwnd: HWND, message: u32, wparam: WPARAM, lparam: LPARAM) -> Result<isize> {
    let mut result: usize = 0;
    let sent = unsafe {
        SendMessageTimeoutW(
            hwnd,
            message,
            wparam,
            lparam,
            SMTO_ABORTIFHUNG,
            WINDOW_MESSAGE_TIMEOUT_MS,
            Some(&mut result as *mut usize),
        )
    };

    if sent.0 == 0 {
        // 対象がハングしている、または既に破棄されている。タイトル取得を諦めるだけで、
        // 呼び出し元のサンプラーは正常に次のティックへ進める。
        return Ok(0);
    }

    Ok(result as isize)
}

fn read_process_name(hwnd: HWND) -> Result<String> {
    let mut process_id = 0u32;
    unsafe {
        GetWindowThreadProcessId(hwnd, Some(&mut process_id));
    }

    if process_id == 0 {
        return Ok("unknown".to_string());
    }

    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, process_id) }
        .with_context(|| "failed to open foreground process")?;

    let result = (|| {
        let mut capacity = MAX_PATH;
        let mut buffer = vec![0u16; capacity as usize];
        unsafe {
            QueryFullProcessImageNameW(
                handle,
                PROCESS_NAME_WIN32,
                PWSTR(buffer.as_mut_ptr()),
                &mut capacity,
            )
        }
        .with_context(|| "failed to read foreground process name")?;

        let full_path = String::from_utf16_lossy(&buffer[..capacity as usize]);
        Ok(full_path
            .rsplit('\\')
            .next()
            .unwrap_or("unknown")
            .to_string())
    })();

    unsafe {
        let _ = CloseHandle(handle);
    }

    result
}

fn is_fullscreen_window(hwnd: HWND) -> Result<bool> {
    let mut window_rect = RECT::default();
    unsafe { GetWindowRect(hwnd, &mut window_rect) }
        .with_context(|| "failed to read window rect")?;

    let monitor: HMONITOR = unsafe { MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) };
    let mut monitor_info = MONITORINFO {
        cbSize: std::mem::size_of::<MONITORINFO>() as u32,
        ..Default::default()
    };

    let monitor_info_ok =
        unsafe { GetMonitorInfoW(monitor, &mut monitor_info as *mut MONITORINFO as *mut _) };
    if !monitor_info_ok.as_bool() {
        anyhow::bail!("failed to read monitor info");
    }

    let monitor_rect = monitor_info.rcMonitor;
    Ok(close_enough(window_rect.left, monitor_rect.left)
        && close_enough(window_rect.top, monitor_rect.top)
        && close_enough(window_rect.right, monitor_rect.right)
        && close_enough(window_rect.bottom, monitor_rect.bottom))
}

fn close_enough(left: i32, right: i32) -> bool {
    (left - right).abs() <= 1
}
