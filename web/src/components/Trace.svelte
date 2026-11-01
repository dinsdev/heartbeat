<script lang="ts">
  import { onMount } from "svelte";

  import type { RecordBeats } from "../lib/data/beats";
  import type { LabelStore } from "../lib/parity";
  import type { PlaybackClock } from "../lib/playback/clock";
  import { FrameLoop } from "../lib/playback/loop";
  import { pageEnd } from "../lib/playback/pages";
  import { SPAN_S } from "../lib/trace/geometry";
  import { markersInView } from "../lib/trace/markers";
  import { readColors, TraceRenderer } from "../lib/trace/renderer";
  import { Scroller } from "../lib/trace/scroller";

  interface Props {
    trace: Int16Array;
    beats: RecordBeats;
    store: LabelStore;
    fs: number;
    clock: PlaybackClock;
    /** Bumped by the panel to redraw once (play, pause, seek, new labels). */
    redraw: number;
    /** The embed fills its box; the full page keeps a minimum height. */
    fill?: boolean;
    /** Drag to scrub (settling 7): the full page only. */
    scrub?: boolean;
    /** DEMO-14: fixed 10-second pages, no scrolling. */
    reducedMotion?: boolean;
    label: string;
    /** Every frame: the playhead and the view's right edge, in seconds. */
    onframe: (positionS: number, viewEndS: number) => void;
    /** A drag came to rest: the playhead moved by hand. */
    onseek?: () => void;
  }

  let {
    trace,
    beats,
    store,
    fs,
    clock,
    redraw,
    fill = false,
    scrub = false,
    reducedMotion = false,
    label,
    onframe,
    onseek,
  }: Props = $props();

  let wrapper: HTMLDivElement;
  let canvas: HTMLCanvasElement;
  let wake: () => void = () => undefined;
  let scroller: Scroller | undefined;
  let grabbing = $state(false);
  // Playback pauses for a drag and resumes once the paper comes to rest.
  let resume = false;

  // Design call 5: a minimum height for narrow screens, where the nominal
  // 50 mm strip would be under 70 px tall. The scale stays 10 mm per mV.
  const MIN_HEIGHT_PX = 180;

  function makeScroller(reduced: boolean, width: number): Scroller {
    return new Scroller(clock.position(), {
      min: clock.min,
      max: clock.duration,
      pxPerSecond: Math.max(width, 1) / SPAN_S,
      reducedMotion: reduced,
    });
  }

  /** The paper came to rest: playback takes over from where it stopped. */
  function settled() {
    if (!scroller) return;
    clock.seek(scroller.step(performance.now()));
    if (resume) {
      resume = false;
      clock.play();
    }
    onseek?.();
  }

  function onpointerdown(event: PointerEvent) {
    if (!scrub || !scroller || event.button !== 0) return;
    wrapper.setPointerCapture(event.pointerId);
    if (!scroller.active) {
      // Start from where playback is; a coasting paper is caught where it is.
      resume = clock.playing;
      scroller.jumpTo(clock.position());
    }
    clock.pause();
    scroller.down(event.clientX, performance.now());
    grabbing = true;
    wake();
  }

  function onpointermove(event: PointerEvent) {
    if (!scroller?.dragging) return;
    scroller.move(event.clientX, performance.now());
    wake();
  }

  function onpointerup(event: PointerEvent) {
    if (!scroller?.dragging) return;
    if (wrapper.hasPointerCapture(event.pointerId)) {
      wrapper.releasePointerCapture(event.pointerId);
    }
    scroller.up(performance.now());
    grabbing = false;
    // A slow release, or any release under reduced motion, rests at once.
    if (!scroller.active) settled();
    wake();
  }

  onMount(() => {
    let renderer: TraceRenderer;
    try {
      renderer = new TraceRenderer(canvas, MIN_HEIGHT_PX);
    } catch {
      return;
    }
    let paper = "";
    let reduced = reducedMotion;
    scroller = makeScroller(reduced, wrapper.clientWidth);
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
      scroller?.setPxPerSecond(width / SPAN_S);
      wake();
    };
    const frame = (): boolean => {
      if (reduced !== reducedMotion) {
        reduced = reducedMotion;
        scroller = makeScroller(reduced, wrapper.clientWidth);
      }
      let position = clock.position();
      if (scroller?.active) {
        position = scroller.step(performance.now());
        clock.seek(position);
        if (!scroller.active) settled();
      } else {
        scroller?.jumpTo(position);
      }
      const viewEnd = reduced
        ? pageEnd(position, clock.min, clock.duration)
        : position;
      const playhead = Math.round(viewEnd * fs);
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
      onframe(position, viewEnd);
      // Design call 6: frames run only while something moves.
      return clock.playing || Boolean(scroller?.active);
    };
    const loop = new FrameLoop(
      {
        request: (callback) => requestAnimationFrame(callback),
        cancel: (id) => cancelAnimationFrame(id),
        hidden: () => document.hidden,
      },
      frame,
    );
    wake = () => loop.wake();
    theme();
    const scheme = matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => {
      theme();
      wake();
    };
    scheme.addEventListener("change", onScheme);
    const observer = new ResizeObserver(size);
    observer.observe(wrapper);
    const onVisible = () => loop.visibilityChanged();
    document.addEventListener("visibilitychange", onVisible);
    size();
    return () => {
      loop.stop();
      observer.disconnect();
      scheme.removeEventListener("change", onScheme);
      document.removeEventListener("visibilitychange", onVisible);
    };
  });

  $effect(() => {
    void redraw;
    void reducedMotion;
    wake();
  });
</script>

<div
  class="trace"
  class:fill
  class:scrub
  class:grabbing
  bind:this={wrapper}
  role="img"
  aria-label={label}
  {onpointerdown}
  {onpointermove}
  {onpointerup}
  onpointercancel={onpointerup}
>
  <canvas bind:this={canvas} aria-hidden="true"></canvas>
</div>

<style>
  .trace {
    position: relative;
    width: 100%;
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: inset 0 0 0 1px var(--color-hairline);
    /* Settling 7: horizontal drags scrub, vertical page scrolling stays native. */
    touch-action: pan-y;
    user-select: none;
    -webkit-user-select: none;
  }

  .scrub {
    cursor: grab;
  }

  .grabbing {
    cursor: grabbing;
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
