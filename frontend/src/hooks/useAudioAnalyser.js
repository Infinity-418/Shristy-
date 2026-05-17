import { useRef, useState, useCallback, useEffect } from "react";

/**
 * useAudioAnalyser
 * 
 * Returns { analyserNode, audioContext, connectAudio, resumeAudioContext }
 * Call connectAudio(audioElement) right before you play TTS audio.
 * Pass analyserNode and audioContext into <Avatar />.
 */
export function useAudioAnalyser() {
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  
  // Use state to trigger re-renders so that parent component gets the values when initialized
  const [analyserNode, setAnalyserNode] = useState(null);
  const [audioContext, setAudioContext] = useState(null);

  const getOrCreateContext = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        audioContextRef.current = ctx;
        setAudioContext(ctx);
      }
    }
    return audioContextRef.current;
  }, []);

  const resumeAudioContext = useCallback(async () => {
    const ctx = getOrCreateContext();
    if (ctx && ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch (_) {}
    }
  }, [getOrCreateContext]);

  // Global unlock on user gesture
  useEffect(() => {
    const unlock = () => {
      resumeAudioContext();
    };
    window.addEventListener("click", unlock, { passive: true });
    window.addEventListener("keydown", unlock, { passive: true });
    window.addEventListener("touchstart", unlock, { passive: true });
    return () => {
      window.removeEventListener("click", unlock);
      window.removeEventListener("keydown", unlock);
      window.removeEventListener("touchstart", unlock);
    };
  }, [resumeAudioContext]);

  const connectAudio = useCallback((audioElement) => {
    if (!audioElement) return;

    const ctx = getOrCreateContext();
    if (!ctx) return;

    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }

    // Create analyser once
    if (!analyserRef.current) {
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;
      analyserRef.current = analyser;
      setAnalyserNode(analyser);
    }

    const analyser = analyserRef.current;

    // Wire: audioElement -> analyser -> speakers (only once to avoid DOMException)
    if (!sourceRef.current) {
      try {
        const source = ctx.createMediaElementSource(audioElement);
        source.connect(analyser);
        analyser.connect(ctx.destination);
        sourceRef.current = source;
      } catch (err) {
        console.warn("createMediaElementSource warning:", err);
      }
    }
  }, [getOrCreateContext]);

  return {
    analyserNode,
    audioContext,
    connectAudio,
    resumeAudioContext,
  };
}
