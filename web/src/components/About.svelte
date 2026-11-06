<script lang="ts">
  import type { Manifest } from "../lib/data/manifest";
  import { dataUrl } from "../lib/data/load";

  let { manifest }: { manifest: Manifest | undefined } = $props();
</script>

<section class="about t-body" aria-labelledby="about-title">
  <h2 id="about-title" class="t-h2">How it works</h2>
  <p>
    Each recording is about 30 minutes of ECG from the MIT-BIH Arrhythmia
    Database. The demo shows one lead, filtered in Python from 0.5 to 40 Hz, and
    two cardiologists reviewed each recording's beat labels. For each beat your
    browser cuts a window of 256 samples around it, measures the gaps to the
    beats before and after, and passes both to a small convolutional network
    running in ONNX Runtime in a Web Worker.
  </p>
  <p>
    The counter checks every label against the one Python computed for the same
    beat: the same class, and probabilities within 0.00001. If the model cannot
    load in your browser, the page plays the Python labels instead and says so.
  </p>

  <h3 class="t-h3">Why this recording opens first</h3>
  <p>
    A rule on the expert labels alone picks it: the recording with the most
    early beats (S plus V) among those with at least 25 of each. It starts at
    the first 10 seconds that hold one.
  </p>

  <h3 class="t-h3">Labels arrive one beat late</h3>
  <p>
    The model reads the gap to the next beat, so each label appears once the
    following beat has played. Until then the beat shows a small open circle.
  </p>

  <h3 class="t-h3">A research demo</h3>
  <p>
    This is a research demo. The model has not been clinically validated and
    must not be used to make health decisions. The recordings come from the
    MIT-BIH Arrhythmia Database, collected in a hospital lab between 1975 and
    1979. Nothing here uses your data, and you cannot upload your own. If you
    have concerns about your heart, talk to a doctor.
  </p>

  <h3 class="t-h3">Data</h3>
  <p>
    {manifest?.attribution ??
      "Contains information from the MIT-BIH Arrhythmia Database (version 1.0.0, PhysioNet), which is made available under the ODC Attribution License v1.0."}
    Moody G, Mark R. MIT-BIH Arrhythmia Database (version 1.0.0). PhysioNet (2005).
    <a href="https://doi.org/10.13026/C2F305">doi:10.13026/C2F305</a>.
    {#if manifest}
      <a href={dataUrl(manifest.attribution_file)}>The full attribution note</a
      >.
    {/if}
  </p>
</section>

<style>
  .about {
    max-width: none;
    padding-block: var(--space-9) var(--space-8);
  }

  .about :global(h2) {
    margin: 0 0 var(--space-5);
  }

  .about :global(h3) {
    margin: var(--space-7) 0 var(--space-3);
    padding-top: var(--space-5);
    border-top: 1px solid var(--color-hairline);
  }

  p {
    max-width: var(--measure);
    margin: 0 0 var(--space-4);
  }

  /* Wide screens: the section title holds its place on the left while the
     text runs on the right. The markup stays one flat column. */
  @media (min-width: 960px) {
    .about {
      display: grid;
      grid-template-columns: minmax(12rem, 1fr) minmax(0, 2fr);
      column-gap: var(--space-8);
      align-items: start;
    }

    .about > :global(*) {
      grid-column: 2;
    }

    .about > :global(h2) {
      position: sticky;
      top: var(--space-6);
      grid-row: 1 / span 20;
      grid-column: 1;
    }
  }
</style>
