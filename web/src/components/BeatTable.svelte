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
          <td class="mono">{row.probability}</td>
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
    gap: var(--space-2);
  }

  table {
    width: 100%;
    max-width: 40rem;
    border-collapse: collapse;
  }

  caption {
    margin-bottom: var(--space-2);
    color: var(--color-muted);
    text-align: start;
  }

  th {
    padding: var(--space-1) var(--space-3) var(--space-1) 0;
    border-bottom: 1px solid var(--color-hairline);
    color: var(--color-muted);
    font-weight: 600;
    text-align: start;
    vertical-align: bottom;
  }

  td {
    padding: var(--space-1) var(--space-3) var(--space-1) 0;
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

  .differ td:last-child {
    font-weight: 600;
  }

  .note {
    max-width: 66ch;
    margin: 0;
    color: var(--color-muted);
  }
</style>
