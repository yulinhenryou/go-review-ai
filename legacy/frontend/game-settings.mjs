const PRESETS = { chinese: 7.5, japanese: 6.5 };

export function createGameSettings({ rulesInput, komiInput, customRulesInput, customRulesLabel }) {
  let customKomi = null;
  let customRulesConfirmed = false;

  function syncMode() {
    const custom = rulesInput.value === "custom";
    customRulesLabel.hidden = !custom;
    customRulesInput.disabled = !custom;
    komiInput.readOnly = !custom;
    if (!custom) {
      customRulesInput.value = rulesInput.value;
      komiInput.value = String(PRESETS[rulesInput.value]);
    }
  }

  rulesInput.addEventListener("change", () => {
    customRulesConfirmed = true;
    if (rulesInput.value === "custom" && customKomi !== null) {
      komiInput.value = customKomi;
    }
    syncMode();
  });
  customRulesInput.addEventListener("change", () => { customRulesConfirmed = true; });
  komiInput.addEventListener("input", () => {
    if (rulesInput.value === "custom") customKomi = komiInput.value;
  });

  function read(required) {
    const custom = rulesInput.value === "custom";
    const rules = custom ? customRulesInput.value : rulesInput.value;
    const komi = custom
      ? (komiInput.value === "" ? null : Number(komiInput.value))
      : PRESETS[rules];
    if (!(rules in PRESETS)) throw new Error("请选择计分规则。");
    if (!komiInput.checkValidity() || (komi !== null && (
      !Number.isFinite(komi) || komi < -150 || komi > 150 || !Number.isInteger(komi * 2)
    ))) throw new Error("贴目须为 -150 至 150 之间的整数或半目。");
    if (required && komi === null) throw new Error("请先填写自定义贴目。");
    // An untouched custom form must not supply an implicit rule for an SGF upload.
    return { rules: !required && custom && komi === null && !customRulesConfirmed ? null : rules, komi };
  }

  function apply(game) {
    const rules = game.rules;
    if (!(rules in PRESETS)) throw new Error("返回的计分规则不受支持。");
    const standard = game.komi === PRESETS[rules];
    rulesInput.value = standard ? rules : "custom";
    customRulesInput.value = rules;
    customRulesConfirmed = true;
    komiInput.value = game.komi == null ? "" : String(game.komi);
    if (!standard) customKomi = komiInput.value;
    syncMode();
  }

  syncMode();
  return { read, apply };
}
