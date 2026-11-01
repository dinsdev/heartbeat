<script lang="ts">
  import { onMount } from "svelte";

  import {
    fetchBeats,
    fetchManifest,
    fetchTrace,
    dataUrl,
  } from "./lib/data/load";
  import { LabelingSession } from "./lib/labeling";
  import { Labeler } from "./lib/worker/client";

  let status = $state("Loading the recording");
  let counter = $state("");

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
      status = "Model loading";
      labeler = new Labeler({
        model: dataUrl(manifest.model.model),
        scaler: dataUrl(manifest.model.scaler),
        calibration: dataUrl(manifest.model.calibration),
      });
      const session = new LabelingSession(beats, labeler, () => {
        const c = session.store.counts();
        counter = `Labels match the Python results: ${c.matched.toLocaleString("en")} of ${c.compared.toLocaleString("en")} beats`;
      });
      labeler.sendRecord(beats.record, trace, beats.samples);
      await labeler.ready;
      status = "";
      session.fill(manifest.default.start_s * manifest.fs_hz, manifest.fs_hz);
    })().catch((error: unknown) => {
      status = error instanceof Error ? error.message : String(error);
    });
    return () => labeler?.terminate();
  });
</script>

<main>
  <h1>Heartbeat</h1>
  <p>In development.</p>
  <p role="status">{status} {counter}</p>
</main>
