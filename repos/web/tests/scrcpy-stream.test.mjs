// 解码器纯函数单测：AnnexB 分割、avcc 转换、avcC 描述构建（用真实 scrcpy 流样例字节）
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// ScrcpyViewer 类引用浏览器全局，这里只提取纯函数部分执行
const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../src/media/scrcpyStream.js"), "utf8");
const functionBlock = source.slice(source.indexOf("function concatBytes"), source.indexOf("export class ScrcpyViewer"));
const pureModule = new Function(`${functionBlock}; return { concatBytes, splitAnnexB, firstNaluType, nalusToAvcc, buildAvcDescription };`)();

test("splitAnnexB 拆分 SPS/PPS/IDR（真实 scrcpy 字节）", () => {
  // 00 00 00 01 67(SPS) ... 00 00 00 01 68(PPS) ... 00 00 00 01 65(IDR)
  const payload = new Uint8Array([
    0, 0, 0, 1, 0x67, 1, 2, 3,
    0, 0, 0, 1, 0x68, 9, 9,
    0, 0, 0, 1, 0x65, 0xaa, 0xbb,
  ]);
  const nalus = pureModule.splitAnnexB(payload);
  assert.equal(nalus.length, 3);
  assert.equal(pureModule.firstNaluType(nalus[0]), 7);
  assert.equal(pureModule.firstNaluType(nalus[1]), 8);
  assert.equal(pureModule.firstNaluType(nalus[2]), 5);
  assert.deepEqual(Array.from(nalus[1]), [0x68, 9, 9]);
});

test("nalusToAvcc 输出 4 字节长度前缀格式", () => {
  const nalu = new Uint8Array([0x65, 1, 2, 3, 4]);
  const avcc = pureModule.nalusToAvcc([nalu]);
  assert.equal(avcc.length, 4 + 5);
  assert.deepEqual(Array.from(avcc.slice(0, 4)), [0, 0, 0, 5]);
  assert.equal(avcc[4], 0x65);
});

test("buildAvcDescription 生成合法 avcC 与 codec 字符串", () => {
  // SPS 头：67 + profile_idc=0x64 constraint=0x00 level=0x28
  const sps = new Uint8Array([0x67, 0x64, 0x00, 0x28, 0xd1, 0x00]);
  const pps = new Uint8Array([0x68, 0xee, 0x06, 0xf2]);
  const { description, codec } = pureModule.buildAvcDescription(sps, pps);
  assert.equal(codec, "avc1.640028");
  // 长度必须精确：尾部多余字节会让 Chromium 解不出任何帧（曾实测踩坑）
  assert.equal(description.length, 11 + sps.length + pps.length);
  assert.equal(description[0], 1);
  assert.equal(description[1], 0x64);
  assert.equal(description[2], 0x00);
  assert.equal(description[3], 0x28);
  // lengthSizeMinusOne = 3
  assert.equal(description[4] & 0x03, 3);
  assert.equal(description[5] & 0x1f, 1); // 1 个 SPS
  const spsLength = (description[6] << 8) | description[7];
  assert.equal(spsLength, sps.length);
  const ppsCount = description[8 + sps.length];
  assert.equal(ppsCount, 1);
});

test("concatBytes 拼接", () => {
  const out = pureModule.concatBytes([new Uint8Array([1, 2]), new Uint8Array([3])], 3);
  assert.deepEqual(Array.from(out), [1, 2, 3]);
});
