use std::{env, path::PathBuf, process::Command};

fn main() {
    tauri_build::build();

    if env::var("CARGO_CFG_TARGET_ENV").as_deref() != Ok("gnu") {
        return;
    }

    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR was not set"));
    let resource_rc = out_dir.join("resource.rc");
    let resource_lib = out_dir.join("resource.lib");

    if !resource_rc.exists() {
        return;
    }

    let target = match env::var("CARGO_CFG_TARGET_ARCH").as_deref() {
        Ok("x86_64") => "pe-x86-64",
        Ok("x86") => "pe-i386",
        Ok("aarch64") => "pe-aarch64-little",
        _ => return,
    };

    let status = Command::new("windres")
        .arg(format!("--input={}", resource_rc.display()))
        .arg("--output-format=coff")
        .arg(format!("--target={target}"))
        .arg("--codepage=65001")
        .arg(format!("--output={}", resource_lib.display()))
        .arg(format!("--include-dir={}", out_dir.display()))
        .status()
        .expect("failed to execute windres for GNU resource compilation");

    if !status.success() {
        panic!("windres failed to rebuild resource.lib for GNU target");
    }
}
