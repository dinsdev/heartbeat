<script lang="ts">
  import { onMount } from "svelte";

  import type { RecordBeats } from "../lib/data/beats";
  import type { LabelStore } from "../lib/parity";
  import type { PlaybackClock } from "../lib/playback/clock";
  import { SPAN_S } from "../lib/trace/geometry";
  import { markersInView } from "../lib/trace/markers";
  import { readColors, TraceRenderer } from "../lib/trace/renderer";

  interface Props {
    trace: Int16Array;
    beats: RecordBeats;
    store: LabelStore;
    fs: number;
    clock: PlaybackClock;
    /** Bumped by the panel to redraw once (play, pause, new labels). */
    redraw: number;
    /** The embed fills its box; the full page keeps a minimum height. */
    fill?: boolean;
    label: string;
    onframe: (positionS: number) => void;
  }

  let {
    trace,
    beats,
    store,
    fs,
    clock,
    redraw,
    fill = false,
    label,
    onframe,
  }: Props = $props();

  let wrapper: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let request: () => void = () => undefined;

  // Design call 5: a minimum height for narrow screens, where the nominal
  // 50 mm strip would be under 70 px tall. The scale stays 10 mm per mV.
  const MIN_HEIGHT_PX = 180;

  onMount(() => {
    let renderer: TraceRenderer;
    try {
      renderer = new TraceRenderer(canvas, MIN_HEIGHT_PX);
    } catch {
      return;
    }
    let raf = 0;
    let paper = "";
    const theme = () => {
      renderer.setColors(readColors(canvas));
      paper = getComputedStyle(canvas).getPropertyValue("--color-paper").trim();
    };
    const size = () => {
      const width = wrapper.clientWidth;
      if (width === 0) return;
      const height = fill ? wrapper.clientHeight : 0;
      renderer = renderer.withMinHeight(
        fill ? Math.max(height, 120) : MIN_HEIGHT_PX,
      );
      renderer.resize(width, window.devicePixelRatio || 1);
      request();
    };
    const frame = () => {
      raf = 0;
      const position = clock.position();
      const playhead = Math.round(position * fs);
      const start = playhead - SPAN_S * fs;
      renderer.draw(
        {
          trace,
          fs,
          startSample: start,
          markers: markersInView(beats, store, start, playhead, playhead),
        },
        paper,
      );
      onframe(position);
      // Design call 6: the loop runs only while playing and visible.
      if (clock.playing && !document.hidden) raf = requestAnimationFrame(frame);
    };
    request = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    theme();
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => {
      theme();
      request();
    };
    scheme.addEventListener("change", onScheme);
    const observer = new ResizeObserver(size);
    observer.observe(wrapper);
    const onVisible = () => request();
    document.addEventListener("visibilitychange", onVisible);
    size();
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      scheme.removeEventListener("change", onScheme);
      document.removeEventListener("visibilitychange", onVisible);
    };
  });

  $effect(() => {
    void redraw;
    request();
  });
</script>

<div class="trace" class:fill bind:this={wrapper} role="img" aria-label={label}>
  <canvas bind:this={canvas} aria-hidden="true"></canvas>
</div>

<style>
  .trace {
    position: relative;
    width: 100%;
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: inset 0 0 0 1px var(--color-hairline);
    /* Settling 7 arrives in Goal B; vertical page scrolling stays native. */
    touch-action: pan-y;
  }

  .fill {
    height: 100%;
    min-height: 0;
  }

  canvas {
    display: block;
    width: 100%;
  }
</style>
