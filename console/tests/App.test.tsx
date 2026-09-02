/**
 * What the shell promises before there is anything to show.
 *
 * An empty console has to read as *waiting*, not as broken - it is the first
 * thing a reviewer sees if they open it before starting a run, and a blank page
 * is indistinguishable from a failure.
 */

import { render, screen } from "@testing-library/react";
import { App } from "../src/App";

describe("the console shell", () => {
  it("says plainly that there is no run, rather than looking broken", () => {
    render(<App />);

    expect(screen.getByText(/nothing to work yet/i)).toBeDefined();
    expect(screen.getByText(/no run loaded/i)).toBeDefined();
  });

  it("names the five phases a claim passes through", () => {
    render(<App />);

    for (const phase of ["portal", "analysis", "emr", "appeal", "report"]) {
      expect(screen.getByText(phase)).toBeDefined();
    }
  });
});
