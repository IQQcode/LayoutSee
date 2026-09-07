// scrcpy H.264 实时流客户端：解析 Core 转发的帧记录，WebCodecs 解码并渲染到 canvas。
// 线格式：头 LSS1(4s)+width/height/fps(u32)，之后每帧 [pts u64][len u32][payload]（len=0 为心跳）。
const CONFIG_PTS = 0x8000000000000000n;
const STREAM_MAGIC = 0x4c535331;
const MAX_RECORD_BYTES = 4 * 1024 * 1024;
const HEADER_BYTES = 16;
const RECORD_HEAD_BYTES = 12;

function concatBytes(chunks, totalLength) {
  const out = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

// Annex-B 起始码分割（00 00 01 / 00 00 00 01），返回不含起始码的 NALU 列表
function splitAnnexB(payload) {
  const nalus = [];
  let start = -1;
  let index = 0;
  while (index <= payload.length - 3) {
    if (payload[index] === 0 && payload[index + 1] === 0 && payload[index + 2] === 1) {
      if (start >= 0) nalus.push(payload.subarray(start, index - (payload[index - 1] === 0 ? 1 : 0)));
      start = index + 3;
      index += 3;
    } else {
      index += 1;
    }
  }
  if (start >= 0 && start < payload.length) nalus.push(payload.subarray(start));
  return nalus.filter((nalu) => nalu.length > 0);
}

function firstNaluType(nalu) {
  return nalu.length ? nalu[0] & 0x1f : -1;
}

// Annex-B NALU → avcc 长度前缀格式
function nalusToAvcc(nalus) {
  let total = 0;
  for (const nalu of nalus) total += 4 + nalu.length;
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  let offset = 0;
  for (const nalu of nalus) {
    view.setUint32(offset, nalu.length);
    out.set(nalu, offset + 4);
    offset += 4 + nalu.length;
  }
  return out;
}

// SPS + PPS → avcC description（decoder configure 必需）；长度必须精确，尾部多余字节会让 Chromium 解不出任何帧
function buildAvcDescription(sps, pps) {
  const out = new Uint8Array(8 + sps.length + 3 + pps.length);
  const view = new DataView(out.buffer);
  out[0] = 1;
  out[1] = sps[1];
  out[2] = sps[2];
  out[3] = sps[3];
  out[4] = 0xfc | 3;
  out[5] = 0xe0 | 1;
  view.setUint16(6, sps.length);
  out.set(sps, 8);
  const ppsCountOffset = 8 + sps.length;
  out[ppsCountOffset] = 1;
  view.setUint16(ppsCountOffset + 1, pps.length);
  out.set(pps, ppsCountOffset + 3);
  const codec = `avc1.${[sps[1], sps[2], sps[3]].map((byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  return { description: out, codec };
}

export class ScrcpyViewer {
  constructor({ canvas, deviceId, onMeta, onStats, onError }) {
    this.canvas = canvas;
    this.deviceId = deviceId;
    this.onMeta = onMeta;
    this.onStats = onStats;
    this.onError = onError;
    this.context = canvas.getContext("2d");
    this.decoder = null;
    this.codecLabel = "";
    this.configKey = "";
    this.pendingConfig = null;
    this.sawKeyframe = false;
    this.awaitingKeyframe = true;
    this.frozen = false;
    this.stopped = false;
    this.stats = { frames: 0, dropped: 0, startedAt: 0 };
    this.renderHandle = 0;
    this.latestFrame = null;
    this.abort = new AbortController();
  }

  start() {
    this.stats.startedAt = performance.now();
    this.renderHandle = requestAnimationFrame(this.renderLoop);
    void this.pump();
  }

  stop() {
    this.stopped = true;
    cancelAnimationFrame(this.renderHandle);
    this.abort.abort();
    this.clearFrame();
    if (this.decoder) {
      try {
        this.decoder.close();
      } catch {
        // 解码器可能已处于 closed 状态
      }
      this.decoder = null;
    }
  }

  setFrozen(flag) {
    this.frozen = flag;
  }

  clearFrame() {
    if (this.latestFrame) {
      this.latestFrame.close();
      this.latestFrame = null;
    }
  }

  renderLoop = () => {
    if (this.stopped) return;
    if (this.latestFrame && !this.frozen) {
      const frame = this.latestFrame;
      this.latestFrame = null;
      if (this.canvas.width !== frame.displayWidth || this.canvas.height !== frame.displayHeight) {
        this.canvas.width = frame.displayWidth;
        this.canvas.height = frame.displayHeight;
      }
      this.context.drawImage(frame, 0, 0);
      frame.close();
    }
    this.renderHandle = requestAnimationFrame(this.renderLoop);
  };

  emitStats() {
    this.onStats?.({
      fps: Math.round((this.stats.frames / Math.max(0.5, (performance.now() - this.stats.startedAt) / 1000)) * 10) / 10,
      frames: this.stats.frames,
      dropped: this.stats.dropped,
      codec: this.codecLabel,
    });
  }

  async pump() {
    try {
      const response = await fetch(`/api/v1/devices/${encodeURIComponent(this.deviceId)}/media/stream`, {
        headers: { Accept: "application/octet-stream" },
        signal: this.abort.signal,
      });
      if (!response.ok || !response.body) throw new Error(`HTTP_${response.status}`);
      const reader = response.body.getReader();
      let buffer = new Uint8Array(0);
      let headerDone = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done || this.stopped) break;
        buffer = concatBytes([buffer, value], buffer.length + value.length);
        if (!headerDone) {
          if (buffer.length < HEADER_BYTES) continue;
          const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
          if (view.getUint32(0) !== STREAM_MAGIC) throw new Error("MEDIA_PROTOCOL");
          const width = view.getUint32(4);
          const height = view.getUint32(8);
          this.onMeta?.({ width, height, fps: view.getUint32(12) });
          buffer = buffer.subarray(HEADER_BYTES);
          headerDone = true;
        }
        let guard = 0;
        while (buffer.length >= RECORD_HEAD_BYTES && guard < 64) {
          const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
          const length = view.getUint32(8);
          if (length > MAX_RECORD_BYTES) throw new Error("MEDIA_RECORD");
          if (buffer.length < RECORD_HEAD_BYTES + length) break;
          const pts = view.getBigUint64(0);
          const payload = buffer.subarray(RECORD_HEAD_BYTES, RECORD_HEAD_BYTES + length);
          buffer = buffer.subarray(RECORD_HEAD_BYTES + length);
          guard += 1;
          if (length === 0 || this.frozen) continue; // 心跳或冻结期间不消费
          this.consumeRecord(pts, payload);
        }
      }
      if (!this.stopped) this.onError?.(new Error("MEDIA_STREAM_END"));
    } catch (error) {
      if (!this.stopped && error?.name !== "AbortError") this.onError?.(error);
    }
  }

  ensureDecoder(sps, pps) {
    const key = `${sps.length}:${pps.length}:${Array.from(sps.slice(0, 8)).join(",")}`;
    if (this.decoder && key === this.configKey) return;
    if (typeof VideoDecoder === "undefined") throw new Error("WEBCODECS_UNAVAILABLE");
    const { description, codec } = buildAvcDescription(sps, pps);
    if (this.decoder) {
      try {
        this.decoder.close();
      } catch {
        // 忽略旧解码器关闭异常（旋转重建场景）
      }
      this.sawKeyframe = false;
    }
    this.decoder = new VideoDecoder({
      output: (frame) => {
        this.clearFrame();
        this.latestFrame = frame;
        this.stats.frames += 1;
      },
      error: (error) => {
        // 解码器自愈：丢弃实例并等待下一个关键帧重建
        uiLogWarn(`解码器错误：${error?.message ?? error}`);
        try {
          this.decoder?.close();
        } catch {
          // already closed
        }
        this.decoder = null;
        this.configKey = "";
        this.awaitingKeyframe = true;
        this.onError?.(error);
      },
    });
    this.decoder.configure({ codec, description, optimizeForLatency: true });
    this.configKey = key;
    this.codecLabel = codec;
    this.awaitingKeyframe = true;
    this.emitStats();
  }

  consumeRecord(pts, payload) {
    try {
      const nalus = splitAnnexB(payload);
      if (nalus.length === 0) return;
      if (pts === CONFIG_PTS) {
        const sps = nalus.find((nalu) => firstNaluType(nalu) === 7);
        const pps = nalus.find((nalu) => firstNaluType(nalu) === 8);
        if (sps && pps) {
          this.pendingConfig = { sps: new Uint8Array(sps), pps: new Uint8Array(pps) };
          this.ensureDecoder(this.pendingConfig.sps, this.pendingConfig.pps);
        }
        return;
      }
      const hasSps = nalus.some((nalu) => firstNaluType(nalu) === 7);
      const hasPps = nalus.some((nalu) => firstNaluType(nalu) === 8);
      if (hasSps && hasPps) {
        const sps = new Uint8Array(nalus.find((nalu) => firstNaluType(nalu) === 7));
        const pps = new Uint8Array(nalus.find((nalu) => firstNaluType(nalu) === 8));
        this.ensureDecoder(sps, pps); // 旋转时 SPS 变化会自动重建解码器
      }
      if (!this.decoder) return;
      const dataNalus = nalus.filter((nalu) => ![7, 8, 9].includes(firstNaluType(nalu)));
      if (dataNalus.length === 0) return;
      const isKey = nalus.some((nalu) => firstNaluType(nalu) === 5);
      if (!this.sawKeyframe) {
        if (!isKey || this.decoder.state !== "configured") return;
        this.sawKeyframe = true;
        this.awaitingKeyframe = false;
      }
      if (this.decoder.decodeQueueSize > 8) {
        // 解码积压：丢帧并等到下一个关键帧再恢复，避免参考帧缺失导致的画面污染
        this.stats.dropped += 1;
        this.awaitingKeyframe = true;
        this.emitStats();
        return;
      }
      if (this.awaitingKeyframe) {
        if (!isKey) {
          this.stats.dropped += 1;
          return;
        }
        this.awaitingKeyframe = false;
      }
      // scrcpy pts 高位是 config/key 标志位，取低 48 位微秒做时间戳（也在 Number 安全整数内）
      const timestamp = Number(pts & 0xffffffffffffn);
      this.decoder.decode(new EncodedVideoChunk({
        type: isKey ? "key" : "delta",
        timestamp,
        data: nalusToAvcc(dataNalus),
      }));
    } catch {
      this.stats.dropped += 1;
    }
  }
}

function uiLogWarn(message) {
  console.warn(`[LayoutSee][投屏] ${message}`);
}
