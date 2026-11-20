// Records a walkthrough video of docs/index.html.
//   node record_demo.js [output.mp4]
// Drives headless Chrome over the DevTools protocol, captures a screencast of the real page,
// and stitches the frames into an MP4 with ffmpeg. Needs Google Chrome and ffmpeg.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, execFileSync } = require("child_process");
const { pathToFileURL } = require("url");

const ROOT = path.resolve(__dirname, "..");
const OUT = process.argv[2] || path.join(ROOT, "presentation", "GuardEQ_Demo.mp4");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
const W = 1280, H = 720;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "guardeq-chrome-"));
  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "guardeq-frames-"));
  const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    `--window-size=${W},${H}`, "--hide-scrollbars", "--force-device-scale-factor=1", "--allow-file-access-from-files",
    "about:blank"], { stdio: "ignore" });
  try {
    let target;
    for (let i = 0; i < 50 && !target; i++) {
      try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()).find((t) => t.type === "page"); } catch (e) { await sleep(200); }
    }
    if (!target) throw new Error("Chrome did not start");
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r) => ws.addEventListener("open", r, { once: true }));
    let id = 0;
    const pending = new Map();
    const shots = [];
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return; }
      if (msg.method === "Page.screencastFrame") {
        const file = path.join(frames, `f${String(shots.length).padStart(5, "0")}.jpg`);
        fs.writeFileSync(file, Buffer.from(msg.params.data, "base64"));
        shots.push({ file, t: msg.params.metadata.timestamp });
        send("Page.screencastFrameAck", { sessionId: msg.params.sessionId });
      }
    });
    const send = (method, params = {}) => new Promise((resolve) => { const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({ id: i, method, params })); });
    const js = async (expr) => {
      const r = (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result || {};
      if (r.exceptionDetails) throw new Error("page script failed: " + (r.exceptionDetails.exception || {}).description);
      return r.result || {};
    };

    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
    await send("Page.navigate", { url: pathToFileURL(path.join(ROOT, "docs", "index.html")).href });
    for (let i = 0; i < 40; i++) {
      await sleep(250);
      if ((await js("!!(window.GUARDEQ && document.getElementById('budget'))")).value) break;
    }

    // Overlay helpers injected into the page: full-screen cards and a caption bar.
    await js(`(() => {
      const st = document.createElement('style');
      st.textContent = \`
        #dv-card{position:fixed;inset:0;z-index:99;background:#57068C;color:#fff;display:flex;flex-direction:column;justify-content:center;padding:0 110px;font-family:Calibri,-apple-system,sans-serif;transition:opacity .6s}
        #dv-card h1{font:700 64px/1.1 Cambria,Georgia,serif;margin:0 0 14px;color:#fff}
        #dv-card p{font-size:26px;color:#D9C7EC;margin:4px 0}
        #dv-cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:98;background:rgba(28,27,34,.88);color:#fff;font:600 22px/1.35 Calibri,-apple-system,sans-serif;padding:12px 22px;border-radius:10px;max-width:1040px;text-align:center;transition:opacity .4s;opacity:0}
        html{scroll-behavior:smooth}\`;
      document.head.appendChild(st);
      const c = document.createElement('div'); c.id = 'dv-cap'; document.body.appendChild(c);
      window.cap = (t) => { c.style.opacity = t ? 1 : 0; if (t) c.textContent = t; };
      window.card = (h, lines) => { let d = document.getElementById('dv-card'); if (!d) { d = document.createElement('div'); d.id = 'dv-card'; document.body.appendChild(d); }
        d.innerHTML = '<h1>' + h + '</h1>' + lines.map(l => '<p>' + l + '</p>').join(''); d.style.opacity = 1; };
      window.uncard = () => { const d = document.getElementById('dv-card'); if (d) { d.style.opacity = 0; setTimeout(() => d.remove(), 700); } };
      window.to = (sel, off = 70) => { const el = document.querySelector(sel); window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off }); };
      window.setBudget = (v) => { const r = document.getElementById('budget'); r.value = v; r.dispatchEvent(new Event('input')); };
      return true; })()`);
    const meta = (await js("JSON.stringify(window.GUARDEQ.meta)")).value;
    const m = JSON.parse(meta);

    await send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: W, maxHeight: H, everyNthFrame: 1 });

    // ---- script --------------------------------------------------------------
    await js(`card('GuardEQ', ['Equilibrium guardrail placement for tool-using LLM agents', 'Demo of the results replay page  ·  Rohit Shidid  ·  ECE-GY 6263'])`);
    await sleep(4000);
    await js("uncard(); window.scrollTo({top:0}); setBudget(0)");
    await sleep(900);
    await js(`cap('${m.trials.toLocaleString()} logged trials, replayed from saved results. The page makes no model calls.')`);
    await sleep(4200);
    await js("to('#budget', 250)");
    await js("cap('Move the budget: the solver re-mixes guardrails at each entry point.')");
    await sleep(1500);
    for (let v = 0; v <= 20; v++) { await js(`setBudget(${v})`); await sleep(v < 9 ? 520 : 260); }
    await sleep(800);
    await js("cap('At 20% of the judge-everywhere cost, the mix is mostly classifier plus targeted judge checks.')");
    for (let v = 20; v >= 4; v--) { await js(`setBudget(${v})`); await sleep(120); }
    await sleep(3800);
    await js("to('#curve', 120); cap('Worst-case damage vs budget: GuardEQ (purple) drops far faster than random or greedy placement.')");
    await sleep(5500);
    for (let v = 4; v <= 12; v++) { await js(`setBudget(${v})`); await sleep(250); }
    await sleep(1500);
    await js("to('#guardTabs', 140); cap('Measured payoffs: how often each attack type worked, per entry point and guardrail.')");
    await sleep(3500);
    await js("document.querySelector('#guardTabs [data-g=classifier]').click()");
    await sleep(2200);
    await js("document.querySelector('#guardTabs [data-g=judge]').click(); cap('With the LLM judge, almost nothing gets through.')");
    await sleep(3500);
    await js("to('#evalTable', 120); cap('Each policy against an LLM attacker that was told the policy and wrote its own injections.')");
    await sleep(5500);
    await js("to('#runFilter', 110); const f = document.getElementById('runFilter'); f.value = 'eval'; f.dispatchEvent(new Event('change'));");
    await js(`(() => { const p = document.getElementById('runPick'); const o = [...p.options].find(o => /succeeded/.test(o.text)) || p.options[0]; p.value = o.value; p.dispatchEvent(new Event('change')); })()`);
    await js("cap('Replay any run: the attacker\\'s reasoning, the planted text (highlighted), and every tool call the agent made.')");
    await sleep(4500);
    for (let i = 1; i <= 6; i++) { await js(`window.scrollBy({top: 260})`); await sleep(1500); }
    await sleep(1200);
    await js("cap('')");
    await js(`card('github.com/rohitshidid/guardeq', ['Code, every transcript, the report and this demo', 'python -m guardeq all --profile full'])`);
    await sleep(4200);
    await send("Page.stopScreencast");
    await sleep(300);
    ws.close();

    // ---- stitch ----------------------------------------------------------------
    if (shots.length < 10) throw new Error(`only ${shots.length} frames captured`);
    const list = path.join(frames, "list.txt");
    const lines = [];
    for (let i = 0; i < shots.length; i++) {
      const dur = i + 1 < shots.length ? Math.max(0.001, shots[i + 1].t - shots[i].t) : 1.0;
      lines.push(`file '${shots[i].file}'`, `duration ${dur.toFixed(4)}`);
    }
    lines.push(`file '${shots[shots.length - 1].file}'`);
    fs.writeFileSync(list, lines.join("\n"));
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list,
      "-vf", `fps=30,scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p`,
      "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", OUT]);
    console.log(`wrote ${OUT} from ${shots.length} frames`);
  } finally {
    chrome.kill("SIGTERM");
    await new Promise((r) => { chrome.once("exit", r); setTimeout(r, 3000); });
    for (const dir of [profile, frames]) {
      try { fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch (e) { /* temp dir; the OS cleans it */ }
    }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
