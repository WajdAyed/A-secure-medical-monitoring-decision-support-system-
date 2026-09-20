mod range;

use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    value: u64,
    min: u64,
    max: u64,
}

#[derive(Serialize)]
struct Output {
    verified: bool,
    status: String,
    proof_type: String,
    prove_ms: f64,
    verify_ms: f64,
    proof_size_bytes: usize,
}

fn main() {

    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();

    let req: Input = serde_json::from_str(&input).unwrap();

    let in_range = req.min <= req.max && req.value >= req.min && req.value <= req.max;
    let (verified, prove_us, verify_us, proof_size_bytes) = range::prove_range(req.value, req.min, req.max);

    let status = if !in_range {
        "ALERT"
    } else if !verified {
        "PROOF_FAILED"
    } else {
        "NORMAL"
    };

    let response = Output {
        verified,
        status: status.to_string(),
        proof_type: "Bulletproofs".to_string(),
        prove_ms: prove_us as f64 / 1000.0,
        verify_ms: verify_us as f64 / 1000.0,
        proof_size_bytes,
    };

    println!("{}", serde_json::to_string(&response).unwrap());

}
