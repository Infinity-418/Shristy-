import { useEffect, useRef, useState } from "react";
import "./Avatar.css";

const MODEL_PATH = "/model/hiyori/hiyori_free_t06.model3.json";
// ^^^ CHANGE THIS to your actual model3.json path after downloading from booth.pm
// Example: "/model/hiyori/hiyori_pro_t02.model3.json"

export default function Avatar({ isSpeaking, analyserNode, audioContext, persona }) {
  const containerRef = useRef(null);
  const appRef = useRef(null);
  const modelRef = useRef(null);
  const animFrameRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);

  // Use refs to prevent stale closures inside the PIXI ticker loop
  const isSpeakingRef = useRef(isSpeaking);
  const analyserNodeRef = useRef(analyserNode);
  const dataArrayRef = useRef(null);

  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  useEffect(() => {
    analyserNodeRef.current = analyserNode;
  }, [analyserNode]);

  useEffect(() => {
    let destroyed = false;

    async function initLive2D() {
      try {
        const PIXI = await import("pixi.js");
        window.PIXI = PIXI;
        const { Live2DModel } = await import("pixi-live2d-display/cubism4");

        // Register ticker for Live2D
        Live2DModel.registerTicker(PIXI.Ticker);

        const app = new PIXI.Application({
          autoStart: true,
          backgroundAlpha: 0,
          width: 420,
          height: 520,
          antialias: true,
          resolution: window.devicePixelRatio || 1,
        });

        if (destroyed) {
          app.destroy(true);
          return;
        }
        appRef.current = app;

        // Apply class name for styling and append it to container
        app.view.classList.add("avatar-canvas");
        app.view.style.opacity = "0";
        app.view.style.transition = "opacity 0.6s ease";
        if (containerRef.current) {
          containerRef.current.appendChild(app.view);
        }

        // Disable autoUpdate so we can manually update the model on every tick
        // after motions have run, ensuring our audio parameter overrides take precedence.
        const model = await Live2DModel.from(MODEL_PATH, {
          autoHitTest: false,
          autoFocus: false,
          autoUpdate: false,
        });

        if (destroyed) {
          app.destroy(true);
          return;
        }
        modelRef.current = model;

        app.stage.addChild(model);

        // Scale and center model to fill canvas (using logical screen dimensions)
        const mWidth = model.width || 1200; // fallback if 0
        const mHeight = model.height || 1400; // fallback if 0
        
        console.log("Live2D Model loaded. Dimensions:", model.width, "x", model.height, "(Using:", mWidth, "x", mHeight, ")");
        console.log("Stage size:", app.screen.width, "x", app.screen.height);

        const scaleX = app.screen.width / mWidth;
        const scaleY = app.screen.height / mHeight;
        let scale = Math.min(scaleX, scaleY) * 0.92;
        
        // Prevent 0, NaN or Infinity scales
        if (!isFinite(scale) || scale <= 0) {
          scale = 0.15;
          console.warn("Invalid scale calculated, falling back to:", scale);
        } else {
          console.log("Calculated scale:", scale);
        }
        
        model.scale.set(scale);
        model.x = (app.screen.width - mWidth * scale) / 2;
        model.y = (app.screen.height - mHeight * scale) / 2 + 20;

        // Start idle motion
        model.motion("Idle");

        setLoaded(true);
        app.view.style.opacity = "1";
        startAudioReactiveLoop();
      } catch (err) {
        console.error("Live2D load error:", err);
        setError(err.message);
      }
    }

    function startAudioReactiveLoop() {
      let idleTime = 0;
      let blinkTimer = randomBetween(2000, 5000);
      let blinkState = false;
      let swayAngle = 0;

      function tick(delta) {
        if (!modelRef.current) return;
        const model = modelRef.current;

        // 1. Manually update the model state (advances active motions and physics)
        // delta in PIXI ticker is a scaler where 1 is approx 16.66ms (60 FPS)
        const elapsedMS = appRef.current ? appRef.current.ticker.elapsedMS : (delta * 16.66);
        model.update(elapsedMS);

        idleTime += delta;

        // Fetch latest state from refs to prevent stale closure issues
        const analyser = analyserNodeRef.current;
        const speaking = isSpeakingRef.current;

        // --- Mouth / voice reactivity ---
        let mouthOpen = 0;
        if (analyser && speaking) {
          if (!dataArrayRef.current || dataArrayRef.current.length !== analyser.frequencyBinCount) {
            dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
          }
          const dataArray = dataArrayRef.current;
          analyser.getByteFrequencyData(dataArray);
          const start = Math.floor(dataArray.length * 0.05);
          const end = Math.floor(dataArray.length * 0.25);
          let sum = 0;
          for (let i = start; i < end; i++) sum += dataArray[i];
          const avg = sum / (end - start);
          mouthOpen = Math.min(1, avg / 80);
          if (mouthOpen < 0.08) {
            // Procedural lip movement wave if frequency data is quiet
            mouthOpen = Math.max(0, Math.sin(idleTime * 0.22) * 0.45 + 0.35);
          }
        } else if (speaking) {
          // Fallback lip sync if analyser is unavailable
          mouthOpen = Math.max(0, Math.sin(idleTime * 0.22) * 0.45 + 0.35);
        }

        try {
          model.internalModel.coreModel.setParameterValueById(
            "ParamMouthOpenY", mouthOpen
          );
          model.internalModel.coreModel.setParameterValueById(
            "ParamMouthForm", speaking ? 0.8 : 0.3
          );
        } catch (_) {}

        // --- Natural body sway ---
        swayAngle += 0.015;
        const sway = Math.sin(swayAngle) * (speaking ? 6 : 3);
        try {
          model.internalModel.coreModel.setParameterValueById(
            "ParamBodyAngleX", sway
          );
          model.internalModel.coreModel.setParameterValueById(
            "ParamBodyAngleY", Math.sin(swayAngle * 0.6) * 2
          );
        } catch (_) {}

        // --- Breathing ---
        const breath = Math.sin(idleTime * 0.03) * 0.5 + 0.5;
        try {
          model.internalModel.coreModel.setParameterValueById(
            "ParamBreath", breath
          );
        } catch (_) {}

        // --- Blinking ---
        blinkTimer -= delta * 16;
        if (blinkTimer <= 0 && !blinkState) {
          blinkState = true;
          blinkTimer = 150;
          try {
            model.internalModel.coreModel.setParameterValueById("ParamEyeLOpen", 0);
            model.internalModel.coreModel.setParameterValueById("ParamEyeROpen", 0);
          } catch (_) {}
        } else if (blinkTimer <= 0 && blinkState) {
          blinkState = false;
          blinkTimer = randomBetween(2000, 6000);
          try {
            model.internalModel.coreModel.setParameterValueById("ParamEyeLOpen", 1);
            model.internalModel.coreModel.setParameterValueById("ParamEyeROpen", 1);
          } catch (_) {}
        }

        // --- Eye look direction ---
        if (idleTime % 120 < 1) {
          try {
            model.internalModel.coreModel.setParameterValueById(
              "ParamEyeBallX", randomBetween(-0.3, 0.3)
            );
            model.internalModel.coreModel.setParameterValueById(
              "ParamEyeBallY", randomBetween(-0.2, 0.2)
            );
          } catch (_) {}
        }

        // --- Head angle when speaking ---
        if (speaking) {
          try {
            model.internalModel.coreModel.setParameterValueById(
              "ParamAngleX", Math.sin(idleTime * 0.04) * 4
            );
            model.internalModel.coreModel.setParameterValueById(
              "ParamAngleY", Math.sin(idleTime * 0.025) * 3
            );
            model.internalModel.coreModel.setParameterValueById(
              "ParamAngleZ", Math.sin(idleTime * 0.02) * 2
            );
          } catch (_) {}
        } else {
          try {
            model.internalModel.coreModel.setParameterValueById("ParamAngleX", sway * 0.5);
            model.internalModel.coreModel.setParameterValueById("ParamAngleY", 0);
            model.internalModel.coreModel.setParameterValueById("ParamAngleZ", 0);
          } catch (_) {}
        }
      }

      if (appRef.current) {
        appRef.current.ticker.add(tick);
        animFrameRef.current = tick;
      }
    }

    initLive2D();

    return () => {
      destroyed = true;
      if (animFrameRef.current && appRef.current) {
        appRef.current.ticker.remove(animFrameRef.current);
      }
      if (appRef.current) {
        appRef.current.destroy(true, { children: true });
        appRef.current = null;
      }
      modelRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!modelRef.current || !appRef.current) return;
    if (isSpeaking && modelRef.current) {
      try { modelRef.current.motion("Talk"); } catch (_) {}
    } else if (modelRef.current) {
      try { modelRef.current.motion("Idle"); } catch (_) {}
    }
  }, [isSpeaking]);

  function randomBetween(a, b) {
    return Math.random() * (b - a) + a;
  }

  return (
    <div className="avatar-wrapper" ref={containerRef}>
      {/* Outer glow ring — pulses when speaking */}
      <div className={`avatar-glow-ring ${isSpeaking ? "speaking" : ""}`} />

      {/* Loading state */}
      {!loaded && !error && (
        <div className="avatar-loading">
          <div className="avatar-loading-spinner" />
          <p>Loading {persona === "psychiatrist" ? "Dr. Shristy" : (persona === "mentor" ? "Shristy (Mentor)" : "Shristy")}...</p>
        </div>
      )}

      {/* Error fallback — shows robot if model fails to load */}
      {error && <FallbackAvatar isSpeaking={isSpeaking} />}

      {/* Speaking label */}
      <div className={`avatar-status ${isSpeaking ? "speaking" : ""}`}>
        <span className="avatar-status-dot" />
        {isSpeaking 
          ? (persona === "psychiatrist" 
            ? "Dr. Shristy is speaking" 
            : (persona === "mentor" ? "Shristy (Mentor) is speaking" : "Shristy is speaking")) 
          : "Connected"}
      </div>
    </div>
  );
}

// Fallback SVG avatar (your existing robot) shown if model fails to load
function FallbackAvatar({ isSpeaking }) {
  return (
    <div className="fallback-avatar">
      <svg viewBox="0 0 200 200" width="260" height="260">
        <circle cx="100" cy="100" r="90" fill="#0d1b2a" stroke="#00e5ff" strokeWidth="2" />
        <circle cx="70" cy="85" r="14" fill="#00e5ff" opacity="0.9" />
        <circle cx="130" cy="85" r="14" fill="#00e5ff" opacity="0.9" />
        <circle cx="70" cy="85" r="7" fill="#fff" />
        <circle cx="130" cy="85" r="7" fill="#fff" />
        <rect
          x="68" y="125" width="64"
          height={isSpeaking ? "18" : "10"}
          rx="5" fill="#00e5ff" opacity="0.8"
          style={{ transition: "height 0.15s ease" }}
        />
        <rect x="30" y="75" width="18" height="36" rx="9" fill="#1a3a5c" stroke="#00e5ff" strokeWidth="1.5" />
        <rect x="152" y="75" width="18" height="36" rx="9" fill="#1a3a5c" stroke="#00e5ff" strokeWidth="1.5" />
      </svg>
      <p style={{ color: "#888", fontSize: "12px", marginTop: "8px" }}>
        Place model in /public/model/ to enable Live2D
      </p>
    </div>
  );
}
