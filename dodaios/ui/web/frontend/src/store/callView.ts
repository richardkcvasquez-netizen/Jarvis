/**
 * How a running call looks in this window: the assistant's look alone
 * (orb-only, the default), or the call window with its words and buttons.
 *
 * A per-window preference, kept in the browser's own storage like the app
 * zoom; storage that cannot be read or written leaves the default in place.
 */
import { create } from "zustand";

export const CALL_VIEW_STORAGE_KEY = "dodaios.callView.v1";

function readOrbOnly(): boolean {
  try {
    const raw = window.localStorage.getItem(CALL_VIEW_STORAGE_KEY);
    if (!raw) return true;
    const parsed = JSON.parse(raw) as { orbOnly?: unknown };
    return typeof parsed.orbOnly === "boolean" ? parsed.orbOnly : true;
  } catch {
    return true; // unreadable storage keeps the default view
  }
}

interface CallViewState {
  orbOnly: boolean;
  setOrbOnly: (orbOnly: boolean) => void;
}

export const useCallView = create<CallViewState>((set) => ({
  orbOnly: readOrbOnly(),
  setOrbOnly: (orbOnly) => {
    set({ orbOnly });
    try {
      window.localStorage.setItem(CALL_VIEW_STORAGE_KEY, JSON.stringify({ orbOnly }));
    } catch {
      // storage refused: the choice holds for this window until it reloads
    }
  },
}));
