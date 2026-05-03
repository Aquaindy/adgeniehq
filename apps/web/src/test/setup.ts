// Vitest setup. Imports `@testing-library/jest-dom` so matchers like
// `toBeInTheDocument` are available, and stubs a couple of browser APIs
// JSDOM doesn't ship by default but that the app expects.

import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Some components use crypto.randomUUID — JSDOM provides it, but the
// fetch-only frontend tests below that mutate localStorage benefit from a
// fresh slate per run.
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
