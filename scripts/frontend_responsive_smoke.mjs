// Optional real-browser layout smoke using installed Chrome + native CDP.
// Required semantic E2E uses React/real HTTP; no new browser framework/dependency.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(root, "tmp/p14-7-e2e");
const chrome =
  process.env.COPILOT_CHROME ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";
await access(chrome); // Explicit failure, not a fabricated layout PASS or silent skip.
await mkdir(output, { recursive: true });
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let backend, browser, vite, ws;
const originalCwd = process.cwd();
const results = [];
try {
  backend = spawn(
    path.join(root, "backend/.venv/Scripts/python.exe"),
    ["backend/tests/agentarts_gateway_harness.py"],
    { cwd: root, windowsHide: true },
  );
  const urls = await new Promise((resolve, reject) => {
    let text = "";
    const timer = setTimeout(
      () => reject(Error("Harness startup timeout")),
      20000,
    );
    backend.stdout.on("data", (data) => {
      text += data;
      const match = text.match(/COMPAT_URLS=(\{[^\r\n]+\})/);
      if (match) {
        clearTimeout(timer);
        resolve(JSON.parse(match[1]));
      }
    });
    backend.once("error", reject);
    backend.stderr.on("data", (data) => reject(Error(String(data))));
  });
  const profile = path.join(output, `chrome-profile-${Date.now()}`);
  await mkdir(profile, { recursive: true });
  browser = spawn(
    chrome,
    [
      "--headless=new",
      "--disable-gpu",
      "--disable-background-networking",
      "--no-first-run",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { windowsHide: true, stdio: "ignore" },
  );
  let debug;
  for (let i = 0; i < 100; i++) {
    try {
      debug = (
        await readFile(path.join(profile, "DevToolsActivePort"), "utf8")
      ).split("\n")[0];
      break;
    } catch {
      await pause(100);
    }
  }
  assert.ok(debug, "Chrome startup timeout");
  const tabs = await (await fetch(`http://127.0.0.1:${debug}/json`)).json();
  ws = new WebSocket(
    tabs.find((tab) => tab.type === "page").webSocketDebuggerUrl,
  );
  await new Promise((resolve) =>
    ws.addEventListener("open", resolve, { once: true }),
  );
  let sequence = 0;
  const pending = new Map(),
    exceptions = [],
    posts = [];
  function call(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(Error(`CDP timeout: ${method}`));
      }, 20000);
      pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }
  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const task = pending.get(message.id);
      pending.delete(message.id);
      if (!task) return;
      message.error
        ? task.reject(Error(JSON.stringify(message.error)))
        : task.resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown")
      exceptions.push(message.params.exceptionDetails);
    else if (
      message.method === "Network.requestWillBeSent" &&
      message.params.request.method === "POST"
    )
      posts.push(message.params.request);
    else if (message.method === "Fetch.requestPaused") {
      const { requestId, request } = message.params;
      const url = new URL(request.url);
      void call(
        url.hostname === "127.0.0.1" || url.hostname === "localhost"
          ? "Fetch.continueRequest"
          : "Fetch.failRequest",
        url.hostname === "127.0.0.1" || url.hostname === "localhost"
          ? { requestId }
          : { requestId, errorReason: "BlockedByClient" },
      );
    }
  });
  async function evaluate(expression) {
    const result = await call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    assert.ok(
      !result.exceptionDetails,
      JSON.stringify(result.exceptionDetails),
    );
    return result.result.value;
  }
  async function wait(expression) {
    for (let i = 0; i < 150; i++) {
      if (await evaluate(`Boolean(${expression})`)) return;
      await pause(100);
    }
    throw Error(
      `UI wait failed: ${expression}\n${await evaluate("document.body.innerText")}`,
    );
  }
  async function fill(selector, text) {
    await evaluate(
      `document.querySelector(${JSON.stringify(selector)}).focus()`,
    );
    await call("Input.insertText", { text });
  }
  async function send(text) {
    await fill("#request-text", text);
    await evaluate('document.querySelector("form.composer").requestSubmit()');
  }
  async function capture(mode, stage) {
    const layout =
      await evaluate(`({ width: innerWidth, scroll: document.documentElement.scrollWidth,
      controls: [...document.querySelectorAll('.hitl-panel button, .hitl-panel input')].map(e => {
        const r=e.getBoundingClientRect(); return {left:r.left,right:r.right,width:r.width,disabled:e.disabled};
      }) })`);
    assert.ok(
      layout.scroll <= layout.width + 1,
      `${mode}/${stage}: horizontal overflow ${JSON.stringify(layout)}`,
    );
    for (const control of layout.controls)
      assert.ok(
        control.width > 0 &&
          control.left >= 0 &&
          control.right <= layout.width + 1,
      );
    const image = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    await writeFile(
      path.join(output, `${mode.toLowerCase()}-${stage}.png`),
      Buffer.from(image.data, "base64"),
    );
    results.push({ mode, stage, layout });
  }
  await call("Runtime.enable");
  await call("Page.enable");
  await call("Network.enable");
  await call("Fetch.enable", { patterns: [{ urlPattern: "http*" }] });
  // Deterministic clock matches the fixture host, never a production clock change.
  await call("Page.addScriptToEvaluateOnNewDocument", {
    source: `const NativeDate=Date;
    globalThis.Date=class extends NativeDate {constructor(...args){if(args.length)super(...args);else super('2026-01-01T00:00:00Z')}
    static now(){return NativeDate.parse('2026-01-01T00:00:00Z')}};`,
  });
  process.chdir(path.join(root, "frontend"));
  const { createServer } = await import(
    pathToFileURL(
      path.join(root, "frontend/node_modules/vite/dist/node/index.js"),
    )
  );
  for (const mode of ["LOCAL", "AGENTARTS"]) {
    console.log(`Responsive smoke: ${mode}`);
    await fetch(urls.gateway + "/__test__/reset", {
      method: "POST",
      body: "{}",
    });
    process.env.VITE_RUNTIME_MODE = mode;
    process.env.VITE_AGENTARTS_RUNTIME_NAME = "competition-copilot";
    process.env.LOCAL_RUNTIME_PROXY_TARGET = urls.local;
    process.env.AGENTARTS_BRIDGE_PROXY_TARGET = urls.bridge;
    vite = await createServer({
      configFile: path.join(root, "frontend/vite.config.ts"),
      server: { host: "127.0.0.1", port: 5173, strictPort: true },
      logLevel: "silent",
    });
    await vite.listen();
    const startCount = posts.length;
    let capturedDashboard = false;
    async function open() {
      const beforeNavigation = posts.length;
      await call("Page.navigate", {
        url: `http://127.0.0.1:5173/?smoke=${Date.now()}`,
      });
      await wait(
        `document.querySelector('.runtime-badge')?.textContent.includes('${mode}') && document.querySelector('.dashboard')`,
      );
      if (!capturedDashboard) {
        for (const width of [1440, 1920]) {
          await call("Emulation.setDeviceMetricsOverride", {
            width,
            height: 1080,
            deviceScaleFactor: 1,
            mobile: false,
          });
          await capture(mode, `dashboard-${width}`);
        }
        await call("Emulation.setDeviceMetricsOverride", {
          width: 1440,
          height: 1100,
          deviceScaleFactor: 1,
          mobile: false,
        });
        capturedDashboard = true;
      }
      await evaluate(
        `document.querySelector('.primary-navigation a[href="#/copilot"]').click()`,
      );
      await wait(
        `location.hash === '#/copilot' && document.querySelector('.primary-navigation a[aria-current="page"]').textContent.includes('Copilot')`,
      );
      assert.equal(
        posts.length,
        beforeNavigation,
        "Product navigation must not invoke backend",
      );
    }
    await call("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 1100,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await open();
    await send("赛事列表");
    await wait('document.querySelector(".result-artifact")');
    await capture(mode, "discovery-desktop");
    const catalogStartCount = posts.length;
    await evaluate(
      `document.querySelector('.primary-navigation a[href="#/competitions"]').click()`,
    );
    await wait(`document.querySelectorAll('.competition-card').length === 12`);
    await capture(mode, "competition-center-desktop");
    await fill('.competition-search input[type="search"]', "华为");
    await wait(`document.querySelectorAll('.competition-card').length === 1`);
    await evaluate(
      `document.querySelector('.competition-card button').click()`,
    );
    await wait(
      `location.hash === '#/competitions/huawei-ict' && document.querySelector('[role="tablist"]')`,
    );
    await capture(mode, "competition-detail-desktop");
    await evaluate(`document.querySelector('[role="tab"]').focus()`);
    await call("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "ArrowRight",
      code: "ArrowRight",
    });
    await wait(
      `document.querySelector('[role="tab"][aria-selected="true"]').textContent === '参赛资格'`,
    );
    await evaluate(
      `document.querySelector('.competition-action-bar button').click(); document.querySelector('.primary-navigation a[href="#/home"]').click()`,
    );
    await wait(
      `document.querySelector('.context-overview').textContent.includes('华为ICT大赛')`,
    );
    await evaluate(
      `document.querySelector('.primary-navigation a[href="#/copilot"]').click()`,
    );
    assert.equal(
      posts.length,
      catalogStartCount,
      "Cached catalog/detail/context selection must not invoke backend",
    );
    await wait(`document.querySelector('.result-artifact')`);
    await call("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await capture(mode, "discovery-narrow");
    for (const student of ["local-graduate", "local-unknown"]) {
      await open();
      await evaluate('document.querySelector(".local-context").open=true');
      await fill("#student-id", student);
      await fill("#competition-id", "gcxl-engineering-practice-innovation");
      await fill("#edition-id", "gcxl-engineering-practice-innovation-2027");
      await send("检查资格");
      await wait('document.querySelector(".source-metadata")');
      await capture(
        mode,
        student === "local-graduate"
          ? "negative-evidence-narrow"
          : "unknown-narrow",
      );
    }
    await open();
    await send("赛事详情");
    await wait('document.querySelector(".clarification-field input")');
    await capture(mode, "clarification-narrow");
    await fill(".clarification-field input", "huawei-ict");
    await evaluate(
      'document.querySelector(".clarification-field input").form.requestSubmit()',
    );
    await wait('document.querySelector(".result-artifact")');
    await capture(mode, "resumed-narrow");
    for (const decision of ["REJECT", "APPROVE"]) {
      await open();
      await evaluate(
        'document.querySelector(".local-context").open=true;document.querySelector(".local-context input[type=checkbox]").click()',
      );
      await send("受控修订");
      await wait('document.querySelector(".approval-actions")');
      await capture(mode, `${decision.toLowerCase()}-wait-narrow`);
      await evaluate(
        `{const button=[...document.querySelectorAll('.approval-actions button')].find(e=>e.textContent.includes('${decision}'));button.click();button.click();}`,
      );
      await wait(
        'document.querySelector(".grounded-results") && !document.querySelector(".approval-actions")',
      );
      assert.equal(
        await evaluate('Boolean(document.querySelector(".plan-diff"))'),
        decision === "APPROVE",
      );
      await capture(mode, `${decision.toLowerCase()}-result-narrow`);
    }
    assert.equal(
      posts.length - startCount,
      9,
      "one runtime POST per explicit action",
    );
    const modePosts = posts.slice(startCount);
    assert.ok(
      modePosts.every(
        (request) =>
          !Object.keys(request.headers).some(
            (key) => key.toLowerCase() === "authorization",
          ) && !request.postData?.includes("HUMAN_APPROVED"),
      ),
    );
    if (mode === "AGENTARTS") {
      const records = await (
        await fetch(urls.gateway + "/__test__/observations")
      ).json();
      assert.equal(records.length, 9);
      assert.ok(
        records.every((entry) => entry.authorized && entry.mcp === null),
      );
    }
    await call("Page.navigate", { url: "about:blank" });
    await vite.close();
    vite = undefined;
  }
  assert.equal(exceptions.length, 0, JSON.stringify(exceptions));
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { passed: true, posts: posts.length, exceptions, results },
      null,
      2,
    ),
  );
  console.log(
    JSON.stringify({
      passed: true,
      modes: 2,
      posts: posts.length,
      layouts: results.length,
      output,
    }),
  );
} finally {
  ws?.close();
  if (browser?.exitCode === null) {
    const ended = once(browser, "exit");
    browser.kill();
    await ended;
  }
  await vite?.close();
  if (backend?.exitCode === null) {
    const ended = once(backend, "exit");
    backend.kill();
    await ended;
  }
  process.chdir(originalCwd);
}
