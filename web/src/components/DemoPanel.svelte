<script lang="ts">
  import { onMount, untrack } from "svelte";

  import type { RecordBeats } from "../lib/data/beats";
  import type { Manifest, RecordEntry } from "../lib/data/manifest";
  import { clockTime, count } from "../lib/format";
  import type { LabelingSession } from "../lib/labeling";
  import type { ParityCounts } from "../lib/parity";
  import { PlaybackClock, SPEEDS } from "../lib/playback/clock";
  import { SPAN_S } from "../lib/trace/geometry";
  import Legend from "./Legend.svelte";
  import Trace from "./Trace.svelte";

  interface Props {
    embed: boolean;
    manifest: Manifest;
    entry: RecordEntry;
    trace: Int16Array;
    beats: RecordBeats;
    session: LabelingSession;
    modelState: "loading" | "ready" | "fallback";
    counts: ParityCounts;
    labelsVersion: number;
  }

  let {
    embed,
    manifest,
    entry,
    trace,
    beats,
    session,
    modelState,
    counts,
    labelsVersion,
  }: Props = $props();

  const FALLBACK_NOTE =
    "Showing precomputed labels; in-browser model unavailable";
  const D7_LINE =
    "Research demo, not medical advice. Recordings come from a public research database.";
  const TRAINING_NOTE =
    "Development build: these are training patients the model has already seen, so its labels here look better than they would on new patients.";

  // A panel lives for one record: its rate, start and length are read once.
  const { fs, start, duration } = untrack(() => ({
    fs: manifest.fs_hz,
    start: manifest.default.start_s,
    duration: trace.length / manifest.fs_hz,
  }));
  // The first view is the default 10-second span; the playhead is its right edge.
  const clock = new PlaybackClock(
    () => performance.now(),
    start + SPAN_S,
    duration,
    SPAN_S,
  );
  let playing = $state(false);
  let speed = $state(String(clock.speed));
  let reducedMotion = $state(
    matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  let shownSecond = $state(Math.floor(clock.position()));
  let redraw = $state(0);
  let lastFill = -Infinity;

  const mismatches = $derived(counts.compared - counts.matched);
  const fullHref = $derived.by(() => {
    const url = new URL(location.href);
    url.searchParams.delete("embed");
    return url.href;
  });
  const traceLabel = $derived(
    `ECG trace of record ${entry.record}, ${clockTime(shownSecond - SPAN_S)} to ${clockTime(shownSecond)}, with a label on each beat`,
  );

  function onframe(position: number, viewEnd: number) {
    const second = Math.floor(position);
    if (second !== shownSecond) shownSecond = second;
    if (playing !== clock.playing) playing = clock.playing;
    // DEMO-03: keep the visible span and the next 10 seconds labeled.
    if (Math.abs(viewEnd - lastFill) >= 0.5) {
      lastFill = viewEnd;
      session.fill(Math.round(viewEnd * fs), fs);
    }
  }

  function changeSpeed() {
    clock.setSpeed(Number(speed));
    redraw++;
  }

  function toggle() {
    if (clock.playing) clock.pause();
    else clock.play();
    playing = clock.playing;
    redraw++;
  }

  $effect(() => {
    // New labels or a model change: draw again even while paused.
    void labelsVersion;
    void modelState;
    lastFill = -Infinity;
    redraw++;
  });

  onMount(() => {
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const onMotion = () => (reducedMotion = motion.matches);
    motion.addEventListener("change", onMotion);
    // D6: the full page autoplays, silent, with a visible pause; never under
    // reduced motion.
    if (!motion.matches) {
      clock.play();
      playing = true;
      redraw++;
    }
    return () => motion.removeEventListener("change", onMotion);
  });
</script>

<section
  class="panel"
  class:embed
  data-testid="demo-panel"
  aria-label="Live demo"
>
  <div class="strip">
    <Trace
      {trace}
      {beats}
      store={session.store}
      {fs}
      {clock}
      {redraw}
      fill={embed}
      scrub={!embed}
      {reducedMotion}
      label={traceLabel}
      {onframe}
    />
  </div>

  <div class="bar">
    <button class="play" type="button" aria-pressed={playing} onclick={toggle}>
      <span class="icon" class:pause={playing} aria-hidden="true"></span>
      {playing ? "Pause" : "Play"}
    </button>
    <label class="speed t-small">
      Speed
      <select bind:value={speed} onchange={changeSpeed}>
        {#each SPEEDS as option (option)}
          <option value={String(option)}>{option}x</option>
        {/each}
      </select>
    </label>
    <p class="where t-data">
      <span>Record {entry.record}</span>
      <span class="time" data-testid="playhead" data-seconds={shownSecond}
        >{clockTime(shownSecond)} of {clockTime(clock.duration)}</span
      >
    </p>
    <p class="status t-small" role="status">
      {#if modelState === "fallback"}
        {FALLBACK_NOTE}
      {:else if modelState === "loading"}
        Model loading
      {:else}
        Labels match the Python results: {count(counts.matched)} of {count(
          counts.compared,
        )} beats{#if mismatches > 0}<strong class="mismatch"
            >, {count(mismatches)} differ</strong
          >{/if}
      {/if}
    </p>
  </div>

  <Legend compact={embed} />

  <div class="notes t-small">
    <p class="d7">{D7_LINE}</p>
    {#if manifest.split === "DS1"}
      <p class="training">{TRAINING_NOTE}</p>
    {/if}
    {#if embed}
      <p>
        <a href={fullHref} target="_blank" rel="noopener">Open the full demo</a>
      </p>
    {/if}
  </div>
</section>

<style>
  .panel {
    display: grid;
    gap: var(--space-4);
  }

  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-5);
  }

  .play {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 40px;
    padding: 0 var(--space-5) 0 var(--space-4);
    border: 0;
    border-radius: var(--radius-pill);
    background: var(--color-accent);
    color: var(--color-paper);
    font: 600 var(--text-small) / 1 var(--font-text);
    cursor: pointer;
    /* apple-design: the press responds at once. */
    transition: transform 100ms ease-out;
  }

  .play:hover {
    filter: brightness(1.08);
  }

  .play:active {
    transform: scale(0.97);
  }

  .icon {
    width: 0;
    height: 0;
    border-style: solid;
    border-width: 6px 0 6px 10px;
    border-color: transparent transparent transparent currentColor;
  }

  .icon.pause {
    width: 10px;
    height: 12px;
    border: 0;
    border-inline: 3px solid currentColor;
  }

  .speed {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-muted);
  }

  .speed select {
    min-height: 32px;
    padding: 0 var(--space-2);
    border: 1px solid var(--color-hairline);
    border-radius: var(--radius-md);
    background: var(--color-paper);
    color: var(--color-ink);
    font: inherit;
  }

  .where {
    display: flex;
    gap: var(--space-4);
    margin: 0;
    color: var(--color-muted);
  }

  .time {
    color: var(--color-ink);
  }

  .status {
    margin: 0;
    color: var(--color-ink);
    margin-inline-start: auto;
  }

  .mismatch {
    color: var(--hb-class-v);
  }

  .notes {
    display: grid;
    gap: var(--space-2);
  }

  .notes p {
    margin: 0;
  }

  .training {
    max-width: 66ch;
    padding-inline-start: var(--space-3);
    border-inline-start: 3px solid var(--color-amber);
    color: var(--color-ink);
  }

  /* Settling 5: the embed fills the site's box, laid out by container queries. */
  .embed {
    height: 100%;
    grid-template-rows: minmax(0, 1fr) auto auto auto;
    gap: var(--space-3);
  }

  .embed .strip {
    min-height: 0;
  }

  .embed .notes {
    gap: var(--space-1);
  }

  /* A narrow embed (about 4:5 on phones): smaller text, more paper. */
  @container demo (max-width: 480px) {
    .status {
      margin-inline-start: 0;
      flex-basis: 100%;
    }

    .embed {
      gap: var(--space-2);
    }

    .embed .bar {
      gap: var(--space-2) var(--space-4);
    }

    .embed .play {
      min-height: 36px;
    }

    .embed .notes,
    .embed :global(.legend) {
      font-size: var(--text-label);
      line-height: 1.4;
    }
  }

  @media (max-width: 560px) {
    .status {
      margin-inline-start: 0;
      flex-basis: 100%;
    }
  }
</style>
