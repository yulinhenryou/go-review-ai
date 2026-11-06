//! Baseline: decoding, parsing, extracting and writing SGF (ROADMAP M1
//! acceptance 7).

use std::hint::black_box;

use criterion::{Criterion, Throughput, criterion_group, criterion_main};
use weiqi_core::sgf;

const KEJIE: &[u8] = include_bytes!("../../../testdata/sgf/kejie-2025-11-27.sgf");
const KEJIE_GBK: &[u8] = include_bytes!("../../../testdata/sgf/kejie-2025-11-27-gbk.sgf");

/// Copies of the Ke Jie game in one collection: about 1 MiB and 155,000 nodes.
const COPIES: usize = 128;

fn sgf(c: &mut Criterion) {
    let mut group = c.benchmark_group("sgf");

    group.throughput(Throughput::Bytes(KEJIE.len() as u64));
    group.bench_function("parse/kejie_utf8", |b| {
        b.iter(|| sgf::parse(black_box(KEJIE)).unwrap());
    });
    group.throughput(Throughput::Bytes(KEJIE_GBK.len() as u64));
    group.bench_function("parse/kejie_gbk_guessed", |b| {
        b.iter(|| sgf::parse(black_box(KEJIE_GBK)).unwrap());
    });

    let large = KEJIE.repeat(COPIES);
    let parsed = sgf::parse(&large).unwrap();
    assert_eq!(parsed.games.len(), COPIES);
    group.throughput(Throughput::Bytes(large.len() as u64));
    group.bench_function("parse/large_collection", |b| {
        b.iter(|| sgf::parse(black_box(&large)).unwrap());
    });

    let tree = &sgf::parse(KEJIE).unwrap().games[0];
    group.throughput(Throughput::Elements(tree.len() as u64));
    group.bench_function("extract/kejie", |b| {
        b.iter(|| sgf::extract(black_box(tree)).unwrap());
    });
    group.bench_function("write/kejie", |b| {
        b.iter(|| black_box(tree).to_sgf());
    });
    group.finish();
}

criterion_group!(benches, sgf);
criterion_main!(benches);
