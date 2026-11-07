//! SGF parsing and replay as two pure functions. `replaySgf` parses the
//! bytes again instead of keeping a handle, so the caller never has to free
//! anything. The cost is small: natively, parsing an 8 KB, 111-move record
//! takes about 0.11 ms (`docs/acceptance/M1.md`, benchmarks).

use serde::Serialize;
use wasm_bindgen::prelude::*;
use weiqi::sgf::{self, Collection, GameInfo, GameRecord, RecordReplayError};

use crate::game::{PositionDto, RulesDto, SetupDto};
use crate::{
    ErrorClass, PlayedMove, coded, core_error, parse_komi, parse_rules, played_moves, to_js,
};

#[derive(Serialize)]
struct WarningDto {
    code: &'static str,
    offset: Option<usize>,
}

#[derive(Serialize)]
struct ExtractWarningDto {
    code: &'static str,
    node: Option<usize>,
}

#[derive(Serialize)]
struct ExtractFailureDto {
    code: &'static str,
    node: usize,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct GameInfoDto {
    black_player: Option<String>,
    white_player: Option<String>,
    black_rank: Option<String>,
    white_rank: Option<String>,
    date: Option<String>,
    event: Option<String>,
    round: Option<String>,
    place: Option<String>,
    name: Option<String>,
    result_text: Option<String>,
}

impl GameInfoDto {
    fn new(info: &GameInfo) -> Self {
        Self {
            black_player: info.black_player.clone(),
            white_player: info.white_player.clone(),
            black_rank: info.black_rank.clone(),
            white_rank: info.white_rank.clone(),
            date: info.date.clone(),
            event: info.event.clone(),
            round: info.round.clone(),
            place: info.place.clone(),
            name: info.name.clone(),
            result_text: info.result_text.clone(),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct GameRecordDto {
    width: u8,
    height: u8,
    rules: Option<RulesDto>,
    rules_text: Option<String>,
    komi: Option<f64>,
    handicap: Option<u32>,
    setup: SetupDto,
    moves: Vec<PlayedMove>,
    info: GameInfoDto,
    warnings: Vec<ExtractWarningDto>,
}

impl GameRecordDto {
    fn new(record: &GameRecord) -> Self {
        let size = record.size;
        Self {
            width: size.width(),
            height: size.height(),
            rules: record.rules.map(RulesDto::new),
            rules_text: record.rules_text.clone(),
            komi: record.komi.map(weiqi::Komi::points),
            handicap: record.handicap,
            setup: SetupDto::new(size, &record.setup),
            moves: played_moves(size, &record.moves),
            info: GameInfoDto::new(&record.info),
            warnings: record
                .warnings
                .iter()
                .map(|w| ExtractWarningDto {
                    code: w.code(),
                    node: w.node,
                })
                .collect(),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct SgfGameDto {
    record: Option<GameRecordDto>,
    extract_error: Option<ExtractFailureDto>,
}

#[derive(Serialize)]
struct SgfCollectionDto {
    encoding: &'static str,
    warnings: Vec<WarningDto>,
    games: Vec<SgfGameDto>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ReplayWarningDto {
    move_number: usize,
    code: &'static str,
}

#[derive(Serialize)]
struct ReplayDto {
    positions: Vec<PositionDto>,
    warnings: Vec<ReplayWarningDto>,
}

fn parse(data: &[u8]) -> Result<Collection, JsValue> {
    sgf::parse(data).map_err(|error| {
        coded(
            ErrorClass::Sgf,
            error.code(),
            &error,
            &[("offset", Some(error.offset))],
        )
    })
}

/// Parses SGF bytes in any supported encoding and extracts every game's main
/// line. Throws an `SgfError` when the bytes are not SGF.
#[wasm_bindgen(js_name = parseSgf, unchecked_return_type = "SgfCollection")]
pub fn parse_sgf(data: &[u8]) -> Result<JsValue, JsValue> {
    let collection = parse(data)?;
    let games = collection
        .games
        .iter()
        .map(|tree| match sgf::extract(tree) {
            Ok(record) => SgfGameDto {
                record: Some(GameRecordDto::new(&record)),
                extract_error: None,
            },
            Err(error) => SgfGameDto {
                record: None,
                extract_error: Some(ExtractFailureDto {
                    code: error.code(),
                    node: error.node,
                }),
            },
        })
        .collect();
    Ok(to_js(&SgfCollectionDto {
        encoding: collection.encoding,
        warnings: collection
            .warnings
            .iter()
            .map(|w| WarningDto {
                code: w.code(),
                offset: w.offset,
            })
            .collect(),
        games,
    }))
}

/// Replays game `game` (0-based) of the SGF bytes in "record" mode, with the
/// rules and komi a user confirmed.
#[wasm_bindgen(js_name = replaySgf, unchecked_return_type = "Replay")]
pub fn replay_sgf(data: &[u8], game: usize, rules: &str, komi: f64) -> Result<JsValue, JsValue> {
    let rules = parse_rules(rules)?;
    let komi = parse_komi(komi)?;
    let collection = parse(data)?;
    let tree = collection.games.get(game).ok_or_else(|| {
        core_error(
            "no_such_game",
            format!("game {game} of {}", collection.games.len()),
        )
    })?;
    let record = sgf::extract(tree).map_err(|error| {
        coded(
            ErrorClass::Extract,
            error.code(),
            &error,
            &[("node", Some(error.node))],
        )
    })?;
    let replay = record.replay(rules, komi).map_err(|error| {
        let move_number = match error {
            RecordReplayError::Replay(e) => Some(e.move_number),
            RecordReplayError::Setup(_) => None,
        };
        coded(
            ErrorClass::Replay,
            error.code(),
            error,
            &[("moveNumber", move_number)],
        )
    })?;
    Ok(to_js(&ReplayDto {
        positions: replay.positions.iter().map(PositionDto::new).collect(),
        warnings: replay
            .warnings
            .iter()
            .map(|w| ReplayWarningDto {
                move_number: w.move_number,
                code: w.kind.code(),
            })
            .collect(),
    }))
}
