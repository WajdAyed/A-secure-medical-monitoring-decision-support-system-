use bulletproofs::{BulletproofGens, PedersenGens, RangeProof};

use curve25519_dalek_ng::scalar::Scalar;

use merlin::Transcript;

use rand::thread_rng;
use std::time::Instant;

/// Prove the *clinical interval* min <= value <= max without revealing value.
/// The two committed witnesses are value-min and max-value; both must be
/// non-negative for their Bulletproof range proofs to verify.
pub fn prove_range(value: u64, min: u64, max: u64) -> (bool, u128, u128, usize) {
    if min > max || value < min || value > max {
        return (false, 0, 0, 0);
    }

    let pc_gens = PedersenGens::default();

    let bp_gens = BulletproofGens::new(64, 2);

    let blindings = [Scalar::random(&mut thread_rng()), Scalar::random(&mut thread_rng())];
    let witnesses = [value - min, max - value];

    let mut prover_transcript =
        Transcript::new(b"Privacy-CDSS");

    let prove_started = Instant::now();
    let (proof, commitments) =
        match RangeProof::prove_multiple(
            &bp_gens,
            &pc_gens,
            &mut prover_transcript,
            &witnesses,
            &blindings,
            64,
        ) {

            Ok(v) => v,

            Err(_) => return (false, prove_started.elapsed().as_micros(), 0, 0),
        };
    let prove_us = prove_started.elapsed().as_micros();
    let proof_size_bytes = proof.to_bytes().len();

    let mut verifier_transcript =
        Transcript::new(b"Privacy-CDSS");

    let verify_started = Instant::now();
    let verified = proof
        .verify_multiple(
            &bp_gens,
            &pc_gens,
            &mut verifier_transcript,
            &commitments,
            64,
        )
        .is_ok();
    (verified, prove_us, verify_started.elapsed().as_micros(), proof_size_bytes)
}
