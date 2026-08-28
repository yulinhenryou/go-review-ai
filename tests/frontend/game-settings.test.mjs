import assert from "node:assert/strict";
import test from "node:test";
import { createGameSettings } from "../../frontend/game-settings.mjs";

function field(value = "") {
  const listeners = {};
  return {
    value, readOnly: false, disabled: false, valid: true,
    addEventListener(type, listener) { listeners[type] = listener; },
    checkValidity() { return this.valid; },
    change(value) { this.value = value; listeners.change?.(); },
    input(value) { this.value = value; listeners.input?.(); }
  };
}

function setup() {
  const elements = {
    rulesInput: field("custom"), komiInput: field(),
    customRulesInput: field("chinese"), customRulesLabel: { hidden: false }
  };
  return { ...elements, settings: createGameSettings(elements) };
}

test("custom starts editable and does not invent missing SGF metadata", () => {
  const form = setup();
  assert.equal(form.komiInput.readOnly, false);
  assert.equal(form.customRulesLabel.hidden, false);
  assert.deepEqual(form.settings.read(false), { rules: null, komi: null });
  assert.throws(() => form.settings.read(true), /自定义贴目/);
});

test("Chinese and Japanese/Korean presets set and lock the correct komi", () => {
  const form = setup();
  for (const [rules, komi] of [["chinese", 7.5], ["japanese", 6.5], ["chinese", 7.5]]) {
    form.rulesInput.change(rules);
    assert.equal(form.komiInput.value, String(komi));
    assert.equal(form.komiInput.readOnly, true);
    assert.equal(form.customRulesLabel.hidden, true);
    assert.equal(form.customRulesInput.disabled, true);
    assert.deepEqual(form.settings.read(true), { rules, komi });
  }
});

test("explicit custom scoring can fill SGF rules while retaining its recorded komi", () => {
  const form = setup();
  form.customRulesInput.change("japanese");
  assert.deepEqual(form.settings.read(false), { rules: "japanese", komi: null });
  assert.throws(() => form.settings.read(true), /自定义贴目/);
});

test("switching to custom unlocks komi and retains an explicit scoring rule", () => {
  const form = setup();
  form.rulesInput.change("japanese");
  form.rulesInput.change("custom");
  assert.equal(form.komiInput.value, "6.5");
  assert.equal(form.komiInput.readOnly, false);
  assert.equal(form.customRulesInput.disabled, false);
  assert.equal(form.customRulesLabel.hidden, false);
  form.komiInput.input("5.5");
  assert.deepEqual(form.settings.read(true), { rules: "japanese", komi: 5.5 });
  form.customRulesInput.change("chinese");
  assert.deepEqual(form.settings.read(true), { rules: "chinese", komi: 5.5 });
});

test("custom komi survives a round trip through presets", () => {
  const form = setup();
  form.komiInput.input("0");
  form.rulesInput.change("chinese");
  form.rulesInput.change("custom");
  assert.equal(form.komiInput.value, "0");
  assert.deepEqual(form.settings.read(true), { rules: "chinese", komi: 0 });
});

test("SGF nonstandard komi is preserved as custom, not overwritten by defaults", () => {
  const form = setup();
  form.rulesInput.change("chinese");
  form.settings.apply({ rules: "japanese", komi: 5.5 });
  assert.equal(form.rulesInput.value, "custom");
  assert.equal(form.komiInput.readOnly, false);
  assert.deepEqual(form.settings.read(true), { rules: "japanese", komi: 5.5 });
  form.settings.apply({ rules: "chinese", komi: 0 });
  assert.deepEqual(form.settings.read(true), { rules: "chinese", komi: 0 });
});

test("SGF standard metadata selects its preset without triggering a user change", () => {
  const form = setup();
  for (const [rules, komi] of [["chinese", 7.5], ["japanese", 6.5]]) {
    form.settings.apply({ rules, komi });
    assert.equal(form.rulesInput.value, rules);
    assert.equal(form.komiInput.readOnly, true);
    assert.deepEqual(form.settings.read(true), { rules, komi });
  }
});

test("invalid custom komi is rejected before a request", () => {
  const form = setup();
  for (const value of ["NaN", "Infinity", "151", "-151", "6.25"]) {
    form.komiInput.input(value);
    assert.throws(() => form.settings.read(true), /整数或半目/);
  }
  form.komiInput.input("0");
  form.komiInput.valid = false;
  assert.throws(() => form.settings.read(true), /整数或半目/);
});
