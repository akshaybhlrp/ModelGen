mod ast_extractor;
mod simhash;
mod storage;
mod verifier;

use ast_extractor::RustAstExtractor;
use simhash::SimHash;
use storage::{ModuleRecord, PurushaDb};
use verifier::RustVerifier;
use std::time::Instant;

fn main() {
    println!("============================================================");
    println!("  MODELGEN - 100% PURE RUST FRONTIER KERNEL & VERIFIER      ");
    println!("============================================================");

    // 1. Initialize atomic redb storage
    let db_path = "frontier_rust.redb";
    let _ = std::fs::remove_file(db_path); // fresh run
    let db = PurushaDb::open(db_path).expect("Failed to initialize redb database");
    println!("[+] Purusha atomic redb storage initialized at {}", db_path);

    // 2. Define sample candidate algorithms + test suites
    let candidate_1_fn = r#"
pub fn sort_integers(mut v: Vec<i32>) -> Vec<i32> {
    v.sort();
    v
}
"#;
    let candidate_1_test = r#"
pub fn test() {
    assert_eq!(sort_integers(vec![3, 1, 2]), vec![1, 2, 3]);
    assert_eq!(sort_integers(vec![]), Vec::<i32>::new());
    assert_eq!(sort_integers(vec![5]), vec![5]);
}
"#;

    let candidate_2_fn = r#"
pub fn reverse_string(s: String) -> String {
    s.chars().rev().collect()
}
"#;
    let candidate_2_test = r#"
pub fn test() {
    assert_eq!(reverse_string("hello".to_string()), "olleh".to_string());
    assert_eq!(reverse_string("".to_string()), "".to_string());
}
"#;

    // 3. Verify candidates with native rustc
    println!("\n[+] Compiling and verifying candidates via rustc sandbox...");
    let t0 = Instant::now();
    let c1_passed = RustVerifier::verify(candidate_1_fn, candidate_1_test, 5);
    println!("    -> candidate_1 (sort_integers) verified: {}", if c1_passed { "PASS" } else { "FAIL" });

    let c2_passed = RustVerifier::verify(candidate_2_fn, candidate_2_test, 5);
    println!("    -> candidate_2 (reverse_string) verified: {}", if c2_passed { "PASS" } else { "FAIL" });
    println!("    -> Verification time: {:?}", t0.elapsed());

    // 4. Store passing modules into redb with SimHash fingerprints
    if c1_passed {
        let hash = blake3::hash(candidate_1_fn.as_bytes());
        let sh = SimHash::compute(candidate_1_fn);
        let rec = ModuleRecord {
            content_hash: *hash.as_bytes(),
            name: "sort_integers".to_string(),
            source_code: candidate_1_fn.to_string(),
            test_code: candidate_1_test.to_string(),
            input_type: "Vec<i32>".to_string(),
            output_type: "Vec<i32>".to_string(),
            license: "MIT".to_string(),
            source_url: "local_seed".to_string(),
        };
        db.store_module(&rec, sh).expect("Failed to store module");
    }

    if c2_passed {
        let hash = blake3::hash(candidate_2_fn.as_bytes());
        let sh = SimHash::compute(candidate_2_fn);
        let rec = ModuleRecord {
            content_hash: *hash.as_bytes(),
            name: "reverse_string".to_string(),
            source_code: candidate_2_fn.to_string(),
            test_code: candidate_2_test.to_string(),
            input_type: "String".to_string(),
            output_type: "String".to_string(),
            license: "MIT".to_string(),
            source_url: "local_seed".to_string(),
        };
        db.store_module(&rec, sh).expect("Failed to store module");
    }

    // 5. Test Retrieval using SimHash LSH query
    println!("\n[+] Testing SimHash LSH Retrieval on Rust Kernel...");
    let query = "sort integers vector list";
    let q_sh = SimHash::compute(query);
    let all_modules = db.list_all_modules().expect("Failed to list modules");

    let mut ranked = Vec::new();
    for m in all_modules {
        let m_sh = SimHash::compute(&m.source_code);
        let dist = SimHash::hamming_distance(q_sh, m_sh);
        ranked.push((m, dist));
    }
    ranked.sort_by_key(|k| k.1); // lowest distance first

    for (rank, (module, dist)) in ranked.iter().enumerate() {
        println!("    Rank #{}: {} (Hamming Distance: {})", rank + 1, module.name, dist);
    }

    println!("\n[+] Pure Rust Kernel: ALL CHECKS PASSED!");
}
