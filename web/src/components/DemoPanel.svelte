<script lang="ts">
  import { onMount, untrack } from "svelte";

  import type { RecordBeats } from "../lib/data/beats";
  import type { Manifest, RecordEntry } from "../lib/data/manifest";
  import { clockTenths, clockTime, count } from "../lib/format";
  import type { LabelingSession } from "../lib/labeling";
  import { splitNotes } from "../lib/notes";
  import type { ParityCounts } from "../lib/parity";
  import { PlaybackClock, SPEEDS } from "../lib/playback/clock";
  import {
    jumpTarget,
    nextDisagreement,
    nextIrregular,
    searchFrom,
  } from "../lib/playback/jumps";
  import { pageEnd, stepPage } from "../lib/playback/pages";
  import { beatBetween } from "../lib/playback/pulse";
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
  // Design call 7: DS1 shows the training-patient note, DS2 DEMO-09's line.
  const notes = $derived(splitNotes(manifest));
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
  // The beat dot pulses as each annotated beat passes the playhead.
  let beatDot = $state<HTMLSpanElement>();
  let lastPulse = -1;

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
  // How far along the slider's track is filled, as a percentage.
  const progress = $derived(
    Math.min(
      100,
      Math.max(
        0,
        ((shownSecond - SPAN_S) / Math.max(1, Math.floor(duration) - SPAN_S)) *
          100,
      ),
    ),
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

  /** One pulse per beat while playing; never on a seek or under reduced motion. */
  function pulse(position: number) {
    const now = Math.round(position * fs);
    const from = lastPulse;
    lastPulse = now;
    if (!clock.playing || reducedMotion || !beatDot?.animate) return;
    if (from < 0 || now - from > fs || !beatBetween(beats.samples, from, now))
      return;
    beatDot.animate(
      [
        { transform: "scale(1.5)", opacity: 1 },
        { transform: "scale(1)", opacity: 1 },
      ],
      { duration: 360, easing: "cubic-bezier(0.23, 1, 0.32, 1)" },
    );
  }

  function onframe(position: number, viewEnd: number) {
    pulse(position);
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
  <div class="card">
    {#if !embed}
      <div class="head">
        <p class="t-data head-record">
          Record {record}<span class="scale">25 mm/s, 10 mm/mV</span>
        </p>
        <p class="t-data head-time">
          {@render dot()}
          {@render playhead()}
        </p>
      </div>
    {/if}

    <div class="strip appear" data-view-end={viewEndSecond}>
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
      <div class="transport">
        <button
          class="play"
          type="button"
          aria-pressed={playing}
          onclick={toggle}
        >
          <span class="icons" class:playing aria-hidden="true">
            <svg class="icon icon-play" viewBox="0 0 16 16">
              <path
                d="M5 3.2v9.6a.8.8 0 0 0 1.2.7l7.6-4.8a.8.8 0 0 0 0-1.4L6.2 2.5A.8.8 0 0 0 5 3.2Z"
              />
            </svg>
            <svg class="icon icon-pause" viewBox="0 0 16 16">
              <rect x="3.5" y="2.5" width="3" height="11" rx="1" />
              <rect x="9.5" y="2.5" width="3" height="11" rx="1" />
            </svg>
          </span>
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
      </div>
      <div class="jumps">
        <button class="quiet" type="button" onclick={() => jump("irregular")}
          >Next irregular beat</button
        >
        <button class="quiet" type="button" onclick={() => jump("disagreement")}
          >Next disagreement</button
        >
      </div>
      {#if embed}
        <p class="t-data record">
          Record {record}
          {@render dot()}{@render playhead()}
        </p>
      {/if}
    </div>

    {#if !embed}
      <div class="where">
        <label class="field t-small">
          Recording
          <select value={record} onchange={pick}>
            {#each manifest.records as option (option.record)}
              <option value={option.record}>{recordOption(option)}</option>
            {/each}
          </select>
        </label>
        <input
          class="scrub"
          type="range"
          aria-label="Position"
          aria-valuetext={timeText}
          min={SPAN_S}
          max={Math.floor(duration)}
          step="5"
          value={sliding ? undefined : shownSecond}
          style:--progress={`${progress}%`}
          oninput={onslide}
          onpointerdown={() => (sliding = true)}
          onchange={() => (sliding = false)}
        />
      </div>
    {/if}
  </div>

  {#snippet playhead()}
    <span class="time t-data" data-testid="playhead" data-seconds={shownSecond}
      >{timeText}</span
    >
  {/snippet}

  {#snippet dot()}
    <span class="beat" class:on={playing} aria-hidden="true"
      ><span class="beat-core" bind:this={beatDot}></span></span
    >
  {/snippet}

  <div class="readout">
    <div class="words t-small">
      <p class="counter" data-state={modelState}>
        <span class="state" aria-hidden="true">
          {#if modelState === "ready"}
            <svg class="check" viewBox="0 0 16 16">
              <circle cx="8" cy="8" r="6.5" />
              <path d="m5.2 8.2 1.9 1.9 3.8-4" />
            </svg>
          {:else if modelState === "loading"}
            <span class="spinner"></span>
          {:else}
            <svg class="info" viewBox="0 0 16 16">
              <circle cx="8" cy="8" r="6.5" />
              <path d="M8 7.2v3.6M8 5.2v.1" />
            </svg>
          {/if}
        </span>
        <span>
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
        </span>
      </p>
      {#if !embed}
        <!-- DEMO-12; the embed's compact set leaves it out (settling 5). -->
        <p class="summary" role="status" data-testid="summary">{summary}</p>
      {/if}
      <p class="jump" role="status" data-testid="jump-note">{jumpNote}</p>
    </div>

    <Legend compact={embed} />
  </div>

  <div class="notes t-small">
    <p class="d7">{D7_LINE}</p>
    {#each notes as note (note.kind)}
      <p class={note.kind} data-testid="{note.kind}-note">{note.text}</p>
    {/each}
    {#if embed}
      <p>
        <a class="full" href={fullHref} target="_blank" rel="noopener"
          >Open the full demo</a
        >
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
    /* minmax(0, ...): a long recording name never widens the page. */
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-5);
  }

  /* The instrument: the strip with its readout above and its controls below,
     on one raised surface. */
  .card {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-4);
    padding: var(--space-4);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    /* No shadow in light, here or on the controls: WebKit painting in software
       (Linux) spent long enough on them to fail R38 (ledger, 2026-11-05). */
    box-shadow: var(--hb-card-edge);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-1) var(--space-4);
    padding-inline: var(--space-1);
  }

  .head p {
    margin: 0;
  }

  .head-record {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-3);
    color: var(--color-ink);
    font-weight: 500;
  }

  .scale {
    color: var(--color-muted);
    font-weight: 400;
  }

  .head-time {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  /* The beat dot: teal while playing, it swells once per beat. */
  .beat {
    display: inline-grid;
    place-items: center;
    width: 12px;
    height: 12px;
  }

  .beat-core {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--color-muted);
    opacity: 0.45;
    transition:
      background-color var(--motion-base) ease,
      opacity var(--motion-base) ease;
  }

  .beat.on .beat-core {
    background: var(--color-accent);
    opacity: 1;
  }

  .strip {
    --trace-radius: var(--radius-md);
    min-width: 0;
  }

  .bar,
  .where {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3) var(--space-4);
  }

  .bar {
    justify-content: space-between;
  }

  .transport,
  .jumps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }

  .where .field {
    max-width: 100%;
  }

  .where {
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-hairline);
  }

  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    min-height: 40px;
    border-radius: var(--radius-pill);
    font: 600 var(--text-small) / 1 var(--font-text);
    cursor: pointer;
    /* The press responds at once; colors ease. */
    transition:
      transform 120ms var(--hb-ease-out),
      background-color var(--motion-fast) ease,
      border-color var(--motion-fast) ease;
  }

  button:active {
    transform: scale(0.97);
  }

  .play {
    /* Wide enough for "Pause", so the bar never shifts on press. */
    min-width: 6.75rem;
    padding: 0 var(--space-5) 0 var(--space-4);
    border: 0;
    background: var(--color-accent);
    color: var(--color-paper);
  }

  .quiet {
    padding: 0 var(--space-4);
    border: 1px solid var(--color-hairline);
    background: transparent;
    color: var(--color-ink);
  }

  @media (hover: hover) and (pointer: fine) {
    .play:hover {
      filter: brightness(1.08);
    }

    .quiet:hover {
      border-color: var(--color-muted);
      background: var(--color-accent-soft);
    }
  }

  /* Play and pause share a box and trade places with a short scale and fade.
     No blur: WebKit painting in software (Linux) spent up to 1.7 s on one
     frame of a blur transition (ledger, 2026-11-03). */
  .icons {
    display: grid;
    width: 14px;
    height: 14px;
  }

  .icon {
    grid-area: 1 / 1;
    width: 14px;
    height: 14px;
    fill: currentColor;
    transition:
      opacity 160ms var(--hb-ease-out),
      transform 160ms var(--hb-ease-out);
  }

  .icon-pause,
  .playing .icon-play {
    opacity: 0;
    transform: scale(0.6);
  }

  .playing .icon-pause {
    opacity: 1;
    transform: none;
  }

  .field {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    color: var(--color-muted);
  }

  /* Drawn, not native: WebKit keeps a native select near 23 px tall whatever
     its min-height, under WCAG 2.5.8's 24 px. The chevron is two gradients. */
  select {
    appearance: none;
    min-width: 0;
    min-height: 32px;
    max-width: 100%;
    padding: 0 calc(var(--space-2) + 18px) 0 var(--space-3);
    border: 1px solid var(--color-hairline);
    border-radius: var(--radius-md);
    background:
      linear-gradient(45deg, transparent 50%, currentColor 50%) no-repeat
        calc(100% - 16px) 55% / 5px 5px,
      linear-gradient(135deg, currentColor 50%, transparent 50%) no-repeat
        calc(100% - 11px) 55% / 5px 5px,
      var(--color-paper);
    color: var(--color-ink);
    font: inherit;
    text-overflow: ellipsis;
    cursor: pointer;
    transition: border-color var(--motion-fast) ease;
  }

  @media (hover: hover) and (pointer: fine) {
    select:hover {
      border-color: var(--color-muted);
    }
  }

  /* The open list in the page's own materials where the browser allows it
     (customizable select); elsewhere the system menu, as before. Still a
     real select, so keys, labels and form behavior are the browser's. */
  @supports (appearance: base-select) {
    select,
    select::picker(select) {
      appearance: base-select;
    }

    select {
      align-items: center;
      font-variant-numeric: tabular-nums;
    }

    /* Sized to the chosen text here, not the longest option as natively, so
       the width is fixed and the slider stays put: a floor that fits the
       longest record line, or the full row on a phone. */
    @media (min-width: 30rem) {
      .where select {
        min-inline-size: 20rem;
      }
    }

    @media (max-width: 29.99rem) {
      .where .field {
        flex: 1 1 100%;
      }

      .where select {
        flex: 1;
      }
    }

    select::picker-icon {
      display: none;
    }

    select:open {
      border-color: var(--color-accent);
    }

    select::picker(select) {
      max-block-size: min(22rem, 60dvh);
      margin-block: var(--space-1);
      padding: var(--space-1);
      border: 1px solid var(--color-hairline);
      border-radius: var(--radius-md);
      background: var(--color-surface);
      color: var(--color-ink);
      transform-origin: top center;
    }

    option {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      min-block-size: 32px;
      padding: var(--space-1) var(--space-3) var(--space-1) var(--space-2);
      border-radius: var(--radius-sm);
      white-space: nowrap;
      cursor: pointer;
    }

    option::checkmark {
      content: "";
      inline-size: 6px;
      block-size: 6px;
      border-radius: var(--radius-pill);
      background: var(--color-accent);
    }

    option:not(:checked)::checkmark {
      visibility: hidden;
    }

    option:checked {
      font-weight: 500;
    }

    option:focus-visible {
      outline: 2px solid var(--color-accent);
      outline-offset: -2px;
      background: var(--color-accent-soft);
    }

    @media (hover: hover) and (pointer: fine) {
      option:hover {
        background: var(--color-accent-soft);
      }
    }

    @media (prefers-reduced-motion: no-preference) {
      select::picker(select) {
        transition:
          opacity 160ms var(--hb-ease-out),
          transform 160ms var(--hb-ease-out);
      }

      @starting-style {
        select:open::picker(select) {
          opacity: 0;
          transform: translateY(-4px) scale(0.98);
        }
      }
    }
  }

  .record {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    color: var(--color-muted);
  }

  .time {
    color: var(--color-ink);
    white-space: nowrap;
  }

  /* The slider: a hairline track that fills teal up to the playhead. */
  .scrub {
    --track: 4px;
    --thumb: 16px;
    flex: 1 1 16rem;
    min-width: 0;
    min-height: 24px;
    margin: 0;
    background: transparent;
    cursor: pointer;
    appearance: none;
  }

  .scrub::-webkit-slider-runnable-track {
    height: var(--track);
    border-radius: var(--radius-pill);
    background: linear-gradient(
      to right,
      var(--color-accent) var(--progress, 0%),
      var(--color-hairline) var(--progress, 0%)
    );
  }

  .scrub::-moz-range-track {
    height: var(--track);
    border-radius: var(--radius-pill);
    background: var(--color-hairline);
  }

  .scrub::-moz-range-progress {
    height: var(--track);
    border-radius: var(--radius-pill);
    background: var(--color-accent);
  }

  .scrub::-webkit-slider-thumb {
    width: var(--thumb);
    height: var(--thumb);
    margin-top: calc((var(--track) - var(--thumb)) / 2);
    border: 2px solid var(--color-surface);
    border-radius: 50%;
    background: var(--color-accent);
    appearance: none;
    transition: transform 120ms var(--hb-ease-out);
  }

  .scrub::-moz-range-thumb {
    width: var(--thumb);
    height: var(--thumb);
    border: 2px solid var(--color-surface);
    border-radius: 50%;
    background: var(--color-accent);
    transition: transform 120ms var(--hb-ease-out);
  }

  .scrub:active::-webkit-slider-thumb {
    transform: scale(1.15);
  }

  .scrub:active::-moz-range-thumb {
    transform: scale(1.15);
  }

  /* Status on the left, the key to the marks on the right. */
  .readout {
    display: grid;
    gap: var(--space-4) var(--space-7);
    align-items: start;
  }

  @media (min-width: 760px) {
    .panel:not(.embed) .readout {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }
  }

  .words {
    display: flex;
    flex-direction: column;
  }

  .words p {
    margin: 0;
    color: var(--color-ink);
  }

  .counter {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
  }

  .state {
    display: inline-grid;
    flex: none;
    place-items: center;
    width: 1.1em;
    height: 1lh;
  }

  .state svg {
    width: 1.1em;
    height: 1.1em;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.5;
  }

  .check {
    stroke: var(--color-accent);
  }

  .info {
    stroke: var(--color-muted);
  }

  /* The check draws itself once, the moment the model is ready. */
  @media (prefers-reduced-motion: no-preference) {
    .check circle {
      stroke-dasharray: 41;
      animation: draw 520ms var(--hb-ease-out) both;
    }

    .check path {
      stroke-dasharray: 9;
      animation: draw 300ms var(--hb-ease-out) 260ms both;
    }

    .spinner {
      animation: spin 800ms linear infinite;
    }
  }

  @keyframes draw {
    from {
      stroke-dashoffset: 41;
    }
    to {
      stroke-dashoffset: 0;
    }
  }

  @keyframes spin {
    to {
      transform: rotate(1turn);
    }
  }

  .spinner {
    width: 0.85em;
    height: 0.85em;
    border: 1.5px solid var(--color-hairline);
    border-top-color: var(--color-accent);
    border-radius: 50%;
  }

  /* Empty live regions stay in the page (so they announce) but take no room. */
  .words p:not(:empty) ~ p:not(:empty) {
    margin-top: var(--space-1);
    padding-inline-start: calc(1.1em + var(--space-2));
  }

  .summary,
  .jump {
    color: var(--color-muted);
  }

  .words .jump:not(:empty) {
    color: var(--color-ink);
  }

  .mismatch {
    color: var(--hb-class-v);
  }

  .notes {
    display: grid;
    gap: var(--space-2);
    padding-top: var(--space-4);
    border-top: 1px solid var(--color-hairline);
  }

  .notes p {
    margin: 0;
    max-width: 66ch;
  }

  /* The amber dot is decoration (BRAND.md: amber is never text on light). */
  .training {
    position: relative;
    padding-inline-start: var(--space-4);
    color: var(--color-ink);
  }

  .training::before {
    content: "";
    position: absolute;
    inset-inline-start: 0;
    top: 0.6em;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--color-amber);
  }

  /* Settling 5: the embed fills the site's box, laid out by container queries.
     It stays flat: the site's own frame is the surface. */
  .embed {
    height: 100%;
    grid-template-rows: minmax(0, 1fr) auto auto;
    gap: var(--space-3);
  }

  .embed .card {
    grid-template-rows: minmax(0, 1fr) auto;
    min-height: 0;
    gap: var(--space-3);
    padding: 0;
    background: none;
    box-shadow: none;
  }

  .embed .strip {
    min-height: 0;
  }

  .embed .readout {
    gap: var(--space-2);
  }

  .embed .notes {
    gap: var(--space-1);
    padding-top: 0;
    border-top: 0;
  }

  /* WCAG 2.5.8: the link is a target of its own, at least 24 px tall. */
  .full {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
  }

  /* A phone: the strip runs nearly edge to edge inside the card. */
  @media (max-width: 520px) {
    .panel:not(.embed) .card {
      margin-inline: calc(var(--space-2) * -1);
      padding: var(--space-3);
    }

    .scale {
      display: none;
    }
  }

  /* A narrow embed (about 4:5 on phones): smaller text, more paper. */
  @container demo (max-width: 480px) {
    .embed {
      gap: var(--space-2);
    }

    .embed .bar,
    .embed .where,
    .embed .transport,
    .embed .jumps {
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
      min-width: 5.5rem;
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
