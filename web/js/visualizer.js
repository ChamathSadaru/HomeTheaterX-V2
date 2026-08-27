// Audio Visualizer Module
import { state } from './state.js';

export const visualizerState = {
  mode: "waveform" // waveform -> bars -> pixel
};

let offset = 0;
let scopeCanvas = null;
let scopeCtx = null;

export function initOscilloscope() {
  scopeCanvas = document.getElementById('scope-canvas');
  if (scopeCanvas) {
    scopeCtx = scopeCanvas.getContext('2d');
    animateScope();
  }
}

function animateScope() {
  if (!scopeCanvas || !scopeCtx) return;
  scopeCtx.clearRect(0, 0, scopeCanvas.width, scopeCanvas.height);

  const width = scopeCanvas.width;
  const height = scopeCanvas.height;
  const centerY = height / 2;

  const localPeak = (window.mediaPlayerIsPlaying) ? (0.12 + Math.sin(Date.now() / 120) * 0.06) : 0.0;
  const peak = Math.max(state.windowsAudioPeak, localPeak);
  const activeAmp = peak * 11;
  const idleAmp = 2.0;
  const amp = state.isSystemMuted ? 0 : Math.max(idleAmp, activeAmp);
  const volumeFactor = state.volumes["master"] / 100;

  if (visualizerState.mode === "waveform") {
    scopeCtx.strokeStyle = "#f59e0b";
    scopeCtx.lineWidth = 2.5;
    scopeCtx.beginPath();

    for (let x = 0; x < width; x++) {
      let y = centerY;
      y += Math.sin(x * 0.03 + offset) * amp * volumeFactor;
      y += Math.cos(x * 0.07 - offset * 1.3) * (amp * 0.4) * volumeFactor;

      if (x === 0) {
        scopeCtx.moveTo(x, y);
      } else {
        scopeCtx.lineTo(x, y);
      }
    }
    scopeCtx.stroke();

  } else if (visualizerState.mode === "bars") {
    const numBars = 28;
    const spacing = 4;
    const barWidth = Math.floor((width - (numBars - 1) * spacing) / numBars);

    for (let i = 0; i < numBars; i++) {
      const peakVal = state.isSystemMuted ? 0 : peak;
      const barHeight = peakVal > 0.01
        ? (Math.sin(i / 2 + offset) * 0.35 + 0.65) * peakVal * height * 0.75 * volumeFactor + 2
        : 2 + Math.sin(i + offset) * 1.5;

      const x = i * (barWidth + spacing);
      const y = height - barHeight;

      scopeCtx.fillStyle = "#f59e0b";
      scopeCtx.fillRect(x, y, barWidth, barHeight);

      scopeCtx.fillStyle = "rgba(255, 255, 255, 0.45)";
      scopeCtx.fillRect(x, y, barWidth, 1.2);
    }

  } else if (visualizerState.mode === "pixel") {
    scopeCtx.fillStyle = "#3b82f6";
    const step = 6;
    for (let x = 0; x < width; x += step) {
      let y = centerY;
      y += Math.sin(x * 0.03 + offset) * amp * volumeFactor;
      y += Math.cos(x * 0.07 - offset * 1.3) * (amp * 0.4) * volumeFactor;

      const gridY = Math.round(y / 4) * 4;
      scopeCtx.fillRect(x, gridY, 3, 3);
    }
  }

  const peakVal = Math.max(state.windowsAudioPeak, (window.mediaPlayerIsPlaying) ? 0.12 : 0.0);
  const speed = 0.06 + (peakVal * 0.12);
  offset += speed;

  // Also animate the mini AVR scope if active
  // avrState and updateAVRConsoleUI are assumed to be defined in app.js / receiver logic
  if (window.avrState && window.avrState.power && window.avrState.source === "OPTICAL") {
    drawAvrVisualizer(peakVal, amp, volumeFactor);
  }

  requestAnimationFrame(animateScope);
}

function drawAvrVisualizer(peak, amp, volumeFactor) {
  const canvas = document.getElementById("avr-vis-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const w = canvas.width;
  const h = canvas.height;
  const centerY = h / 2;

  ctx.strokeStyle = "#f59e0b";
  ctx.lineWidth = 1.6;
  ctx.shadowColor = "rgba(245, 158, 11, 0.4)";
  ctx.shadowBlur = 3;
  ctx.beginPath();

  for (let x = 0; x < w; x++) {
    let y = centerY;
    const waveAmp = amp * 0.35 * volumeFactor;
    y += Math.sin(x * 0.06 + offset) * waveAmp;
    y += Math.cos(x * 0.14 - offset * 1.5) * (waveAmp * 0.25);
    y = Math.max(1, Math.min(h - 1, y));

    if (x === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();
  ctx.shadowBlur = 0;
}
