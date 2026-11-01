<script lang="ts">
  import { onMount } from "svelte";

  import About from "./components/About.svelte";
  import DemoPanel from "./components/DemoPanel.svelte";
  import Footer from "./components/Footer.svelte";
  import Header from "./components/Header.svelte";
  import type { RecordBeats } from "./lib/data/beats";
  import {
    dataUrl,
    fetchBeats,
    fetchManifest,
    fetchTrace,
  } from "./lib/data/load";
  import type { Manifest, RecordEntry } from "./lib/data/manifest";
  import { LabelingSession } from "./lib/labeling";
  import type { ParityCounts } from "./lib/parity";
  import { VISIBLE_S } from "./lib/worker/chunks";
  import { Labeler } from "./lib/worker/client";
  import { canRunModel } from "./lib/worker/support";

  // D1: `?embed=page` is the case study's iframe: no page chrome.
  const embed = new URLSearchParams(location.search).get("embed") === "page";

  // A labeler for pages that cannot run the model: every request fails.
  const NO_MODEL = { label: () => Promise.reject(new Error("no model")) };

  let manifest = $state<Manifest>();
  let loaded = $state<{
    entry: RecordEntry;
    startS: number;
    trace: Int16Array;
    beats: RecordBeats;
    session: LabelingSession;
  }>();
  let traceState = $state<"loading" | "ready" | "error">("loading");
  let modelState = $state<"loading" | "ready" | "fallback">("loading");
  let counts = $state<ParityCounts>({ compared: 0, matched: 0, total: 0 });
  let labelsVersion = $state(0);
  let labelsShown = $state(0);
  let error = $state("");
  // One Worker for the page; each record gets its own labeling session.
  let labeler: Labeler | undefined;
  let choosing = 0;

  const labelSource = $derived(
    modelState === "fallback" ? "python" : labelsShown > 0 ? "browser" : "none",
  );

  function countShown(
    session: LabelingSession,
    beats: RecordBeats,
    from: number,
    to: number,
  ) {
    let shown = 0;
    beats.keptSamples.forEach((sample, row) => {
      if (sample >= from && sample < to && session.store.get(row)) shown++;
    });
    return shown;
  }

  /** Fetch a record and start labeling it; the newest choice wins. */
  async function load(data: Manifest, entry: RecordEntry, startS: number) {
    const ticket = ++choosing;
    const [trace, beats] = await Promise.all([
      fetchTrace(entry.trace),
      fetchBeats(entry.beats),
    ]);
    if (ticket !== choosing) return;
    const fs = data.fs_hz;
    const viewFrom = startS * fs;
    const update = () => {
      if (loaded?.session !== session) return;
      counts = session.store.counts();
      labelsShown = countShown(
        session,
        beats,
        viewFrom,
        viewFrom + VISIBLE_S * fs,
      );
      labelsVersion++;
      if (session.store.fallback) modelState = "fallback";
    };
    const session = new LabelingSession(beats, labeler ?? NO_MODEL, update);
    labeler?.sendRecord(beats.record, trace, beats.samples);
    // DEMO-06: the trace and expert marks play before the model is ready.
    loaded = { entry, startS, trace, beats, session };
    counts = session.store.counts();
    labelsShown = 0;
    traceState = "ready";
    if (!labeler || modelState === "fallback") session.fail();
    else if (modelState === "ready")
      session.fill(viewFrom + VISIBLE_S * fs, fs);
  }

  function select(record: string) {
    const data = manifest!;
    const entry = data.records.find((r) => r.record === record)!;
    // Other records start at the beginning; the default keeps D4's start.
    const startS = record === data.default.record ? data.default.start_s : 0;
    load(data, entry, startS).catch(failed);
  }

  function failed(reason: unknown) {
    traceState = "error";
    error = reason instanceof Error ? reason.message : String(reason);
  }

  onMount(() => {
    void (async () => {
      const data = await fetchManifest();
      manifest = data;
      if (canRunModel()) {
        try {
          labeler = new Labeler({
            model: dataUrl(data.model.model),
            scaler: dataUrl(data.model.scaler),
            calibration: dataUrl(data.model.calibration),
          });
        } catch {
          labeler = undefined;
        }
      }
      const entry = data.records.find((r) => r.record === data.default.record)!;
      await load(data, entry, data.default.start_s);
      if (!labeler) return;
      try {
        await labeler.ready;
      } catch {
        modelState = "fallback";
        loaded?.session.fail();
        return;
      }
      modelState = "ready";
      const current = loaded!;
      current.session.fill(
        (current.startS + VISIBLE_S) * data.fs_hz,
        data.fs_hz,
      );
    })().catch(failed);
    return () => labeler?.terminate();
  });
</script>

<div class="page" class:embed>
  {#if !embed}
    <Header />
  {/if}
  <main
    class="main"
    data-testid="demo"
    data-trace={traceState}
    data-label-source={labelSource}
    data-labels-shown={labelsShown}
  >
    {#if embed}
      <h1 class="visually-hidden">Heartbeat</h1>
    {/if}
    {#if traceState === "error"}
      <p class="message" role="alert">
        The recording could not be loaded ({error}). Reloading the page may
        help.
      </p>
    {:else if manifest && loaded}
      {#key loaded.session}
        <DemoPanel
          {embed}
          {manifest}
          entry={loaded.entry}
          startS={loaded.startS}
          trace={loaded.trace}
          beats={loaded.beats}
          session={loaded.session}
          {modelState}
          {counts}
          {labelsVersion}
          onselect={select}
        />
      {/key}
    {:else}
      <div class="placeholder" aria-hidden="true"></div>
      <p class="message t-small" role="status">Loading the recording</p>
    {/if}
    {#if !embed}
      <About {manifest} />
    {/if}
  </main>
  {#if !embed}
    <Footer />
  {/if}
</div>

<style>
  .page {
    max-width: var(--page-max);
    margin-inline: auto;
    padding-inline: var(--gutter);
  }

  .embed {
    max-width: none;
    height: 100dvh;
    padding: var(--space-3);
    container: demo / size;
  }

  .embed .main {
    height: 100%;
  }

  .placeholder {
    height: 180px;
    border-radius: var(--radius-md);
    box-shadow: inset 0 0 0 1px var(--color-hairline);
  }

  .embed .placeholder {
    height: calc(100% - 3rem);
  }

  .message {
    margin: var(--space-3) 0 0;
  }
</style>
