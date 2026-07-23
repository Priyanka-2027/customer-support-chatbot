// main.tsx
// ─────────────────────────────────────────────────────────────
// Application entry point.
// Mounts the root React component into the DOM.
// This file should stay minimal — no logic lives here.
// ─────────────────────────────────────────────────────────────

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

// document.getElementById("root") targets the <div id="root">
// in index.html — this is where the entire React tree is injected.
//
// The ! (non-null assertion) tells TypeScript that this element
// definitely exists. If it doesn't, React will throw a clear error.
const rootElement = document.getElementById("root")!;

// createRoot() is the React 18 API for concurrent rendering.
// It replaces the older ReactDOM.render() from React 17.
const root = createRoot(rootElement);

root.render(
  // StrictMode renders components twice in development to help
  // detect side effects and deprecated patterns. Has zero impact
  // on production builds — it's a development-only tool.
  <StrictMode>
    <App />
  </StrictMode>
);
