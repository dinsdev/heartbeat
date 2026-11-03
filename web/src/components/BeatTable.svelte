<script lang="ts">
  import type { BeatRow } from "../lib/summary";

  interface Props {
    rows: BeatRow[];
    /** The span the rows cover, as text, such as "0:20 to 0:30". */
    span: string;
  }

  let { rows, span }: Props = $props();

  const TOKENS: Record<string, string> = {
    N: "--hb-class-n",
    S: "--hb-class-s",
    V: "--hb-class-v",
    F: "--hb-class-f",
    Q: "--hb-class-q",
  };

  /** The probability as a 0 to 1 fill for its bar ("under 1%" draws a sliver). */
  function fill(probability: string): number {
    if (probability.startsWith("under")) return 0.005;
    return (Number.parseFloat(probability) || 0) / 100;
  }
</script>

<!-- DEMO-12: the beats in view as a table, not live-announced (D6). -->
<div class="wrap">
  <table class="t-small">
    <caption class="t-small">Beats in view, {span}</caption>
    <thead>
      <tr>
        <th scope="col">Time</th>
        <th scope="col">Model</th>
        <th scope="col">Estimated probability</th>
        <th scope="col">Experts</th>
        <th scope="col">Match</th>
      </tr>
    </thead>
    <tbody>
      {#each rows as row (row.row)}
        <tr class:differ={row.match === "No"}>
          <td class="mono">{row.time}</td>
          <td
            class="mono letter"
            style:color={`var(${TOKENS[row.model] ?? "--color-muted"})`}
            >{row.model}</td
          >
          <td class="mono">
            <span class="probability">
              <span class="value">{row.probability}</span>
              {#if row.probability}
                <span class="bar" aria-hidden="true"
                  ><span class="bar-fill" style:--p={fill(row.probability)}
                  ></span></span
                >
              {/if}
            </span>
          </td>
          <td class="mono letter" style:color={`var(${TOKENS[row.expert]})`}
            >{row.expert}</td
          >
          <td>{row.match}</td>
        </tr>
      {:else}
        <tr><td colspan="5">No beats in this span</td></tr>
      {/each}
    </tbody>
  </table>
  <p class="note t-small">
    The first and last beats of each recording have no label: the model reads
    the gap to the beat before and after each one.
  </p>
</div>

<style>
  .wrap {
    display: grid;
    gap: var(--space-3);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  caption {
    margin-bottom: var(--space-3);
    color: var(--color-ink);
    font-weight: 600;
    text-align: start;
  }

  th {
    padding: var(--space-2) var(--space-4) var(--space-2) var(--space-2);
    border-bottom: 1px solid var(--color-line);
    color: var(--color-muted);
    font: var(--text-label-weight) var(--text-label) / var(--text-label-lh)
      var(--font-mono);
    letter-spacing: var(--text-label-tracking);
    text-align: start;
    text-transform: uppercase;
    vertical-align: bottom;
  }

  td {
    padding: var(--space-2) var(--space-4) var(--space-2) var(--space-2);
    border-bottom: 1px solid var(--color-hairline);
    color: var(--color-ink);
  }

  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  .letter {
    font-weight: 600;
  }

  .probability {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
  }

  .value {
    min-width: 4.5ch;
  }

  /* The estimated probability as a short bar, read beside the number. */
  .bar {
    position: relative;
    width: clamp(3.5rem, 12vw, 8rem);
    height: 4px;
    overflow: hidden;
    border-radius: var(--radius-pill);
    background: var(--color-hairline);
  }

  .bar-fill {
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: var(--color-muted);
    transform: scaleX(var(--p, 0));
    transform-origin: left;
  }

  /* No tint on the row: the S color would drop under 4.5:1 on it. */
  .differ td:last-child {
    color: var(--hb-class-v);
    font-weight: 600;
  }

  .note {
    max-width: 66ch;
    margin: 0;
    color: var(--color-muted);
  }

  /* Phones: the bar gives way so the five columns fit. */
  @media (max-width: 520px) {
    .bar {
      display: none;
    }

    th,
    td {
      padding-inline: var(--space-1) var(--space-2);
    }
  }
</style>
