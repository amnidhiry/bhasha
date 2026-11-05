import assert from "node:assert/strict";
import { test } from "node:test";
import { diff } from "../src/diff.ts";

test("marks deletions and insertions", () => {
  assert.deepEqual(diff("我在银行工作了。", "我在银行工作。"), [
    { kind: "same", text: "我在银行工作" }, { kind: "del", text: "了" }, { kind: "same", text: "。" }]);
  assert.deepEqual(diff("我昨天去朋友家。", "我昨天去了朋友家。"), [
    { kind: "same", text: "我昨天去" }, { kind: "ins", text: "了" }, { kind: "same", text: "朋友家。" }]);
});

test("replacement is a deletion then an insertion", () => {
  assert.deepEqual(diff("一本人", "一个人"), [
    { kind: "same", text: "一" }, { kind: "del", text: "本" }, { kind: "ins", text: "个" }, { kind: "same", text: "人" }]);
});
