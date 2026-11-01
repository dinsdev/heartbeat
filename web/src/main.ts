import "../vendor/brand/tokens.css";
import "./styles/fonts.css";
import "./styles/heartbeat-tokens.css";

import { mount } from "svelte";

import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) {
  throw new Error("index.html has no #app element");
}

export default mount(App, { target });
