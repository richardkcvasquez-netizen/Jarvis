import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Mic, MicOff, PhoneOff } from "lucide-react";

import { VoiceGlow } from "@/components/home/VoiceGlow";
import { LookSlot } from "@/components/looks/LookSlot";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { VoiceState } from "@/store/events";

/**
 * A running call as the assistant's look alone (orb-only call view).
 *
 * The whole window goes dark around the look: no words, no pet, no header.
 * What the call is doing is still said to screen readers. The microphone
 * switch and the hang-up stay reachable without being seen: they come up when
 * the pointer moves over the foot of the window or a key focuses them, and
 * Escape hangs up.
 */
export function CallOrbStage({ state, status, label, active, busy, muted, live, onHangUp, onToggleMute }: {
  state: VoiceState;
  status: string;
  label: string;
  active: boolean;
  busy: boolean;
  muted: boolean;
  live: boolean;
  onHangUp: () => void;
  onToggleMute: () => void;
}) {
  const t = useT();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && active && !busy) onHangUp();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, busy, onHangUp]);

  return createPortal(
    <section data-testid="call-orb-stage" data-state={state} role="region" aria-label={label}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black">
      <p className="sr-only" data-testid="call-status" aria-live="polite">{status}</p>
      <LookSlot state={state} className="h-[min(82vh,82vw)] w-[min(82vh,82vw)]">
        <VoiceGlow active={active} thinking={state === "thinking" || state === "connecting"} className="h-full" />
      </LookSlot>
      <footer className="group absolute inset-x-0 bottom-0 flex h-28 items-end justify-center gap-4 pb-6">
        <button type="button" onClick={onToggleMute} disabled={!live} aria-pressed={muted} data-testid="call-mute"
          aria-label={muted ? t("home.call.unmute") : t("home.call.mute")} title={muted ? t("home.call.unmute") : t("home.call.mute")}
          className={cn(
            "inline-flex h-11 w-11 items-center justify-center rounded-full opacity-0 transition-opacity duration-300 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none",
            muted ? "bg-foreground text-background" : "bg-white/10 text-white",
          )}>
          {muted ? <MicOff className="h-[18px] w-[18px]" aria-hidden /> : <Mic className="h-[18px] w-[18px]" aria-hidden />}
        </button>
        <button type="button" onClick={onHangUp} disabled={busy || !active} data-testid="call-hang-up"
          aria-label={t("agentic_grid.voice_bubble.hang_up_title")} title={t("agentic_grid.voice_bubble.hang_up_title")}
          className="inline-flex h-11 w-16 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 transition-opacity duration-300 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none">
          <PhoneOff className="h-[18px] w-[18px]" aria-hidden />
        </button>
      </footer>
    </section>,
    document.body,
  );
}
