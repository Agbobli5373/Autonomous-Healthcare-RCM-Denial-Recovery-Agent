/**
 * How each Action is written on screen.
 *
 * `Record<Action, ...>` rather than `Record<string, ...>`: a sixth Action added
 * to the glossary should not compile until every place that renders one has
 * been told about it. Two characters for a row, where the column must not become
 * the widest thing in it; the full name where there is room to read it.
 */

import type { Action } from "./claims";

export const ACTIONS: Record<Action, { abbreviation: string; title: string }> = {
  appeal: { abbreviation: "AP", title: "Appeal" },
  corrected_claim: { abbreviation: "CC", title: "Corrected claim" },
  rebill: { abbreviation: "RB", title: "Rebill" },
  patient_bill: { abbreviation: "PB", title: "Patient bill" },
  close: { abbreviation: "CL", title: "Close" },
};
