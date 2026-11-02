<script lang="ts">
  import lockupDark from "../../vendor/brand/lockup-dark.svg?url";
  import lockupLight from "../../vendor/brand/lockup-light.svg?url";
</script>

<header class="header">
  <a class="home" href="https://dins.dev">
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
  <h1 class="t-h1 title">Heartbeat</h1>
  <p class="t-lead lead">
    I trained a small neural network to label heartbeats in ECG recordings. Here
    it labels a real recording live, in your browser.
  </p>
</header>

<style>
  .header {
    padding-block: var(--space-5) var(--space-5);
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

  .title {
    margin: var(--space-6) 0 var(--space-2);
  }

  .lead {
    margin: 0;
    max-width: 46ch;
  }
</style>
