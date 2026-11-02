<script lang="ts">
  import { onMount, untrack } from "svelte";

  import type { RecordBeats } from "../lib/data/beats";
  import type { Manifest, RecordEntry } from "../lib/data/manifest";
  import { clockTenths, clockTime, count } from "../lib/format";
  import type { LabelingSession } from "../lib/labeling";
  import type { ParityCounts } from "../lib/parity";
  import { PlaybackClock, SPEEDS } from "../lib/playback/clock";
  import {
    jumpTarget,
    nextDisagreement,
    nextIrregular,
    searchFrom,
  } from "../lib/playback/jumps";
  import { pageEnd, stepPage } from "../lib/playback/pages";
  import {
    beatRows,
    recordOption,
    statusLine,
    traceSummary,
  } from "../lib/summary";
  import { SPAN_S } from "../lib/trace/geometry";
  import BeatTable from "./BeatTable.svelte";
  import Legend from "./Legend.svelte";
  import Trace from "./Trace.svelte";

  interface Props {
    embed: boolean;
    manifest: Manifest;
    entry: RecordEntry;
    /** Where the first view starts, in seconds. */
    startS: number;
    trace: Int16Array;
    beats: RecordBeats;
    session: LabelingSession;
    modelState: "loading" | "ready" | "fallback";
    counts: ParityCounts;
    labelsVersion: number;
    onselect: (record: string) => void;
  }

  let {
    embed,
    manifest,
    entry,
    startS,
    trace,
    beats,
    session,
    modelState,
    counts,
    labelsVersion,
    onselect,
  }: Props = $props();

  const FALLBACK_NOTE =
    "Showing precomputed labels; in-browser model unavailable";
  const D7_LINE =
    "Research demo, not medical advice. Recordings come from a public research database.";
  const TRAINING_NOTE =
    "Development build: these are training patients the model has already seen, so its labels here look better than they would on new patients.";
  const NO_IRREGULAR = "No irregular beats in this recording";
  const NO_DISAGREEMENT =
    "No disagreements in this recording: the model agrees with the experts on every scored beat";

  // A panel lives for one record: its rate, start and length are read once.
  const { fs, start, duration, record } = untrack(() => ({
    fs: manifest.fs_hz,
    start: startS,
    duration: trace.length / manifest.fs_hz,
    record: entry.record,
  }));
  // The first view is a 10-second span; the playhead is its right edge.
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
  // The view's right edge in whole seconds, for tests: it changes at most
  // once a second of recording, never per frame.
  let viewEndSecond = $state(Math.floor(viewEndOf(clock.position())));
  let redraw = $state(0);
  // What the words describe: the span at the last 10-second mark, pause or seek.
  let described = $state(spanEnding(clock.position()));
  let summary = $state("");
  let traceLabel = $state("");
  let jumpNote = $state("");
  let sliding = $state(false);
  let lastFill = -Infinity;
  let lastWindow = -1;
  let lastJump: number | undefined;

  const mismatches = $derived(counts.compared - counts.matched);
  const fullHref = $derived.by(() => {
    const url = new URL(location.href);
    url.searchParams.delete("embed");
    return url.href;
  });
  const rows = $derived.by(() => {
    void labelsVersion;
    return beatRows(beats, session.store, fs, described.from, described.to);
  });
  const spanText = $derived(
    `${clockTime(described.from / fs)} to ${clockTime(described.to / fs)}`,
  );
  const timeText = $derived(
    `${clockTime(shownSecond)} of ${clockTime(duration)}`,
  );

  function viewEndOf(position: number): number {
    return reducedMotion ? pageEnd(position, clock.min, duration) : position;
  }

  function spanEnding(position: number) {
    const to = Math.round(viewEndOf(position) * fs);
    return { from: to - SPAN_S * fs, to };
  }

  /** The table and the polite status line (DEMO-12). */
  function summarize(position: number) {
    described = spanEnding(position);
    summary = statusLine(beats, session.store, described.from, described.to);
  }

  /** D6: the canvas label, on pause and seek only. */
  function labelTrace(position: number) {
    const { from, to } = spanEnding(position);
    traceLabel = traceSummary(record, beats, session.store, fs, from, to);
  }

  function describeAll() {
    const position = clock.position();
    summarize(position);
    labelTrace(position);
    lastWindow = Math.floor(viewEndOf(position) / SPAN_S);
  }

  function onframe(position: number, viewEnd: number) {
    const second = Math.floor(position);
    if (second !== shownSecond) shownSecond = second;
    const end = Math.floor(viewEnd);
    if (end !== viewEndSecond) viewEndSecond = end;
    if (playing !== clock.playing) {
      playing = clock.playing;
      // The recording ran out: that is a pause too.
      if (!playing && position >= duration) describeAll();
    }
    // D6: a summary every 10 seconds of playback.
    const window = Math.floor(viewEnd / SPAN_S);
    if (clock.playing && window !== lastWindow) {
      lastWindow = window;
      summarize(position);
    }
    // DEMO-03: keep the visible span and the next 10 seconds labeled.
    if (Math.abs(viewEnd - lastFill) >= 0.5) {
      lastFill = viewEnd;
      session.fill(Math.round(viewEnd * fs), fs);
    }
  }

  function toggle() {
    if (clock.playing) {
      clock.pause();
      describeAll();
    } else clock.play();
    playing = clock.playing;
    redraw++;
  }

  function changeSpeed() {
    clock.setSpeed(Number(speed));
    redraw++;
  }

  function seekTo(seconds: number) {
    clock.seek(seconds);
    shownSecond = Math.floor(clock.position());
    lastJump = undefined;
    describeAll();
    redraw++;
  }

  /** DEMO-14: under reduced motion the view moves by whole pages. */
  function turnPage(pages: number) {
    seekTo(stepPage(clock.position(), pages, clock.min, duration));
  }

  function onslide(event: Event) {
    seekTo(Number((event.currentTarget as HTMLInputElement).value));
  }

  function jump(kind: "irregular" | "disagreement") {
    const position = clock.position();
    const after = searchFrom(
      position,
      viewEndOf(position),
      fs,
      reducedMotion,
      lastJump,
    );
    const row =
      kind === "irregular"
        ? nextIrregular(beats, after)
        : nextDisagreement(beats, session.store, after);
    if (row === undefined) {
      jumpNote = kind === "irregular" ? NO_IRREGULAR : NO_DISAGREEMENT;
      return;
    }
    const sample = beats.keptSamples[row]!;
    const expert = beats.classes[beats.keptIndex[row]!]!;
    const model = session.store.get(row)?.label ?? beats.pythonLabels[row]!;
    seekTo(jumpTarget(sample, fs, reducedMotion, clock.min, duration));
    lastJump = sample;
    const at = `Beat at ${clockTenths(sample / fs)}`;
    jumpNote =
      kind === "irregular"
        ? `${at}: experts ${expert}`
        : `${at}: model ${model}, experts ${expert}`;
  }

  function pick(event: Event) {
    onselect((event.currentTarget as HTMLSelectElement).value);
  }

  $effect(() => {
    // New labels or a model change: draw again even while paused.
    void labelsVersion;
    void modelState;
    untrack(() => {
      lastFill = -Infinity;
      redraw++;
      // While paused the words follow the labels as they arrive.
      if (!clock.playing) describeAll();
    });
  });

  onMount(() => {
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const onMotion = () => {
      reducedMotion = motion.matches;
      describeAll();
    };
    motion.addEventListener("change", onMotion);
    describeAll();
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
  <div class="strip" data-view-end={viewEndSecond}>
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
      onseek={describeAll}
    />
  </div>

  <div class="bar">
    <button class="play" type="button" aria-pressed={playing} onclick={toggle}>
      <span class="icon" class:pause={playing} aria-hidden="true"></span>
      {playing ? "Pause" : "Play"}
    </button>
    {#if reducedMotion}
      <button
        class="quiet"
        type="button"
        aria-label="Previous 10 seconds"
        onclick={() => turnPage(-1)}>Previous</button
      >
      <button
        class="quiet"
        type="button"
        aria-label="Next 10 seconds"
        onclick={() => turnPage(1)}>Next</button
      >
    {/if}
    <label class="field t-small">
      <span class="field-name">Speed</span>
      <select bind:value={speed} onchange={changeSpeed}>
        {#each SPEEDS as option (option)}
          <option value={String(option)}>{option}x</option>
        {/each}
      </select>
    </label>
    <button class="quiet" type="button" onclick={() => jump("irregular")}
      >Next irregular beat</button
    >
    <button class="quiet" type="button" onclick={() => jump("disagreement")}
      >Next disagreement</button
    >
    {#if embed}
      <p class="t-data record">Record {record} {@render playhead()}</p>
    {/if}
  </div>

  {#snippet playhead()}
    <span class="time t-data" data-testid="playhead" data-seconds={shownSecond}
      >{timeText}</span
    >
  {/snippet}

  {#if embed}
    <!-- Settling 5's compact set: record and time ride in the bar. -->
  {:else}
    <div class="where">
      <label class="field t-small">
        Recording
        <select value={record} onchange={pick}>
          {#each manifest.records as option (option.record)}
            <option value={option.record}>{recordOption(option)}</option>
          {/each}
        </select>
      </label>
      {@render playhead()}
      <input
        class="scrub"
        type="range"
        aria-label="Position"
        aria-valuetext={timeText}
        min={SPAN_S}
        max={Math.floor(duration)}
        step="5"
        value={sliding ? undefined : shownSecond}
        oninput={onslide}
        onpointerdown={() => (sliding = true)}
        onchange={() => (sliding = false)}
      />
    </div>
  {/if}

  <div class="words t-small">
    <p class="counter">
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
    {#if !embed}
      <!-- DEMO-12; the embed's compact set leaves it out (settling 5). -->
      <p class="summary" role="status" data-testid="summary">{summary}</p>
    {/if}
    <p class="jump" role="status" data-testid="jump-note">{jumpNote}</p>
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

  {#if !embed}
    <BeatTable {rows} span={spanText} />
  {/if}
</section>

<style>
  .panel {
    display: grid;
    gap: var(--space-4);
  }

  .bar,
  .where {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-4);
  }

  button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-height: 40px;
    border-radius: var(--radius-pill);
    font: 600 var(--text-small) / 1 var(--font-text);
    cursor: pointer;
    /* apple-design: the press responds at once. */
    transition: transform 100ms ease-out;
  }

  button:active {
    transform: scale(0.97);
  }

  .play {
    padding: 0 var(--space-5) 0 var(--space-4);
    border: 0;
    background: var(--color-accent);
    color: var(--color-paper);
  }

  .play:hover {
    filter: brightness(1.08);
  }

  .quiet {
    padding: 0 var(--space-4);
    border: 1px solid var(--color-hairline);
    background: transparent;
    color: var(--color-ink);
  }

  .quiet:hover {
    border-color: var(--color-muted);
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

  .field {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-muted);
  }

  select {
    min-height: 32px;
    max-width: 100%;
    padding: 0 var(--space-2);
    border: 1px solid var(--color-hairline);
    border-radius: var(--radius-md);
    background: var(--color-paper);
    color: var(--color-ink);
    font: inherit;
  }

  .record {
    display: inline-flex;
    gap: var(--space-3);
    margin: 0;
    color: var(--color-muted);
  }

  .time {
    color: var(--color-ink);
    white-space: nowrap;
  }

  .scrub {
    flex: 1 1 16rem;
    min-width: 0;
    min-height: 24px;
    margin: 0;
    accent-color: var(--color-accent);
  }

  .words {
    display: flex;
    flex-direction: column;
  }

  .words p {
    margin: 0;
    color: var(--color-ink);
  }

  /* Empty live regions stay in the page (so they announce) but take no room. */
  .words p:not(:empty) ~ p:not(:empty) {
    margin-top: var(--space-1);
  }

  .summary,
  .jump {
    color: var(--color-muted);
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
    grid-template-rows: minmax(0, 1fr) auto auto auto auto auto;
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
    .embed {
      gap: var(--space-2);
    }

    .embed .bar,
    .embed .where {
      gap: var(--space-2) var(--space-3);
    }

    .embed button {
      min-height: 32px;
      font-size: var(--text-label);
    }

    /* The select keeps its label for assistive tech; the word gives way to paper. */
    .embed .field-name {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }

    .embed select {
      min-height: 32px;
    }

    .embed .record {
      gap: var(--space-2);
      font-size: var(--text-label);
    }

    .embed .record .time {
      font-size: inherit;
    }

    .embed .play {
      padding: 0 var(--space-4) 0 var(--space-3);
    }

    .embed .quiet {
      padding: 0 var(--space-3);
    }

    .embed .notes,
    .embed .words,
    .embed :global(.legend) {
      font-size: var(--text-label);
      line-height: 1.4;
    }
  }
</style>
