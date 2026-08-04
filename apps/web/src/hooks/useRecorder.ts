/**
 * Microphone recording, via MediaRecorder.
 *
 * Deliberately small: start, stop, elapsed, and the resulting Blob. Codec
 * choice is left to the browser because Safari and Chrome disagree, and the
 * backend accepts whatever either produces.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "denied" | "unsupported";

// First match wins. Safari only does mp4; Chrome and Firefox prefer webm.
const CANDIDATES = ["audio/webm", "audio/mp4", "audio/ogg"];

function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  return CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

export function useRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  // Why it failed, so the operator can act on it: a blocked permission and
  // a missing microphone need different fixes.
  const [reason, setReason] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const start = useCallback(async () => {
    const mimeType = pickMimeType();
    if (!mimeType || !navigator.mediaDevices?.getUserMedia) {
      setReason(
        window.isSecureContext
          ? "This browser can't record audio."
          : "Recording needs a secure connection (https, or localhost).",
      );
      setState("unsupported");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      const name = error instanceof DOMException ? error.name : "";
      setReason(
        name === "NotAllowedError"
          ? "Microphone permission was denied. Allow it in your browser's site settings."
          : name === "NotFoundError"
            ? "No microphone was found."
            : name === "NotReadableError"
              ? "The microphone is in use by another app."
              : `Could not open the microphone${name ? ` (${name})` : ""}.`,
      );
      setState("denied");
      return;
    }

    const recorder = new MediaRecorder(stream, { mimeType });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.start();

    streamRef.current = stream;
    recorderRef.current = recorder;
    setSeconds(0);
    setReason(null);
    setState("recording");
    timerRef.current = window.setInterval(() => setSeconds((s) => s + 1), 1000);
  }, []);

  /** Stop and resolve the recording, or null if nothing was captured. */
  const stop = useCallback(async (): Promise<{ blob: Blob; filename: string } | null> => {
    const recorder = recorderRef.current;
    if (!recorder) return null;

    const finished = new Promise<Blob>((resolve) => {
      recorder.onstop = () =>
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType }));
    });
    recorder.stop();
    const blob = await finished;

    cleanup();
    setState("idle");

    if (blob.size === 0) return null;
    const extension = recorder.mimeType.includes("mp4") ? "mp4" : "webm";
    return { blob, filename: `note.${extension}` };
  }, [cleanup]);

  const cancel = useCallback(() => {
    recorderRef.current?.stop();
    chunksRef.current = [];
    cleanup();
    setState("idle");
  }, [cleanup]);

  return { state, seconds, reason, start, stop, cancel };
}
