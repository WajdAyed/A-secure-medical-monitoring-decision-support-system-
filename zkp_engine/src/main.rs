use serde::{Deserialize, Serialize};
use std::io::{self, Read};
use zkp_engine::range::{prove_range, verify_range, ProofPackage};

#[derive(Deserialize)]
#[serde(tag = "action", rename_all = "snake_case")]
enum Input {
    Prove { value: u64, min: u64, max: u64, nonce: String },
    Verify { package: ProofPackage, expected_nonce: String },
}

#[derive(Serialize)]
struct Output {
    verified: bool,
    status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    package: Option<ProofPackage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    elapsed_ms: f64,
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("stdin");
    let output = match serde_json::from_str::<Input>(&input) {
        Ok(Input::Prove { value, min, max, nonce }) => match prove_range(value, min, max, &nonce) {
            Ok((package, us)) => Output { verified: false, status: "PENDING_VERIFICATION", package: Some(package), error: None, elapsed_ms: us as f64 / 1000.0 },
            Err(error) => Output { verified: false, status: "ALERT", package: None, error: Some(error), elapsed_ms: 0.0 },
        },
        Ok(Input::Verify { package, expected_nonce }) => match verify_range(&package, &expected_nonce) {
            Ok(us) => Output { verified: true, status: "NORMAL", package: None, error: None, elapsed_ms: us as f64 / 1000.0 },
            Err(error) => Output { verified: false, status: "PROOF_FAILED", package: None, error: Some(error), elapsed_ms: 0.0 },
        },
        Err(error) => Output { verified: false, status: "PROOF_FAILED", package: None, error: Some(error.to_string()), elapsed_ms: 0.0 },
    };
    println!("{}", serde_json::to_string(&output).expect("json"));
}
