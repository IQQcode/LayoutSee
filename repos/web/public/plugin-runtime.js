/**
 * LayoutSee 插件运行时（插件侧 SDK）。
 *
 * 插件页面用 <script src="/plugin-runtime.js"></script> 引入后可用全局 $u。
 * 插件文档是 opaque origin（sandbox 无 allow-same-origin），因此这里只能用 postMessage，
 * 且宿主消息的来源校验由宿主负责：插件侧只接受 event.source === window.parent 的回包。
 */
(function () {
  "use strict";

  var PROTOCOL_VERSION = 1;
  var DEFAULT_TIMEOUT_MS = 10000;
  var pending = new Map();
  var listeners = new Map();
  var counter = 0;

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var message = event.data;
    if (!message || message.v !== PROTOCOL_VERSION) return;
    if (message.kind === "event") {
      var handlers = listeners.get(message.method);
      if (handlers) handlers.forEach(function (handler) { handler(message.params); });
      return;
    }
    var entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    window.clearTimeout(entry.timer);
    if (message.kind === "result") entry.resolve(message.result);
    else entry.reject(Object.assign(new Error((message.error && message.error.message) || "调用失败"), { code: message.error && message.error.code }));
  });

  function call(method, params, timeoutMs) {
    counter += 1;
    var id = "c" + counter + "-" + Math.floor(performance.now());
    return new Promise(function (resolve, reject) {
      var timer = window.setTimeout(function () {
        pending.delete(id);
        reject(Object.assign(new Error("宿主未在 " + (timeoutMs || DEFAULT_TIMEOUT_MS) + "ms 内响应"), { code: "OPERATION_TIMEOUT" }));
      }, timeoutMs || DEFAULT_TIMEOUT_MS);
      pending.set(id, { resolve: resolve, reject: reject, timer: timer });
      window.parent.postMessage({ v: PROTOCOL_VERSION, kind: "call", id: id, method: method, params: params || {} }, "*");
    });
  }

  window.$u = Object.freeze({
    version: PROTOCOL_VERSION,
    call: call,
    on: function (name, handler) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(handler);
      return function () { listeners.get(name).delete(handler); };
    },
    host: {
      getContext: function () { return call("host.getContext"); },
      can: function (key) {
        return call("host.getContext").then(function (context) {
          return Boolean(context && context.capabilities && context.capabilities[key]);
        });
      },
      saveFile: function (name, content) { return call("host.saveFile", { name: name, content: content }); },
      copyText: function (text) { return call("host.copyText", { text: text }); },
    },
    snapshot: {
      get: function () { return call("snapshot.get", {}, 15000); },
      query: function (expression) { return call("snapshot.query", { expression: expression }); },
    },
    device: {
      info: function () { return call("device.info"); },
      currentApp: function () { return call("device.currentApp"); },
      logcat: function (options) {
        var params = options || {};
        return call("device.logcat", { after: params.after, limit: params.limit }, 25000);
      },
      logcatClear: function () { return call("device.logcatClear"); },
      tap: function (x, y) { return call("device.tap", { x: x, y: y }); },
      swipe: function (from, to) { return call("device.swipe", { fromX: from.x, fromY: from.y, toX: to.x, toY: to.y }); },
      inputText: function (text) { return call("device.inputText", { text: text }); },
    },
    mcp: {
      callTool: function (name, args) { return call("mcp.callTool", { name: name, arguments: args || {} }, 20000); },
    },
    storage: {
      get: function (key) { return call("storage.get", { key: key }); },
      set: function (key, value) { return call("storage.set", { key: key, value: value }); },
    },
    ui: {
      toast: function (message, tone) { return call("ui.toast", { message: message, tone: tone }); },
      confirm: function (message) { return call("ui.confirm", { message: message }); },
    },
  });
})();
