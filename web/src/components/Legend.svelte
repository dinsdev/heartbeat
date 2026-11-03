<script lang="ts">
  let { compact = false }: { compact?: boolean } = $props();

  const classes = [
    { letter: "N", name: "Normal", token: "--hb-class-n" },
    { letter: "S", name: "Supraventricular early beat", token: "--hb-class-s" },
    { letter: "V", name: "Ventricular early beat", token: "--hb-class-v" },
    { letter: "F", name: "Fusion beat", token: "--hb-class-f" },
  ];
</script>

<ul class="legend t-small" class:compact aria-label="What the marks mean">
  {#each classes as item (item.letter)}
    <li>
      <span class="letter" style:color={`var(${item.token})`}
        >{item.letter}</span
      >
      {compact ? item.name.replace(/ (early )?beat$/, "") : item.name}
    </li>
  {/each}
  <li><span class="dash" aria-hidden="true"></span>Not scored</li>
  <li>
    <span class="ring" aria-hidden="true">N</span>
    {compact
      ? "Disagrees with the experts"
      : "Model and experts disagree; the experts' letter is beneath"}
  </li>
  {#if !compact}
    <li><span class="pending" aria-hidden="true"></span>Label not known yet</li>
  {/if}
</ul>

<style>
  /* The full key is a tidy two-column list; the embed's runs inline. */
  .legend {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
    gap: var(--space-2) var(--space-5);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .compact {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
  }

  li {
    display: inline-flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
  }

  li > span {
    flex: none;
    align-self: center;
  }

  /* Marks in a fixed column so the names line up. */
  .legend:not(.compact) li {
    display: grid;
    grid-template-columns: 1.5em minmax(0, 1fr);
    align-items: center;
  }

  .legend:not(.compact) li > span {
    justify-self: center;
  }

  .letter,
  .ring {
    font-family: var(--font-mono);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .dash {
    width: 0.8em;
    height: 2px;
    background: var(--hb-class-q);
    border-radius: 1px;
  }

  .ring {
    display: inline-grid;
    place-items: center;
    width: 1.5em;
    height: 1.5em;
    border: 1.5px solid var(--hb-class-n);
    border-radius: 50%;
    color: var(--hb-class-n);
    font-size: 0.8em;
  }

  .pending {
    width: 0.45em;
    height: 0.45em;
    border: 1px solid var(--color-muted);
    border-radius: 50%;
    opacity: 0.7;
  }
</style>
