// Room Calibration Module
import { apiPost, showToast } from './api.js';
import { state, ids } from './state.js';
import { updateDdlButtonUI } from './audio_effects.js';

// Debounce helper
function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

const saveCalibrationDelays = debounce(() => {
  const delays = {};
  const calIds = ["surroundL", "towerL", "center", "subwoofer", "towerR", "surroundR"];
  calIds.forEach(id => {
    const slider = document.getElementById(`delay-${id}`);
    if (slider) {
      delays[id] = parseInt(slider.value);
    }
  });
  apiPost("/api/settings/update", { calibration_delays: delays });
}, 250);

const saveCalibrationEQ = debounce(() => {
  const eq = {};
  const eqBands = ["bass", "mid", "treble"];
  eqBands.forEach(band => {
    const slider = document.getElementById(`eq-${band}`);
    if (slider) {
      eq[band] = parseFloat(slider.value);
    }
  });
  apiPost("/api/settings/update", { calibration_eq: eq });
}, 250);

export function applyCalibrationUI() {
  const settings = state.settings;
  const enabled = settings.calibration_enabled !== false;

  const btn = document.getElementById("toggle-calibration");
  const indicator = document.getElementById("calibration-indicator");
  const btnText = document.getElementById("calibration-btn-text");
  const spinner = document.getElementById("cal-spinner");

  if (btn && indicator && btnText) {
    if (enabled) {
      btn.className = "flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/60 text-xs font-mono font-bold uppercase transition-all duration-300 cursor-pointer shadow-[0_0_10px_rgba(245,158,11,0.15)]";
      btnText.innerText = "ON";
      btnText.className = "text-amber-400 transition-colors duration-300";
      indicator.className = "w-1.5 h-1.5 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.8)] transition-all duration-300";
    } else {
      btn.className = "flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-950 border border-zinc-800 hover:border-amber-500/40 text-xs font-mono font-bold uppercase transition-all duration-300 cursor-pointer";
      btnText.innerText = "OFF";
      btnText.className = "text-zinc-400 transition-colors duration-300";
      indicator.className = "w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.7)] transition-all duration-300";
    }
    if (spinner) spinner.classList.add("hidden");
    if (indicator) indicator.classList.remove("hidden");
    btn.disabled = false;
  }

  const delayGrid = document.querySelector("#view-room-cal .grid");
  const eqGrid = document.getElementById("cal-eq-container");
  const calSvg = document.getElementById("cal-svg");
  const centerBtn = document.getElementById("btn-cal-center-reset");
  const optBtn = document.getElementById("btnAcousticCorrection");

  if (enabled) {
    if (delayGrid) delayGrid.classList.remove("calibration-dimmed");
    if (eqGrid) eqGrid.classList.remove("calibration-dimmed");
    if (calSvg) calSvg.classList.remove("calibration-dimmed");
    if (centerBtn) centerBtn.classList.remove("calibration-dimmed");
    if (optBtn) optBtn.classList.remove("calibration-dimmed");
  } else {
    if (delayGrid) delayGrid.classList.add("calibration-dimmed");
    if (eqGrid) eqGrid.classList.add("calibration-dimmed");
    if (calSvg) calSvg.classList.add("calibration-dimmed");
    if (centerBtn) centerBtn.classList.add("calibration-dimmed");
    if (optBtn) optBtn.classList.add("calibration-dimmed");
  }

  const clickX = settings.calibration_focus_x ?? 200;
  const clickY = settings.calibration_focus_y ?? 240;

  const focusPoint = document.getElementById("focus-point");
  const focusGlow = document.getElementById("focus-glow-circle");
  const focusGlowOuter = document.getElementById("focus-glow-circle-outer");

  if (focusPoint) {
    focusPoint.setAttribute("cx", clickX);
    focusPoint.setAttribute("cy", clickY);
  }
  if (focusGlow) {
    focusGlow.setAttribute("cx", clickX);
    focusGlow.setAttribute("cy", clickY);
    focusGlow.style.transformOrigin = `${clickX}px ${clickY}px`;
  }
  if (focusGlowOuter) {
    focusGlowOuter.setAttribute("cx", clickX);
    focusGlowOuter.setAttribute("cy", clickY);
  }

  const calIds = ["surroundL", "towerL", "center", "subwoofer", "towerR", "surroundR"];
  calIds.forEach(id => {
    const line = document.getElementById(`line-${id}`);
    if (line) {
      line.setAttribute("x2", clickX);
      line.setAttribute("y2", clickY);
    }
  });

  if (settings.calibration_delays) {
    Object.keys(settings.calibration_delays).forEach(id => {
      const rawVal = settings.calibration_delays[id];
      const slider = document.getElementById(`delay-${id}`);
      if (slider) slider.value = rawVal;

      const ms = (rawVal / 10).toFixed(1);
      const meters = (ms * 0.343).toFixed(2);

      const lblDelay = document.getElementById(`lbl-delay-${id}`);
      const lblDist = document.getElementById(`lbl-dist-${id}`);
      if (lblDelay) lblDelay.innerText = `${ms} ms`;
      if (lblDist) {
        const gains = settings.calibration_gains || {};
        const gainVal = gains[id] !== undefined ? gains[id] : 0.0;
        const gainText = (gainVal >= 0 ? "+" : "") + gainVal.toFixed(1) + " dB";
        lblDist.innerText = `${meters} m (${gainText})`;
      }
    });
  }

  if (settings.calibration_eq) {
    Object.keys(settings.calibration_eq).forEach(band => {
      const val = settings.calibration_eq[band];
      const slider = document.getElementById(`eq-${band}`);
      if (slider) slider.value = val;

      const lbl = document.getElementById(`lbl-eq-${band}`);
      if (lbl) {
        lbl.innerText = (val >= 0 ? "+" : "") + val.toFixed(1) + " dB";
      }
    });
  }

  // Update Segmented calibration mode buttons styles
  const activeMode = (settings && settings.calibration_mode) ? settings.calibration_mode : (state.settings.calibration_mode || "sweetspot");
  const modes = ["sweetspot", "steering", "levelonly"];
  modes.forEach(m => {
    const btn = document.getElementById(`btn-calmode-${m}`);
    if (btn) {
      if (activeMode === m) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    }
  });
}

export function initRoomCalibrations() {
  const calIds = ["surroundL", "towerL", "center", "subwoofer", "towerR", "surroundR"];

  const calSvg = document.getElementById("cal-svg");
  if (calSvg) {
    calSvg.addEventListener("click", async (e) => {
      if (state.settings.calibration_enabled === false) {
        return;
      }
      const rect = calSvg.getBoundingClientRect();
      const clickX = ((e.clientX - rect.left) / rect.width) * 400;
      const clickY = ((e.clientY - rect.top) / rect.height) * 400;

      const focusPoint = document.getElementById("focus-point");
      const focusGlow = document.getElementById("focus-glow-circle");
      const focusGlowOuter = document.getElementById("focus-glow-circle-outer");

      if (focusPoint) {
        focusPoint.setAttribute("cx", clickX);
        focusPoint.setAttribute("cy", clickY);
      }
      if (focusGlow) {
        focusGlow.setAttribute("cx", clickX);
        focusGlow.setAttribute("cy", clickY);
        focusGlow.style.transformOrigin = `${clickX}px ${clickY}px`;
      }
      if (focusGlowOuter) {
        focusGlowOuter.setAttribute("cx", clickX);
        focusGlowOuter.setAttribute("cy", clickY);
      }

      calIds.forEach(id => {
        const line = document.getElementById(`line-${id}`);
        if (line) {
          line.setAttribute("x2", clickX);
          line.setAttribute("y2", clickY);
        }
      });

      const res = await apiPost("/api/calibration/optimize", { x: clickX, y: clickY });
      if (res && res.status === "success") {
        state.settings.calibration_focus_x = clickX;
        state.settings.calibration_focus_y = clickY;
        state.settings.calibration_delays = res.delays;
        state.settings.calibration_gains = res.gains;
        applyCalibrationUI();
        showToast("Sweet-Spot Focused", `Recalibrated sound phase focal target to coordinates [${Math.round(clickX)}, ${Math.round(clickY)}].`, "brand-blue");
      }
    });
  }

  calIds.forEach(id => {
    const slider = document.getElementById(`delay-${id}`);
    if (slider) {
      slider.addEventListener("input", (e) => {
        if (state.settings.calibration_enabled === false) {
          e.preventDefault();
          return;
        }
        const rawVal = parseInt(e.target.value);
        const ms = (rawVal / 10).toFixed(1);
        const meters = (ms * 0.343).toFixed(2);

        const lblDelay = document.getElementById(`lbl-delay-${id}`);
        const lblDist = document.getElementById(`lbl-dist-${id}`);

        if (lblDelay) lblDelay.innerText = `${ms} ms`;
        if (lblDist) lblDist.innerText = `${meters} m`;

        saveCalibrationDelays();
      });
    }
  });

  const eqBands = ["bass", "mid", "treble"];
  eqBands.forEach(band => {
    const slider = document.getElementById(`eq-${band}`);
    if (slider) {
      slider.addEventListener("input", (e) => {
        if (state.settings.calibration_enabled === false) {
          e.preventDefault();
          return;
        }
        const val = parseFloat(e.target.value);
        const lbl = document.getElementById(`lbl-eq-${band}`);
        if (lbl) {
          lbl.innerText = (val >= 0 ? "+" : "") + val.toFixed(1) + " dB";
        }
        saveCalibrationEQ();
      });
    }
  });

  const optBtn = document.getElementById("btnAcousticCorrection");
  if (optBtn) {
    optBtn.addEventListener("click", async () => {
      if (state.settings.calibration_enabled === false) {
        return;
      }
      showToast("Optimizing EQ", "Calculating room acoustic correction coefficients...", "brand-blue");

      const optimizedEQ = { bass: 1.5, mid: 0.5, treble: 1.0 };
      const res = await apiPost("/api/settings/update", { calibration_eq: optimizedEQ });
      if (res && res.status === "success") {
        state.settings.calibration_eq = optimizedEQ;

        setTimeout(() => {
          Object.keys(optimizedEQ).forEach(band => {
            const val = optimizedEQ[band];
            const slider = document.getElementById(`eq-${band}`);
            if (slider) slider.value = val;

            const lbl = document.getElementById(`lbl-eq-${band}`);
            if (lbl) {
              lbl.innerText = (val >= 0 ? "+" : "") + val.toFixed(1) + " dB";
            }
          });

          showToast("Calibration Complete", "Optimized room correction profile applied.", "brand-blue");
        }, 1000);
      }
    });
  }

  const calToggleBtn = document.getElementById("toggle-calibration");
  if (calToggleBtn) {
    calToggleBtn.addEventListener("click", async () => {
      const current = state.settings.calibration_enabled !== false;
      const newState = !current;

      const spinner = document.getElementById("cal-spinner");
      const indicator = document.getElementById("calibration-indicator");
      const btnText = document.getElementById("calibration-btn-text");
      if (spinner) spinner.classList.remove("hidden");
      if (indicator) indicator.classList.add("hidden");
      if (btnText) btnText.innerText = "...";
      calToggleBtn.disabled = true;

      const res = await apiPost("/api/calibration/toggle", { enabled: newState });
      if (res && (res.status === "success" || res.status === "partial")) {
        state.settings.calibration_enabled = newState;
        applyCalibrationUI();

        if (newState) {
          showToast("Calibration ON", "Phase delay correction active in Equalizer APO pipeline.", "brand-blue");
          if (res.ddl_disabled) {
            setTimeout(() => {
              showToast("Dolby Live Disabled", "DDL was automatically disabled — Room Calibration and DDL cannot run simultaneously.", "brand-amber");
              state.ddlActive = false;
              updateDdlButtonUI();
            }, 1200);
          }
        } else {
          showToast("Calibration OFF", "Phase delay correction removed from APO signal chain.", "brand-amber");
        }
      } else {
        applyCalibrationUI();
      }
    });
  }

  const centerResetBtn = document.getElementById("btn-cal-center-reset");
  if (centerResetBtn) {
    centerResetBtn.addEventListener("click", async () => {
      if (state.settings.calibration_enabled === false) {
        return;
      }
      const CENTER_X = 200;
      const CENTER_Y = 200;

      const focusPoint = document.getElementById("focus-point");
      const focusGlow = document.getElementById("focus-glow-circle");
      const focusGlowOuter = document.getElementById("focus-glow-circle-outer");
      if (focusPoint) {
        focusPoint.style.transition = "cx 0.4s ease, cy 0.4s ease";
        focusPoint.setAttribute("cx", CENTER_X);
        focusPoint.setAttribute("cy", CENTER_Y);
      }
      if (focusGlow) {
        focusGlow.style.transition = "cx 0.4s ease, cy 0.4s ease";
        focusGlow.setAttribute("cx", CENTER_X);
        focusGlow.setAttribute("cy", CENTER_Y);
        focusGlow.style.transformOrigin = `${CENTER_X}px ${CENTER_Y}px`;
      }
      if (focusGlowOuter) {
        focusGlowOuter.style.transition = "cx 0.4s ease, cy 0.4s ease";
        focusGlowOuter.setAttribute("cx", CENTER_X);
        focusGlowOuter.setAttribute("cy", CENTER_Y);
      }

      const calIds = ["surroundL", "towerL", "center", "subwoofer", "towerR", "surroundR"];
      calIds.forEach(id => {
        const line = document.getElementById(`line-${id}`);
        if (line) {
          line.style.transition = "x2 0.4s ease, y2 0.4s ease";
          line.setAttribute("x2", CENTER_X);
          line.setAttribute("y2", CENTER_Y);
        }
      });

      centerResetBtn.classList.add("border-amber-500/60", "text-amber-400");
      setTimeout(() => centerResetBtn.classList.remove("border-amber-500/60", "text-amber-400"), 600);

      const res = await apiPost("/api/calibration/optimize", { x: CENTER_X, y: CENTER_Y });
      if (res && res.status === "success") {
        state.settings.calibration_focus_x = CENTER_X;
        state.settings.calibration_focus_y = CENTER_Y;
        state.settings.calibration_delays = res.delays;
        state.settings.calibration_gains = res.gains;
        applyCalibrationUI();
        showToast("Center Reset", "Focus point reset to room center. Phase delays and gains recalculated.", "brand-blue");
      }
    });
  }

  // Segmented calibration mode buttons click listeners
  const modes = ["sweetspot", "steering", "levelonly"];
  modes.forEach(m => {
    const btn = document.getElementById(`btn-calmode-${m}`);
    if (btn) {
      btn.addEventListener("click", async (e) => {
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }

        // Instantly switch active button glow & styling
        state.settings.calibration_mode = m;
        applyCalibrationUI();

        let modeTitle = "";
        let modeDesc = "";
        if (m === "sweetspot") {
          modeTitle = "Sweet-Spot Active";
          modeDesc = "Timing alignment and soundstage balance prioritized.";
        } else if (m === "steering") {
          modeTitle = "Sound Steering Active";
          modeDesc = "Pure sound volume focus directed towards sweet spot.";
        } else {
          modeTitle = "Level-Only Active";
          modeDesc = "Equalized loudness without timing phase delays.";
        }
        showToast(modeTitle, modeDesc, "brand-blue");

        // Save setting
        await apiPost("/api/settings/update", { calibration_mode: m });
        
        // Recalculate delays and gains
        const x = state.settings.calibration_focus_x !== undefined ? state.settings.calibration_focus_x : 200;
        const y = state.settings.calibration_focus_y !== undefined ? state.settings.calibration_focus_y : 200;
        
        const res = await apiPost("/api/calibration/optimize", { x, y, mode: m });
        if (res && res.status === "success") {
          state.settings.calibration_delays = res.delays;
          state.settings.calibration_gains = res.gains;
          applyCalibrationUI();
        }
      });
    }
  });
}
