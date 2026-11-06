// G2, Phase 8 design call 5: the stage video and its still, from the built demo
// with DS2 data, at `?embed=page` in light theme on record 200. The embed always
// shows D7's line (DEMO-15), so the line is in the pixels with no second copy.
//
// Playwright's recorder ignores device scale: it drew the 800 by 500 page in one
// corner of a grey 1600 by 1000 frame (tried 2026-11-06). So this drives the
// page's clock and takes one screenshot per frame. Run after `pnpm run build`:
//   node scripts/record-capture.js
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const PORT = 4174;
const URL_EMBED = `http://localhost:${PORT}/?embed=page`;
const VIEW = { width: 800, height: 500 };
const SCALE = 2;
const FPS = 30;
const SECONDS = 15;
const STILL_AT_S = 10;
const RECORD = "200";
const D7_LINE =
  "Research demo, not medical advice. Recordings come from a public research database.";

const web = fileURLToPath(new URL("../", import.meta.url));
const out = fileURLToPath(new URL("../../docs/case-study/", import.meta.url));
const video = join(out, "capture.mp4");
const still = join(out, "capture.jpg");

function fail(message) {
  console.error(`record-capture: ${message}`);
  process.exit(1);
}

function tool(name, args) {
  const result = spawnSync(name, args, { encoding: "utf8" });
  if (result.error?.code === "ENOENT") {
    fail(`${name} is missing: install it (brew install ffmpeg)`);
  }
  if (result.status !== 0) fail(`${name} failed:\n${result.stderr}`);
  return result.stdout;
}

/** Design call 5: the demo must be the DS2 build and open on record 200. */
function checkBuild() {
  const manifest = JSON.parse(
    readFileSync(join(web, "dist/data/manifest.json"), "utf8"),
  );
  if (manifest.split !== "DS2") fail(`the build is ${manifest.split}, not DS2`);
  if (manifest.default.record !== RECORD) {
    fail(`the build opens on ${manifest.default.record}, not ${RECORD}`);
  }
}

async function waitForServer() {
  for (let attempt = 0; attempt < 50; attempt++) {
    const ready = await fetch(URL_EMBED).then(
      (response) => response.ok,
      () => false,
    );
    if (ready) return;
    await new Promise((done) => setTimeout(done, 200));
  }
  fail(`no server on port ${PORT}`);
}

async function captureFrames(folder) {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({
      viewport: VIEW,
      deviceScaleFactor: SCALE,
      colorScheme: "light",
      reducedMotion: "no-preference",
    });
    const page = await context.newPage();
    await page.clock.install();
    await page.goto(URL_EMBED);
    await page.getByRole("button", { name: "Pause" }).waitFor();
    await page.getByText("Labels match the Python results").waitFor();
    if (!(await page.getByText(D7_LINE).isVisible())) {
      fail("D7's line is not visible in the embed");
    }
    const box = await page.getByText(D7_LINE).boundingBox();
    if (box === null || box.y < 0 || box.y + box.height > VIEW.height) {
      fail(`D7's line is cut off: ${JSON.stringify(box)}`);
    }
    const shown = page.getByText(
      new RegExp(`^Record ${RECORD} \\d+:\\d\\d of `),
    );
    if (!(await shown.isVisible())) fail(`the page is not on record ${RECORD}`);

    await page.clock.pauseAt(Date.now() + 1000);
    const total = FPS * SECONDS;
    for (let frame = 0; frame < total; frame++) {
      await page.clock.runFor(1000 / FPS);
      const name = `frame-${String(frame).padStart(5, "0")}.png`;
      await page.screenshot({ path: join(folder, name) });
    }
  } finally {
    await browser.close();
  }
}

function encode(folder) {
  // prettier-ignore
  tool("ffmpeg", [
    "-y", "-loglevel", "error",
    "-framerate", String(FPS),
    "-i", join(folder, "frame-%05d.png"),
    "-c:v", "libx264", "-preset", "slow", "-crf", "20",
    "-pix_fmt", "yuv420p",
    "-movflags", "+faststart",
    "-an",
    video,
  ]);
  // prettier-ignore
  tool("ffmpeg", [
    "-y", "-loglevel", "error",
    "-ss", String(STILL_AT_S),
    "-i", video,
    "-frames:v", "1", "-q:v", "2",
    still,
  ]);
}

/** Refuse anything but the agreed format; print what ffprobe says. */
function probe() {
  const report = JSON.parse(
    // prettier-ignore
    tool("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration:stream=codec_type,codec_name,pix_fmt,width,height",
      "-of", "json",
      video,
    ]),
  );
  const streams = report.streams;
  const [first] = streams;
  if (
    streams.length !== 1 ||
    first.codec_type !== "video" ||
    first.codec_name !== "h264" ||
    first.pix_fmt !== "yuv420p" ||
    first.width !== VIEW.width * SCALE ||
    first.height !== VIEW.height * SCALE
  ) {
    fail(`unexpected video: ${JSON.stringify(report)}`);
  }
  console.log(JSON.stringify(report));
  console.log(`capture.mp4: ${statSync(video).size} bytes`);
  console.log(`capture.jpg: ${statSync(still).size} bytes`);
}

tool("ffmpeg", ["-version"]);
tool("ffprobe", ["-version"]);
checkBuild();
const server = spawn(
  process.execPath,
  [
    "node_modules/vite/bin/vite.js",
    "preview",
    "--port",
    String(PORT),
    "--strictPort",
  ],
  { cwd: web, stdio: "ignore", detached: true },
);
const folder = mkdtempSync(join(tmpdir(), "heartbeat-capture-"));
try {
  await waitForServer();
  await captureFrames(folder);
  encode(folder);
  probe();
} finally {
  process.kill(-server.pid);
  rmSync(folder, { recursive: true, force: true });
}
