use blake3::Hasher;

pub struct SimHash;

impl SimHash {
    /// Computes a 64-bit SimHash fingerprint from tokenized Rust source text
    pub fn compute(text: &str) -> u64 {
        let mut v = [0i32; 64];
        let normalized = text.to_lowercase();
        let tokens: Vec<&str> = normalized.split_whitespace().collect();

        if tokens.is_empty() {
            return 0;
        }

        for token in tokens {
            let mut hasher = Hasher::new();
            hasher.update(token.as_bytes());
            let hash_bytes = hasher.finalize();
            let hash_u64 = u64::from_le_bytes(hash_bytes.as_bytes()[0..8].try_into().unwrap());

            for i in 0..64 {
                if (hash_u64 & (1 << i)) != 0 {
                    v[i] += 1;
                } else {
                    v[i] -= 1;
                }
            }
        }

        let mut fingerprint: u64 = 0;
        for i in 0..64 {
            if v[i] > 0 {
                fingerprint |= 1 << i;
            }
        }
        fingerprint
    }

    /// Computes Hamming distance between two 64-bit fingerprints
    pub fn hamming_distance(a: u64, b: u64) -> u32 {
        (a ^ b).count_ones()
    }
}
