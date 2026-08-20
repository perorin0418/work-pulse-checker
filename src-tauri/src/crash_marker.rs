use std::{
    fs,
    io::ErrorKind,
    path::{Path, PathBuf},
};

use anyhow::Result;

const MARKER_FILE_NAME: &str = "running.marker";

/// 前回のプロセスが正常終了したかを、データディレクトリ内のマーカーファイルの
/// 残留有無で判定する。正常終了時だけ消す運用にすることで、残っていれば異常終了とわかる。
pub struct CrashMarker {
    path: PathBuf,
}

impl CrashMarker {
    pub fn new(data_dir: &Path) -> Self {
        Self {
            path: data_dir.join(MARKER_FILE_NAME),
        }
    }

    /// マーカーが残っていれば true を返し、いずれの場合もマーカーを張り直す。
    pub fn check_and_arm(&self, started_at: &str) -> Result<bool> {
        let was_unclean = self.path.exists();

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.path, started_at)?;

        Ok(was_unclean)
    }

    /// 正常終了時にマーカーを消す。既に無い場合も成功扱いにして冪等にする。
    pub fn disarm(&self) -> Result<()> {
        match fs::remove_file(&self.path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error.into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::CrashMarker;
    use tempfile::tempdir;

    #[test]
    fn reports_a_clean_start_when_no_marker_exists() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        assert!(!marker.check_and_arm("2026-08-20T09:00:00+09:00").unwrap());
    }

    #[test]
    fn reports_an_unclean_start_when_a_marker_is_left_behind() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        marker.check_and_arm("first").unwrap();

        assert!(marker.check_and_arm("second").unwrap());
    }

    #[test]
    fn disarm_makes_the_next_start_clean() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());
        marker.check_and_arm("first").unwrap();

        marker.disarm().unwrap();

        assert!(!marker.check_and_arm("second").unwrap());
    }

    #[test]
    fn disarm_succeeds_when_the_marker_is_already_gone() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        marker.disarm().unwrap();
    }
}
