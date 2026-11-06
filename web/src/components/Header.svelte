<script lang="ts">
  import lockupDark from "../../vendor/brand/lockup-dark.svg?url";
  import lockupLight from "../../vendor/brand/lockup-light.svg?url";
</script>

<header class="header">
  <a class="home rise" href="https://dins.dev">
    <img
      class="lockup light"
      src={lockupLight}
      alt="dins"
      width="130"
      height="32"
    />
    <img
      class="lockup dark"
      src={lockupDark}
      alt="dins"
      width="130"
      height="32"
    />
  </a>
  <div class="hero">
    <h1 class="t-display title rise rise-text rise-1">Heartbeat</h1>
    <p class="t-lead lead rise rise-text rise-1">
      I trained a small neural network to label heartbeats in ECG recordings.
      Here it labels a real recording live, in your browser.
    </p>
  </div>
</header>

<style>
  .header {
    padding-block: var(--space-5) var(--space-6);
  }

  .home {
    display: inline-block;
    border-radius: var(--radius-sm);
  }

  .lockup {
    display: block;
    height: 32px;
    width: auto;
  }

  .dark {
    display: none;
  }

  @media (prefers-color-scheme: dark) {
    :global(:root:not([data-theme="light"])) .light {
      display: none;
    }
    :global(:root:not([data-theme="light"])) .dark {
      display: block;
    }
  }

  :global(:root[data-theme="dark"]) .light {
    display: none;
  }

  :global(:root[data-theme="dark"]) .dark {
    display: block;
  }

  /* Title and lead share a baseline row on wide screens, stacked on phones. */
  .hero {
    display: grid;
    gap: var(--space-3) var(--space-7);
    margin-top: clamp(var(--space-6), 6vw, var(--space-8));
  }

  @media (min-width: 860px) {
    .hero {
      grid-template-columns: auto minmax(0, 1fr);
      align-items: end;
    }
  }

  .title {
    margin: 0;
  }

  .lead {
    margin: 0;
    max-width: 46ch;
    padding-bottom: 0.35em;
    text-wrap: pretty;
  }
</style>
