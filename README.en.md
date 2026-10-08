<p align="center">
  <img src="./assets/readme/icon.png" width="72" alt="The LayoutSee icon: a rainbow gradient ribbon folded into an M shape">
</p>

[中文](README.md) · English

<p align="center">
  <img src="./assets/readme/hero-inspector.webp" width="100%" alt="The LayoutSee workbench: on the left, a live Android screen with every node outlined and the selected control boxed in red; in the middle, the attribute panel of that node listing class, bounds, index and clickable; on the right, the UI hierarchy tree, an XPath box, and candidate selectors with match counts">
</p>

LayoutSee is a runtime-view tool for mobile devices, built for macOS. Plug in an Android phone and it does two things right away: it puts the screen in a window — live mirroring you can click and type into — and it lays out the **view hierarchy** behind that screen, where every control's text, resource-id, size, position and clickability is readable and actionable.

Coding for mobile was never the hard part for an AI agent. Seeing is. A screenshot gives it a rough idea, but can't say how big a button is, where it sits, or whether something is covering it; `uiautomator dump` returns thousands of lines of XML that neither a person nor a model wants to read. LayoutSee fills that gap: **one capture returns the frame, the hierarchy, the attributes and the coordinates from the same instant**, trimmed into a list an agent can read in one pass and handed over through MCP. Screenshots answer "does it look right"; the view tree answers "what is it, structurally".

It's for mobile developers, QA engineers and AI agents. Android is fully supported today; iOS and HarmonyOS already have a place in the UI, marked as previews.

## How it works

1. **One capture, four things in sync.** Freeze the frame → dump the hierarchy → take that frame's screenshot → build the node index, all inside a single snapshot. The snapshot carries its schema version, platform, orientation, window size, capture time and source driver; the tree, overlays, attributes, summary and diagnostics are all derived from it, so you never end up with a tree from one frame and a picture from another.

2. **Point at something, see everything about it.** Click a control on the screen and the tree expands to it and scrolls into view; select a node in the tree and the screen highlights its bounds. Switch on **inspect mode** and clicking the screen selects a node instead of injecting a tap — safe for poking around on a real device. The attribute panel shows the raw properties in full: class, bounds, index, clickable, content-desc, nothing filtered.

3. **XPath runs on the original XML, selectors come with match counts.** Queries execute against the raw hierarchy text saved at capture time, never against a rebuilt JSON tree, so semantics can't drift. Selecting a node generates candidate selectors, each labelled with how many times it matches in the current snapshot — anything matching more than once is marked unstable.

4. **Agents get a list, not XML.** The semantic summary keeps interactive elements, text nodes and the skeleton of the hierarchy; each element carries a short `ref` and a normalized center point, so the agent can tap without computing coordinates. The default budget is 1200 tokens — over that, text is compressed first and interactive elements are never dropped to fit. Generate twice from the same snapshot and you get identical output.

5. **Diagnostics offer evidence, not opinions.** `diagnose_layout` covers six geometric problems: overlap, occlusion, out-of-bounds, touch targets that are too small, truncated text, and invisible interactive nodes. Each finding lists the nodes involved, quantitative evidence (overlap ratio, target size in dp, pixels out of bounds) and a fixed-template suggestion — no model is asked to invent an explanation.

6. **Agents can act, on a leash.** Read-only mode is a single write gate shared by the UI and MCP; every write lands in an audit log tagged as coming from the UI, MCP or a plugin; there is no shell tool in the MCP catalog, so an agent never gets unbounded command execution. A `ref` is bound to its snapshot — reuse it after the screen changed and the call is rejected instead of tapping something else.

7. **Plugins are an interface, not a back door.** Each plugin declares in its manifest which permissions it wants, what it contributes to the workbench, and whether it registers MCP tools. Code runs in a restricted iframe, capabilities are only reachable through the `$u` bridge, and device-writing permissions ask for confirmation the first time.

## Install

Download the DMG for your architecture from [Releases](https://github.com/IQQcode/LayoutSee/releases/latest): `-arm64` for Apple Silicon, `-x64` for Intel. The builds aren't signed or notarized yet — if macOS blocks the first launch, allow it under System Settings → Privacy & Security → "Open Anyway".

Three things on the phone side: enable Developer Options and USB debugging, connect with a cable that actually carries data, and tap "Always allow from this computer" when the authorization prompt appears.

The Android pipeline needs `adb`. If it isn't installed, the device page walks you through it, you can point LayoutSee at an `adb` binary in Settings, or run `brew install android-platform-tools`.

No sign-up window, no license check, no network calls: snapshots, archives and logs stay on your machine, and the core listens on the loopback interface by default.

## A walkthrough

### Plug the device in

<p align="center">
  <img src="./assets/readme/devices.webp" width="100%" alt="The device page in its empty state: with no devices detected, it shows the three-step guide — enable Developer Options and USB debugging, connect to the Mac with a data cable, confirm the authorization prompt; the footer shows the local core connected on 127.0.0.1">
</p>

Devices are listed per platform: serial, model, status, and a way in. The list refreshes every five seconds and tells you when something is plugged or unplugged; when nothing is detected you get the three-step guide instead of a blank page. Next to it is group control: several devices in a grid, each cell refreshing its own screen, each cell freezable, double-click to open a workbench.

### Mirror, and just use it

<p align="center">
  <img src="./assets/readme/workbench.webp" width="100%" alt="The device workbench: an Android screen being mirrored on the left, with a vertical control rail holding Home, recents, power, volume, rotate, capture, freeze, read-only and inspect-mode buttons; on the right, the Common tab with the foreground package and activity, an app-launch form and a package search">
</p>

Android mirroring runs on scrcpy: H.264 over a WebSocket, decoded in the browser, degrading to a screenshot mode on devices that don't cooperate — never a black screen. The rail on the left drives the device: Home, recents, power, volume, rotate, capture, freeze, read-only, inspect mode. Left click taps, dragging swipes, middle click is Home, right click is Back, the wheel scrolls; the keyboard types straight to the device, Enter and Backspace included. The Common tab handles apps: see the foreground package and activity, start, stop, clear data.

### Capture once: tree, attributes, summary, diagnostics

<p align="center">
  <img src="./assets/readme/summary.webp" width="100%" alt="The Layout Intelligence tab: the semantic summary reports 1186 tokens with all 20/20 interactive elements kept, listing each element with its ref, role, text and normalized coordinates; below it is the entry point for layout diagnostics covering occlusion, overlap, out-of-bounds, small touch targets, text truncation and invisible interactive nodes">
</p>

Hit **Capture now** and you get the frame, the hierarchy, the attributes and the coordinates from the same instant. The Elements tab holds the hierarchy tree, the attribute panel, XPath queries and candidate selectors; the Layout Intelligence tab holds the summary the agent actually receives, plus diagnostics — the screenshot above shows 20 interactive elements kept in full while 17 low-value text nodes were trimmed. If you want to know what your agent sees, this is where you look.

### Hand the endpoint to your agent

<p align="center">
  <img src="./assets/readme/mcp.webp" width="100%" alt="The MCP tab: every online device gets its own SSE endpoint (http://127.0.0.1:11663/mcp/android-38181D12A60000/sse), with a config snippet switchable between .mcp.json, Claude, Cursor and Comate and a copy button; below, the tool list, with writes governed by read-only mode">
</p>

The MCP tab lists each device's own SSE endpoint, with the config snippet ready in `.mcp.json`, Claude, Cursor and Comate flavours — copy, paste, done. The tool list shows all 12 built-ins, and with read-only mode on, write tools are turned away at the door.

## The 12 built-in MCP tools

Every online device gets its own endpoint; it stops serving when the device disconnects and comes back with the same address. Twelve built-ins, nine reads and three writes — and plugins can register more under the `plugin.<id>.<name>` namespace.

| Tool | Kind | What it does |
| --- | :---: | --- |
| `capture_layout` | read | Atomic capture — freeze, dump, screenshot and index in one pass; returns snapshot id, node count, sync state |
| `get_layout` | read | The full node tree and context of a snapshot; omit the id for the latest one |
| `get_layout_summary` | read | Deterministic semantic summary, elements carrying short `ref`s and center points |
| `diagnose_layout` | read | Six classes of layout findings with quantitative evidence and suggestions |
| `find_element` | read | Look up an element by text, description or resource-id; returns its `ref` |
| `query_xpath` | read | Run XPath against the snapshot's original XML; returns node keys |
| `get_device_info` | read | Model, serial, window size, density, orientation, read-only state |
| `get_current_app` | read | Foreground package and activity |
| `get_screenshot` | read | PNG of the live screen or a chosen snapshot (base64) |
| `tap` | write | Tap by coordinates or by `ref` |
| `swipe` | write | Swipe gestures |
| `input_text` | write | Type text |

Failures come back as structured error codes rather than stack traces: `SNAPSHOT_STALE` means there's no usable snapshot yet, so capture first; `READ_ONLY_MODE` means the write gate is closed; `REF_NOT_FOUND` means that `ref` died with its snapshot — ask for a new one.

## Plugins

The plugin page ships with three extensions: **Terminal** (a built-in adb shell that double-checks dangerous commands), **Android log capture** and **Snapshot overview**. The latter two live in [`repos/plugins/`](./repos/plugins/) — copy them as a starting point.

<p align="center">
  <img src="./assets/readme/plugins.webp" width="100%" alt="The plugin page: three cards for Terminal, Android log capture and Snapshot overview, each showing availability, its permission list and an open button; the note below explains that plugins run in a restricted iframe and can only reach capabilities through the $u bridge">
</p>

<p align="center">
  <img src="./assets/readme/logcat.webp" width="100%" alt="The Android log plugin: a graphical filter over adb logcat with level, tag and pid filters, pause and resume, clear and restart, auto-scroll and soft wrap, matching the feel of Android Studio's logcat">
</p>

A plugin needs no build step: one directory with a `manifest.json` and an entry HTML file. The manifest states three things — which permissions it needs (`device.read`, `device.write`, `storage.local`, `host.integration`), what it contributes (a workbench tab, or MCP tools via `mcpTools`), and where it applies (host, device platform, engine version range). Plugins run inside an iframe, can't make network requests of their own, and reach everything through the `$u` bridge. Local plugins live in `~/Library/Application Support/LayoutSee/plugins/`, and the plugin page has a button that opens that folder.

## Platforms and limits

| Platform / App | Status |
| --- | --- |
| Android | Full pipeline: mirroring and control, capture, hierarchy and attributes, semantic summary, six diagnostics, MCP, plugins |
| iOS | Placeholder in the UI (marked preview); integration not implemented yet |
| HarmonyOS | Same as iOS |
| Apps | macOS (Apple Silicon and Intel DMGs); the UI is served by the local core, so a browser pointing at it gets the same interface |

<p align="center">
  <img src="./assets/readme/roadmap.webp" width="100%" alt="The iOS tab placeholder reading &quot;iOS support is on the way&quot;, listing device discovery and diagnostics, live mirroring and control, atomic snapshots with element lookup, and MCP tools with plugins — noting these capabilities are currently Android-only">
</p>

Not built yet: snapshot archives and diffs, `.lsnap` import/export, a Windows app, and the team-server form. They sit after V0.2 in the [PRD](./docs/feature/UI-LayoutSee需求文档PRD.md) (Chinese). Two things are deliberately out of scope: design-file comparison and static analysis of layout XML source.

## Run from source

```bash
npm install          # install workspace dependencies (contracts / web / mac)
npm run dev:web      # start the core and open the UI at http://127.0.0.1:4173
npm run test:unit    # unit tests for contracts, core, web and mac
npm run lint         # static checks for the three npm packages
npm run build:all    # contract drift gate + web build + mac main-process build
npm run package:mac  # produce an unsigned DMG and the unpacked app
```

Requires Node ≥ 22.12, Python 3.12 (via uv), macOS and `adb`. In production the core hosts the built frontend: `uv run --project repos/core python -m layoutsee_core --nonce <64hex> --static-dir repos/web/dist`. Per-module build and test commands are in [source/index.md](./source/index.md) (Chinese).

## What's in the repo

- [`repos/contracts`](./repos/contracts/) — single source of truth for cross-process contracts: OpenAPI and JSON Schema, with a drift gate on generated artifacts;
- [`repos/core`](./repos/core/) — the Python core: device access, atomic snapshots, semantic summary, layout diagnostics, the MCP server and the plugin host;
- [`repos/web`](./repos/web/) — the workbench frontend (Vite + React), one build shared by the browser and the desktop shell;
- [`repos/mac`](./repos/mac/) — the macOS shell (Electron): native window, core process supervision, packaging;
- [`repos/plugins`](./repos/plugins/) — bundled plugin examples: log capture and snapshot overview;
- [`skills/layout-see`](./skills/layout-see/) — the skill that teaches an agent to read layouts, run diagnostics and answer from evidence.

The repository is also a working space: the PRD, design specs, competitor research, technical specs and the rules agents follow all live here. The full file tree, directory responsibilities and documentation map are in [docs/repo-structure.md](./docs/repo-structure.md) (Chinese).

## Things it works with

- [`skills/layout-see`](./skills/layout-see/) — hand this skill to your agent and it will know when to capture, when to diagnose, and how to answer questions like "why can't I tap this control". There's also a script path that talks to the local endpoint directly when MCP isn't available.
- [uiautomator2](https://github.com/openatx/uiautomator2) and [scrcpy](https://github.com/Genymobile/scrcpy) — the Android capture and mirroring layers stand on both.
- [uiautodev](https://github.com/codeskyblue/uiautodev) — the core's device-access layer is a fork of this open-source project, inheriting its unified node contract and control/media split; the product layer and the AI layer are rewritten.
