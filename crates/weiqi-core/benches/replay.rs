//! Baseline: replaying whole games (ROADMAP M1 acceptance 7).

use std::hint::black_box;

use criterion::{Criterion, criterion_group, criterion_main};
use weiqi_core::sgf;
use weiqi_core::{BoardSize, Color, Game, Komi, Move, ReplayMode, Rules};

/// A deterministic 300-move legal game on 19x19: a fixed-seed xorshift picks
/// points, and illegal picks are skipped. Random play, not a realistic game.
fn random_game(length: usize) -> Vec<(Color, Move)> {
    let size = BoardSize::square(19).unwrap();
    let points: Vec<_> = size.points().collect();
    let mut game = Game::new(size, Rules::chinese(), Komi::new(7.5).unwrap());
    let mut state: u64 = 0x9e37_79b9_7f4a_7c15;
    while game.move_count() < length {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let point = points[(state % points.len() as u64) as usize];
        let _ = game.play(Move::Play(point));
    }
    game.moves()
}

fn replay(c: &mut Criterion) {
    let size = BoardSize::square(19).unwrap();
    let komi = Komi::new(7.5).unwrap();

    let moves = random_game(300);
    c.bench_function("replay/random_300_moves", |b| {
        b.iter(|| {
            Game::new(size, Rules::chinese(), komi)
                .replay(black_box(&moves), ReplayMode::Strict)
                .unwrap()
        });
    });

    let bytes = include_bytes!("../../../testdata/sgf/maruyama-ito-1976.sgf");
    let record = sgf::extract(&sgf::parse(bytes).unwrap().games[0]).unwrap();
    assert_eq!(record.moves.len(), 235);
    c.bench_function("replay/maruyama_ito_235_moves", |b| {
        b.iter(|| black_box(&record).replay(Rules::japanese(), komi).unwrap());
    });
}

criterion_group!(benches, replay);
criterion_main!(benches);
