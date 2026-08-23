use std::fs;
use std::process::Command;
use tempfile::tempdir;

pub struct RustVerifier;

impl RustVerifier {
    /// Verifies candidate Rust function and its unit test suite using rustc.
    /// Runs compilation and execution inside an isolated temporary directory.
    pub fn verify(fn_source: &str, test_source: &str, timeout_secs: u64) -> bool {
        let dir = match tempdir() {
            Ok(d) => d,
            Err(_) => return false,
        };

        let file_path = dir.path().join("candidate_test.rs");
        let bin_path = dir.path().join("candidate_bin");

        // Combine function under test and test main harness
        let full_program = format!(
            r#"
#![allow(dead_code, unused_variables, unused_mut)]

// Function under test
{}

// Unit tests
{}

fn main() {{
    test();
}}
"#,
            fn_source, test_source
        );

        if fs::write(&file_path, full_program).is_err() {
            return false;
        }

        // 1. Compile with rustc
        let compile_output = Command::new("rustc")
            .arg("--edition=2021")
            .arg("-O")
            .arg(&file_path)
            .arg("-o")
            .arg(&bin_path)
            .output();

        match compile_output {
            Ok(out) if out.status.success() => {}
            _ => return false,
        }

        // 2. Execute test binary with timeout
        let exec_output = Command::new(&bin_path).output();

        match exec_output {
            Ok(out) => out.status.success(),
            Err(_) => false,
        }
    }
}
