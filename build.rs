use std::env;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=rust-toolchain.toml");
    let rustc = env::var_os("RUSTC").unwrap_or_else(|| "rustc".into());
    let version = Command::new(rustc)
        .arg("--version")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .and_then(|output| output.split_whitespace().nth(1).map(str::to_owned))
        .unwrap_or_else(|| "unknown".to_owned());
    println!("cargo:rustc-env=QPLANCK_RUST_VERSION={version}");
}
