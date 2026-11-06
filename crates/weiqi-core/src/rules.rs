//! Rule sets and komi.
//!
//! [`Rules`] mirrors KataGo's rule components (`cpp/game/rules.h`) so that a
//! game maps one-to-one onto an engine query. Komi is kept separate, as in a
//! KataGo analysis query, where `komi` sits beside `rules`.

use crate::board::SuicideRule;

/// Which repetitions are forbidden.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum KoRule {
    /// Only the immediate recapture of a single-stone ko is forbidden; longer
    /// cycles are legal.
    Simple,
    /// A placement may not recreate any earlier arrangement of stones.
    Positional,
    /// A placement may not recreate an earlier arrangement with the same
    /// player to move.
    Situational,
}

/// How the final result is counted.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ScoringRule {
    /// Stones plus surrounded empty points (Chinese style).
    Area,
    /// Surrounded empty points plus prisoners (Japanese style).
    Territory,
}

/// Which points are excluded from the count (KataGo's tax rule).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum TaxRule {
    /// Nothing is excluded.
    None,
    /// Empty points in seki do not count.
    Seki,
    /// KataGo's `ALL`, used by its stone-scoring preset.
    All,
}

/// Compensation White receives per handicap stone under area scoring.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum WhiteHandicapBonus {
    /// None.
    Zero,
    /// One point per handicap stone.
    N,
    /// One point per handicap stone after the first.
    NMinusOne,
}

/// A complete rule set.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Rules {
    /// Repetition rule.
    pub ko: KoRule,
    /// Counting method.
    pub scoring: ScoringRule,
    /// Excluded points.
    pub tax: TaxRule,
    /// Whether multi-stone suicide is legal.
    pub suicide: SuicideRule,
    /// KataGo's `hasButton` (the AGA button variant).
    pub button: bool,
    /// Handicap compensation.
    pub white_handicap_bonus: WhiteHandicapBonus,
    /// KataGo's `friendlyPassOk` flag, carried unchanged so that a query
    /// matches the named preset.
    pub friendly_pass_ok: bool,
}

impl Rules {
    /// KataGo `japanese` (also `korean`).
    pub const fn japanese() -> Self {
        Self {
            ko: KoRule::Simple,
            scoring: ScoringRule::Territory,
            tax: TaxRule::Seki,
            suicide: SuicideRule::Forbidden,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::Zero,
            friendly_pass_ok: false,
        }
    }

    /// KataGo `korean`, identical to [`Rules::japanese`].
    pub const fn korean() -> Self {
        Self::japanese()
    }

    /// KataGo `chinese`: area scoring with simple ko.
    pub const fn chinese() -> Self {
        Self {
            ko: KoRule::Simple,
            scoring: ScoringRule::Area,
            tax: TaxRule::None,
            suicide: SuicideRule::Forbidden,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::N,
            friendly_pass_ok: true,
        }
    }

    /// KataGo `chinese-ogs` and `chinese-kgs`: Chinese with positional superko.
    pub const fn chinese_superko() -> Self {
        Self {
            ko: KoRule::Positional,
            ..Self::chinese()
        }
    }

    /// KataGo `aga` (also `bga`, `french`).
    pub const fn aga() -> Self {
        Self {
            ko: KoRule::Situational,
            scoring: ScoringRule::Area,
            tax: TaxRule::None,
            suicide: SuicideRule::Forbidden,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::NMinusOne,
            friendly_pass_ok: true,
        }
    }

    /// KataGo `aga-button`.
    pub const fn aga_button() -> Self {
        Self {
            button: true,
            ..Self::aga()
        }
    }

    /// KataGo `new-zealand`.
    pub const fn new_zealand() -> Self {
        Self {
            ko: KoRule::Situational,
            scoring: ScoringRule::Area,
            tax: TaxRule::None,
            suicide: SuicideRule::MultiStoneAllowed,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::Zero,
            friendly_pass_ok: true,
        }
    }

    /// KataGo `tromp-taylor`.
    pub const fn tromp_taylor() -> Self {
        Self {
            ko: KoRule::Positional,
            scoring: ScoringRule::Area,
            tax: TaxRule::None,
            suicide: SuicideRule::MultiStoneAllowed,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::Zero,
            friendly_pass_ok: false,
        }
    }

    /// KataGo `stone-scoring`.
    pub const fn stone_scoring() -> Self {
        Self {
            ko: KoRule::Simple,
            scoring: ScoringRule::Area,
            tax: TaxRule::All,
            suicide: SuicideRule::Forbidden,
            button: false,
            white_handicap_bonus: WhiteHandicapBonus::Zero,
            friendly_pass_ok: true,
        }
    }

    /// The preset for a KataGo shorthand name, including its aliases.
    pub fn from_name(name: &str) -> Option<Self> {
        let rules = match name.to_ascii_lowercase().as_str() {
            "japanese" | "korean" => Self::japanese(),
            "chinese" => Self::chinese(),
            "chinese-ogs" | "chinese_ogs" | "chineseogs" | "chinese-kgs" | "chinese_kgs"
            | "chinesekgs" => Self::chinese_superko(),
            "aga" | "bga" | "french" => Self::aga(),
            "aga-button" | "agabutton" | "aga_button" => Self::aga_button(),
            "new-zealand" | "nz" | "newzealand" => Self::new_zealand(),
            "tromp-taylor" | "tromp_taylor" | "tromptaylor" => Self::tromp_taylor(),
            "stone-scoring" | "stonescoring" | "stone_scoring" => Self::stone_scoring(),
            _ => return None,
        };
        Some(rules)
    }
}

/// Largest komi magnitude accepted, in points.
pub const MAX_KOMI: f64 = 150.0;

/// Komi in half-point steps within `-150..=150`, stored exactly as half points.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Komi {
    half_points: i16,
}

/// Komi that is not finite, not a multiple of 0.5, or out of range.
#[derive(Clone, Copy, Debug, PartialEq, thiserror::Error)]
#[error("komi {0} must be a finite multiple of 0.5 within -{MAX_KOMI}..={MAX_KOMI}")]
pub struct InvalidKomi(pub f64);

impl Komi {
    /// Validates `points`; ported from the prototype's `validate_komi` (MIGRATION G03).
    pub fn new(points: f64) -> Result<Self, InvalidKomi> {
        let doubled = points * 2.0;
        let valid = points.is_finite() && points.abs() <= MAX_KOMI && doubled.fract() == 0.0;
        // In range and integral, so the cast is exact.
        valid
            .then_some(Self {
                half_points: doubled as i16,
            })
            .ok_or(InvalidKomi(points))
    }

    /// Komi in points.
    pub fn points(self) -> f64 {
        f64::from(self.half_points) / 2.0
    }

    /// Komi in half points, exact.
    pub const fn half_points(self) -> i16 {
        self.half_points
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn presets_match_katago_rules_cpp() {
        let japanese = Rules::japanese();
        assert_eq!(japanese.ko, KoRule::Simple);
        assert_eq!(japanese.scoring, ScoringRule::Territory);
        assert_eq!(japanese.tax, TaxRule::Seki);
        assert!(!japanese.friendly_pass_ok);

        let chinese = Rules::chinese();
        assert_eq!(chinese.ko, KoRule::Simple);
        assert_eq!(chinese.white_handicap_bonus, WhiteHandicapBonus::N);
        assert_eq!(Rules::chinese_superko().ko, KoRule::Positional);

        assert_eq!(Rules::aga().ko, KoRule::Situational);
        assert_eq!(
            Rules::aga().white_handicap_bonus,
            WhiteHandicapBonus::NMinusOne
        );
        assert!(Rules::aga_button().button);
        assert_eq!(Rules::new_zealand().suicide, SuicideRule::MultiStoneAllowed);
        assert_eq!(Rules::tromp_taylor().ko, KoRule::Positional);
        assert!(!Rules::tromp_taylor().friendly_pass_ok);
        assert_eq!(Rules::stone_scoring().tax, TaxRule::All);
    }

    #[test]
    fn names_and_aliases_resolve() {
        assert_eq!(Rules::from_name("Korean"), Some(Rules::japanese()));
        assert_eq!(
            Rules::from_name("chinese_kgs"),
            Some(Rules::chinese_superko())
        );
        assert_eq!(Rules::from_name("nz"), Some(Rules::new_zealand()));
        assert_eq!(Rules::from_name("ing"), None);
    }

    /// Prototype `test_komi_validation_is_shared`; booleans and strings are
    /// excluded by the type system here.
    #[test]
    fn komi_validation_matches_the_prototype() {
        for value in [f64::NAN, f64::INFINITY, -151.0, 151.0, 0.25] {
            assert!(Komi::new(value).is_err(), "{value}");
        }
        for value in [-150.0, -0.5, 0.0, 6.5, 7.5, 150.0] {
            assert_eq!(Komi::new(value).map(Komi::points), Ok(value));
        }
        assert_eq!(Komi::new(6.5).map(Komi::half_points), Ok(13));
    }
}
