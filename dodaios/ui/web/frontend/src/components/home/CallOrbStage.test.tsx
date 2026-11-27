/**
 * A running call shows the assistant's look alone: the whole window goes dark
 * around it, with no words, no pet and no buttons in sight. The controls are
 * still there for whoever needs them: they come up on hover or focus, and
 * Escape hangs up.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CallWindow } from "@/components/home/CallWindow";
import { useCallView } from "@/store/callView";
import { useEventStore } from "@/store/events";
import { useHomeStore } from "@/store/home";

describe("orb-only call", () => {
  let stopped = 0;
  beforeEach(() => {
    stopped = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/voice/hangup")) stopped += 1;
      return new Response(JSON.stringify({ stopped: true, muted: false }));
    }));
    useCallView.setState({ orbOnly: true });
    useEventStore.setState({ voiceState: "speaking", assistantName: "Jarvis", transcription: "", transcriptionFinal: true });
    useHomeStore.setState({
      transcript: [
        { id: "u1", who: "user", text: "What's the weather like today?", ts: 1 },
        { id: "a1", who: "assistant", text: "Cool and clear, sir.", ts: 2 },
      ] as never,
      liveReply: "",
      callPending: false,
      callProblem: null,
    });
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the look alone, over the whole window", () => {
    render(<CallWindow composerControls />);
    const stage = screen.getByTestId("call-orb-stage");
    expect(stage.parentElement).toBe(document.body);
    expect(stage.querySelector("[data-testid='voice-glow']")).toBeTruthy();
    expect(screen.queryByTestId("call-transcript")).toBeNull();
    expect(screen.queryByTestId("call-waiting")).toBeNull();
    expect(stage.textContent).not.toContain("Cool and clear");
    expect(stage.textContent).not.toContain("weather");
  });

  it("keeps the state for screen readers without showing it", () => {
    render(<CallWindow composerControls />);
    const status = screen.getByTestId("call-status");
    expect(status.textContent).toContain("Speaking");
    expect(status.className).toContain("sr-only");
  });

  it("hangs up on Escape", async () => {
    render(<CallWindow composerControls />);
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(stopped).toBe(1));
  });

  it("still offers the old window to whoever turned orb-only off", () => {
    useCallView.setState({ orbOnly: false });
    render(<CallWindow composerControls />);
    expect(screen.queryByTestId("call-orb-stage")).toBeNull();
    expect(screen.getByTestId("call-transcript")).toBeTruthy();
  });
});
