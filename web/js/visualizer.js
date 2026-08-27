// Audio Visualizer Module (Ultra-Smooth 60/120 FPS High-DPI Engine)
import { state } from './state.js';

export const visualizerState = {
  mode: "waveform" // waveform -> bars -> pixel
};

let offset = 0;
let scopeCanvas = null;
let scopeCtx = null;
let smoothPeak = 0.0;
let barDecay = new Array(32).fill(0);
let dpr = 1;

export function initOscilloscope() {
  scopeCanvas = document.getElementById('scope-canvas');
  if (scopeCanvas) {
    setupHighDpiCanvas();
    scopeCtx = scopeCanvas.getContext('2d');
    window.addEventListener('resize', setupHighDpiCanvas);
    requestAnimationFrame(animateScope);
  }
}

function setupHighDpiCanvas() {
  if (!scopeCanvas) return;
  dpr = window.devicePixelRatio || 1.5;
  const rect = scopeCanvas.getBoundingClientRect();
  const displayWidth = rect.width || 450;
  const displayHeight = rect.height || 96;

  scopeCanvas.width = Math.round(displayWidth * dpr);
  scopeCanvas.height = Math.round(displayHeight * dpr);
}

function animateScope() {
  if (!scopeCanvas || !scopeCtx) return;

  const width = scopeCanvas.width / dpr;
  const height = scopeCanvas.height / dpr;
  const centerY = height / 2;

  // Prepare High-DPI context
  scopeCtx.save();
  scopeCtx.scale(dpr, dpr);
  scopeCtx.clearRect(0, 0, width, height);

  // Smooth lerp physics for peak (Hydraulic damping)
  const localPeak = (window.mediaPlayerIsPlaying) ? (0.14 + Math.sin(Date.now() / 150) * 0.08) : 0.0;
  const targetPeak = Math.max(state.windowsAudioPeak, localPeak);
  smoothPeak = smoothPeak * 0.78 + targetPeak * 0.22;

  const activeAmp = smoothPeak * 13.5;
  const idleAmp = 1.8;
  const amp = state.isSystemMuted ? 0 : Math.max(idleAmp, activeAmp);
  const volumeFactor = state.volumes["master"] / 100;

  if (visualizerState.mode === "waveform") {
    // 1. Phosphor Ambient Neon Glow Underlay
    scopeCtx.save();
    scopeCtx.shadowBlur = 12;
    scopeCtx.shadowColor = "rgba(245, 158, 11, 0.75)";
    scopeCtx.strokeStyle = "#f59e0b";
    scopeCtx.lineWidth = 3.2;
    scopeCtx.lineCap = "round";
    scopeCtx.lineJoin = "round";
    scopeCtx.beginPath();

    // Multi-harmonic fluid wave points
    const step = 3;
    let points = [];
    for (let x = 0; x <= width; x += step) {
      let y = centerY;
      // Fundamental + 2nd harmonic + 3rd micro modulation
      y += Math.sin(x * 0.024 + offset) * amp * volumeFactor;
      y += Math.cos(x * 0.058 - offset * 1.4) * (amp * 0.45) * volumeFactor;
      y += Math.sin(x * 0.012 + offset * 0.6) * (amp * 0.25) * volumeFactor;
      points.push({ x, y });
    }

    if (points.length > 0) {
      scopeCtx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length - 1; i++) {
        const xc = (points[i].x + points[i + 1].x) / 2;
        const yc = (points[i].y + points[i + 1].y) / 2;
        scopeCtx.quadraticCurveTo(points[i].x, points[i].y, xc, yc);
      }
      scopeCtx.lineTo(points[points.length - 1].x, points[points.length - 1].y);
    }
    scopeCtx.stroke();
    scopeCtx.restore();

    // 2. Inner Razor-Sharp Core Laser Line
    scopeCtx.save();
    scopeCtx.strokeStyle = "#fffbeb";
    scopeCtx.lineWidth = 1.2;
    scopeCtx.lineCap = "round";
    scopeCtx.lineJoin = "round";
    scopeCtx.beginPath();
    if (points.length > 0) {
      scopeCtx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length - 1; i++) {
        const xc = (points[i].x + points[i + 1].x) / 2;
        const yc = (points[i].y + points[i + 1].y) / 2;
        scopeCtx.quadraticCurveTo(points[i].x, points[i].y, xc, yc);
      }
      scopeCtx.lineTo(points[points.length - 1].x, points[points.length - 1].y);
    }
    scopeCtx.stroke();
    scopeCtx.restore();

  } else if (visualizerState.mode === "bars") {
    const numBars = 28;
    const spacing = 4;
    const barWidth = Math.floor((width - (numBars - 1) * spacing) / numBars);

    for (let i = 0; i < numBars; i++) {
      const peakVal = state.isSystemMuted ? 0 : smoothPeak;
      // Frequency simulation with natural sub-bass boost on lower bands
      const freqWeight = Math.sin((i / numBars) * Math.PI) * 0.4 + (1.0 - (i / numBars) * 0.5);
      const targetHeight = peakVal > 0.01
        ? ((Math.sin(i * 0.6 + offset) * 0.35 + 0.65) * peakVal * height * 0.85 * freqWeight * volumeFactor) + 2
        : 2 + Math.sin(i * 0.5 + offset) * 1.5;

      // Peak decay cap
      if (targetHeight > barDecay[i]) {
        barDecay[i] = targetHeight;
      } else {
        barDecay[i] = Math.max(2, barDecay[i] - 0.7);
      }

      const x = i * (barWidth + spacing);
      const y = height - targetHeight;

      // Bar Body
      scopeCtx.fillStyle = "#f59e0b";
      scopeCtx.fillRect(x, y, barWidth, targetHeight);

      // Top Peak Hold Cap
      scopeCtx.fillStyle = "#ffffff";
      scopeCtx.fillRect(x, height - barDecay[i] - 2, barWidth, 1.5);
    }

  } else if (visualizerState.mode === "pixel") {
    scopeCtx.fillStyle = "#3b82f6";
    const step = 6;
    for (let x = 0; x < width; x += step) {
      let y = centerY;
      y += Math.sin(x * 0.025 + offset) * amp * volumeFactor;
      y += Math.cos(x * 0.06 - offset * 1.3) * (amp * 0.4) * volumeFactor;

      const gridY = Math.round(y / 4) * 4;
      scopeCtx.fillRect(x, gridY, 3, 3);
    }
  }

  scopeCtx.restore();

  const speed = 0.05 + (smoothPeak * 0.14);
  offset += speed;

  // Mini AVR scope rendering if active
  if (window.avrState && window.avrState.power && window.avrState.source === "OPTICAL") {
    drawAvrVisualizer(smoothPeak, amp, volumeFactor);
  }

  requestAnimationFrame(animateScope);
}

function drawAvrVisualizer(peak, amp, volumeFactor) {
  const avrCanvas = document.getElementById("avr-vis-canvas");
  if (!avrCanvas) return;
  const ctx = avrCanvas.getContext("2d");
  if (!ctx) return;

  ctx.clearRect(0, 0, avrCanvas.width, avrCanvas.height);
  const w = avrCanvas.width;
  const h = avrCanvas.height;
  const cy = h / 2;

  ctx.strokeStyle = "#f59e0b";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let x = 0; x < w; x += 2) {
    let y = cy + Math.sin(x * 0.08 + offset * 1.5) * amp * 0.4 * volumeFactor;
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}
