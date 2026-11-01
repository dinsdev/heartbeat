<script lang="ts">
  import { onMount } from "svelte";

  import type { RecordBeats } from "./lib/data/beats";
  import {
    dataUrl,
    fetchBeats,
    fetchManifest,
    fetchTrace,
  } from "./lib/data/load";
  import { LabelingSession } from "./lib/labeling";
  import { canRunModel } from "./lib/worker/support";
  import { Labeler } from "./lib/worker/client";
  import { VISIBLE_S } from "./lib/worker/chunks";

  // A labeler for pages that cannot run the model: every request fails.
  const NO_MODEL = { label: () => Promise.reject(new Error("no model")) };
  const FALLBACK_NOTE =
    "Showing precomputed labels; in-browser model unavailable";

  let traceState = $state<"loading" | "ready" | "error">("loading");
  let modelState = $state<"loading" | "ready" | "fallback">("loading");
  let counter = $state("");
  let labelsShown = $state(0);
  let error = $state("");

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

  onMount(() => {
    let labeler: Labeler | undefined;
    void (async () => {
      const manifest = await fetchManifest();
      const entry = manifest.records.find(
        (r) => r.record === manifest.default.record,
      )!;
      const [trace, beats] = await Promise.all([
        fetchTrace(entry.trace),
        fetchBeats(entry.beats),
      ]);
      traceState = "ready";
      const fs = manifest.fs_hz;
      // The first view: the default 10-second span, its end at the right edge.
      const viewFrom = manifest.default.start_s * fs;
      const playhead = viewFrom + VISIBLE_S * fs;

      const update = () => {
        const c = session.store.counts();
        counter = `Labels match the Python results: ${c.matched.toLocaleString("en")} of ${c.compared.toLocaleString("en")} beats`;
        labelsShown = countShown(session, beats, viewFrom, playhead);
        if (session.store.fallback) modelState = "fallback";
      };
      if (canRunModel()) {
        try {
          labeler = new Labeler({
            model: dataUrl(manifest.model.model),
            scaler: dataUrl(manifest.model.scaler),
            calibration: dataUrl(manifest.model.calibration),
          });
        } catch {
          labeler = undefined;
        }
      }
      const session = new LabelingSession(beats, labeler ?? NO_MODEL, update);
      if (!labeler) {
        session.fail();
        return;
      }
      labeler.sendRecord(beats.record, trace, beats.samples);
      try {
        await labeler.ready;
      } catch {
        session.fail();
        return;
      }
      modelState = "ready";
      session.fill(playhead, fs);
    })().catch((reason: unknown) => {
      traceState = "error";
      error = reason instanceof Error ? reason.message : String(reason);
    });
    return () => labeler?.terminate();
  });
</script>

<main>
  <h1>Heartbeat</h1>
  <section
    data-testid="demo"
    data-trace={traceState}
    data-label-source={labelSource}
    data-labels-shown={labelsShown}
  >
    <p role="status">
      {#if traceState === "error"}
        The recording could not be loaded: {error}
      {:else if traceState === "loading"}
        Loading the recording
      {:else if modelState === "fallback"}
        {FALLBACK_NOTE}
      {:else if modelState === "loading"}
        Model loading
      {:else}
        {counter}
      {/if}
    </p>
  </section>
</main>
