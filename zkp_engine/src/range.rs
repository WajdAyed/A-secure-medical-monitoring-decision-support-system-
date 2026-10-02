use bulletproofs::{BulletproofGens, PedersenGens, RangeProof};
use curve25519_dalek_ng::{ristretto::CompressedRistretto, scalar::Scalar};
use merlin::Transcript;
use rand::thread_rng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha512};
use std::time::Instant;

const LABEL: &[u8] = b"Privacy-CDSS-bound-range-v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProofPackage {
    pub min: u64,
    pub max: u64,
    pub nonce: String,
    pub commitment: String,
    pub proof: String,
    pub commitments: [String; 2],
    pub binding_proof: BindingProof,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BindingProof {
    pub nonce: String,
    pub response: String,
}

fn challenge(min: u64, max: u64, request_nonce: &[u8; 32], commitments: &[CompressedRistretto; 2], nonce: &CompressedRistretto) -> Scalar {
    let mut h = Sha512::new();
    h.update(b"Privacy-CDSS-binding-v1");
    h.update(min.to_le_bytes());
    h.update(max.to_le_bytes());
    h.update(request_nonce);
    h.update(commitments[0].as_bytes());
    h.update(commitments[1].as_bytes());
    h.update(nonce.as_bytes());
    Scalar::from_bytes_mod_order_wide(&h.finalize().into())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.is_ascii() { return None; }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok()).collect()
}

fn bytes32(s: &str) -> Option<[u8; 32]> {
    unhex(s)?.try_into().ok()
}

pub fn prove_range(value: u64, min: u64, max: u64, request_nonce: &str) -> Result<(ProofPackage, u128), String> {
    if min > max || value < min || value > max {
        return Err("value outside public bounds".into());
    }
    let nonce_bytes = bytes32(request_nonce).ok_or("invalid request nonce")?;
    let pc = PedersenGens::default();
    let bp = BulletproofGens::new(64, 2);
    let blindings = [Scalar::random(&mut thread_rng()), Scalar::random(&mut thread_rng())];
    let witnesses = [value - min, max - value];
    let mut transcript = Transcript::new(LABEL);
    transcript.append_message(b"request_nonce", &nonce_bytes);
    transcript.append_u64(b"min", min);
    transcript.append_u64(b"max", max);
    let started = Instant::now();
    let (proof, commitments) = RangeProof::prove_multiple(
        &bp, &pc, &mut transcript, &witnesses, &blindings, 64,
    ).map_err(|e| e.to_string())?;
    let binding_random = Scalar::random(&mut thread_rng());
    let binding_nonce = (binding_random * pc.B_blinding).compress();
    let binding_challenge = challenge(min, max, &nonce_bytes, &[commitments[0], commitments[1]], &binding_nonce);
    let binding_response = binding_random + binding_challenge * (blindings[0] + blindings[1]);
    Ok((ProofPackage {
        min, max,
        nonce: request_nonce.to_owned(),
        commitment: hex(&(commitments[0].decompress().ok_or("invalid generated commitment")? + Scalar::from(min) * pc.B).compress().to_bytes()),
        proof: hex(&proof.to_bytes()),
        commitments: [hex(commitments[0].as_bytes()), hex(commitments[1].as_bytes())],
        binding_proof: BindingProof { nonce: hex(binding_nonce.as_bytes()), response: hex(&binding_response.to_bytes()) },
    }, started.elapsed().as_micros()))
}

pub fn verify_range(package: &ProofPackage, expected_nonce: &str) -> Result<u128, String> {
    if package.min > package.max { return Err("invalid bounds".into()); }
    let nonce_bytes = bytes32(expected_nonce).ok_or("invalid expected nonce")?;
    if package.nonce != expected_nonce { return Err("request nonce mismatch".into()); }
    if package.proof.len() > 16384 { return Err("proof too large".into()); }
    let proof = RangeProof::from_bytes(&unhex(&package.proof).ok_or("invalid proof hex")?)
        .map_err(|e| e.to_string())?;
    let commitments: Vec<CompressedRistretto> = package.commitments.iter()
        .map(|s| bytes32(s).map(CompressedRistretto).ok_or("invalid commitment"))
        .collect::<Result<_, _>>()?;
    let response = Scalar::from_canonical_bytes(bytes32(&package.binding_proof.response).ok_or("invalid binding response")?)
        .ok_or("noncanonical binding response")?;
    let nonce = CompressedRistretto(bytes32(&package.binding_proof.nonce).ok_or("invalid binding nonce")?);
    let nonce_point = nonce.decompress().ok_or("invalid binding nonce point")?;
    let c0 = commitments[0].decompress().ok_or("invalid first point")?;
    let c1 = commitments[1].decompress().ok_or("invalid second point")?;
    let pc = PedersenGens::default();
    let expected_commitment = (c0 + Scalar::from(package.min) * pc.B).compress();
    if bytes32(&package.commitment).ok_or("invalid reading commitment")? != *expected_commitment.as_bytes() {
        return Err("reading commitment mismatch".into());
    }
    let span = package.max - package.min;
    let difference = c0 + c1 - Scalar::from(span) * pc.B;
    let c = challenge(package.min, package.max, &nonce_bytes, &[commitments[0], commitments[1]], &nonce);
    if response * pc.B_blinding != nonce_point + c * difference {
        return Err("commitments are not bound to public bounds".into());
    }
    let bp = BulletproofGens::new(64, 2);
    let mut transcript = Transcript::new(LABEL);
    transcript.append_message(b"request_nonce", &nonce_bytes);
    transcript.append_u64(b"min", package.min);
    transcript.append_u64(b"max", package.max);
    let started = Instant::now();
    proof.verify_multiple(&bp, &pc, &mut transcript, &commitments, 64)
        .map_err(|e| e.to_string())?;
    Ok(started.elapsed().as_micros())
}

#[cfg(test)]
mod tests {
    use super::*;
    const NONCE: &str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    #[test]
    fn valid_and_tampered_packages() {
        let (mut p, _) = prove_range(120, 100, 140, NONCE).unwrap();
        assert!(verify_range(&p, NONCE).is_ok());
        assert!(verify_range(&p, "1123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef").is_err());
        p.commitment.replace_range(0..2, "ff");
        assert!(verify_range(&p, NONCE).is_err());
        let (mut p, _) = prove_range(120, 100, 140, NONCE).unwrap();
        p.max = 141;
        assert!(verify_range(&p, NONCE).is_err());
        p.max = 140;
        p.commitments.swap(0, 1);
        assert!(verify_range(&p, NONCE).is_err());
        p.commitments.swap(0, 1);
        p.binding_proof.response.replace_range(0..2, if &p.binding_proof.response[..2] == "00" { "01" } else { "00" });
        assert!(verify_range(&p, NONCE).is_err());
        let (mut p, _) = prove_range(120, 100, 140, NONCE).unwrap();
        p.proof.replace_range(0..2, if &p.proof[..2] == "00" { "01" } else { "00" });
        assert!(verify_range(&p, NONCE).is_err());
    }

    #[test]
    fn out_of_range_has_no_proof() {
        assert!(prove_range(99, 100, 140, NONCE).is_err());
    }
}
