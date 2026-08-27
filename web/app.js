// Samsung Virtual Acoustics Studio Symmetrical Deck Controller JavaScript
// Directly binds to custom horizontal tracks and synchronizes with pycaw backend

const ids = ["surroundL", "towerL", "subwoofer", "center", "towerR", "surroundR"];

const channelIndexMap = {
  "towerL": 0,
  "towerR": 1,
  "center": 2,
  "subwoofer": 3,
  "surroundL": 4,
  "surroundR": 5
};

const state = {
  windowsAudioPeak: 0.0,
  volumes: {
    "surroundL": 75,
    "towerL": 80,
    "subwoofer": 90,
    "center": 85,
    "towerR": 80,
    "surroundR": 75,
    "master": 85
  },
  isSystemMuted: false,
  isUserDragging: false,
  userDraggingTimeout: null,
  sweepActive: false,
  sweepInterval: null,
  currentDeviceName: "",
  channelCount: 6,
  
  // Custom View States
  currentView: "studio",
  receiverInput: "HDMI 1 / eARC",
  receiverDSP: "ATMOS STANDARD",
  drcActive: true,
  crossoverVal: "80 Hz",

  // Speaker solo/isolate ("check speakers one by one") state
  solo: { active: false, channel: null },

  // Settings toggles
  settings: {
    notifications_enabled: true,
    minimize_to_tray_on_close: true
  },
  startupEnabled: false
};

// Utility: REST GET
async function apiGet(endpoint) {
  try {
    const response = await fetch(endpoint);
    return await response.json();
  } catch (e) {
    console.error(`GET error ${endpoint}:`, e);
    return null;
  }
}

// Utility: REST POST
async function apiPost(endpoint, data = {}) {
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await response.json();
  } catch (e) {
    console.error(`POST error ${endpoint}:`, e);
    return null;
  }
}

// Prevent polling updates from overriding user interaction
function setUserDragging() {
  state.isUserDragging = true;
  clearTimeout(state.userDraggingTimeout);
  state.userDraggingTimeout = setTimeout(() => {
    state.isUserDragging = false;
  }, 1200);
}

document.addEventListener("DOMContentLoaded", () => {
  initOscilloscope();
  animateSpeakerPulses();
  refreshDevices();
  updateAppStatus();
  setInterval(pollVolumeChanges, 600);

  // Bind dropdown & scan button
  document.getElementById("deviceSelector").addEventListener("change", onDeviceSelected);
  document.getElementById("btnRefresh").addEventListener("refreshDevices", refreshDevices);
  
  // Test Soundstage / Sweep button
  const testBtn = document.getElementById("test-btn");
  if (testBtn) {
    testBtn.addEventListener("click", runSequentialSweep);
  }

  // Visualizer Mode preset switcher
  const btnVisMode = document.getElementById("btn-vis-mode");
  const lblVisMode = document.getElementById("lbl-vis-mode");
  if (btnVisMode) {
    btnVisMode.addEventListener("click", () => {
      if (visualizerMode === "waveform") {
        visualizerMode = "bars";
        if (lblVisMode) lblVisMode.innerText = "Spectrum";
      } else if (visualizerMode === "bars") {
        visualizerMode = "pixel";
        if (lblVisMode) lblVisMode.innerText = "Retro Dots";
      } else {
        visualizerMode = "waveform";
        if (lblVisMode) lblVisMode.innerText = "Waveform";
      }
    });
  }

  const formatSelector = document.getElementById("formatSelector");
  if (formatSelector) {
    formatSelector.addEventListener("change", () => {
      const selectedOption = formatSelector.options[formatSelector.selectedIndex].text;
      
      // Update format details in Diagnostic Scope (systemMode badge)
      const sysMode = document.getElementById("systemMode");
      if (sysMode) {
        if (formatSelector.value === "dolby-digital") {
          sysMode.innerText = "Dolby Digital Live 5.1";
        } else if (formatSelector.value === "24-48000") {
          sysMode.innerText = "24-bit / 48kHz PCM";
        } else if (formatSelector.value === "24-44100") {
          sysMode.innerText = "24-bit / 44.1kHz PCM";
        } else if (formatSelector.value === "16-48000") {
          sysMode.innerText = "16-bit / 48kHz PCM";
        } else if (formatSelector.value === "16-44100") {
          sysMode.innerText = "16-bit / 44.1kHz CD";
        } else if (formatSelector.value === "16-32000") {
          sysMode.innerText = "16-bit / 32kHz FM";
        }
      }
      
      showToast("Audio Format Updated", `Hardware output stream configured to ${selectedOption}`, "brand-blue");
    });
  }

  // Bind individual channel faders
  ids.forEach(id => {
    const slider = document.getElementById(`slider-${id}`);
    if (slider) {
      slider.addEventListener("input", (e) => {
        setUserDragging();
        const value = parseInt(e.target.value);
        state.volumes[id] = value;
        updateFaderUI(id, value);
        const idx = channelIndexMap[id];
        sendChannelVolume(idx, value);
        saveUserPreset();
      });
    }
  });

  // Bind master fader
  const masterSlider = document.getElementById("slider-master");
  if (masterSlider) {
    masterSlider.addEventListener("input", (e) => {
      setUserDragging();
      const value = parseInt(e.target.value);
      state.volumes["master"] = value;
      updateMasterUI(value);
      sendMasterVolume(value);
      saveUserPreset();
    });
  }

  // Mute System button
  const muteBtn = document.getElementById("mute-btn");
  if (muteBtn) {
    muteBtn.addEventListener("click", toggleSystemMute);
  }

  // Reset Balance button
  const resetBtn = document.getElementById("reset-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", resetBalance);
  }

  // Sweep Run button (Legacy)
  const btnSweep = document.getElementById("btnSweep");
  if (btnSweep) {
    btnSweep.addEventListener("click", runSequentialSweep);
  }

  // Bind individual speaker channel muting click listeners
  initSpeakerChannelMuting();

  // Custom Window Controls (Frameless)
  const minBtn = document.getElementById("win-min-btn");
  if (minBtn) {
    minBtn.addEventListener("click", () => {
      apiPost("/api/window/minimize");
    });
  }

  const closeBtn = document.getElementById("win-close-btn");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      apiPost("/api/window/close");
    });
  }

  // Tab navigation bindings
  initTabsNavigation();

  // Room Calibrations bindings
  initRoomCalibrations();

  // Receiver Console bindings
  initReceiverConsole();

  // Settings crossover binding
  initSettingsView();

  // Speaker solo/isolate ("check speakers one by one")
  initSpeakerSoloHandlers();
  initSpeakerGlowHandlers();

  // Subwoofer locked-slider click/drag detection
  initSubwooferLockOverlay();

  // App settings (native notifications, startup, minimize-to-tray)
  initAppSettings();

  // Acoustic presets selector
  initAcousticPresets();

  // Initialize the mini media player
  initMediaPlayer();

  // Real-time audio visualizer sync
  initWindowsAudioSync();
});

// ------------------------------------------------------------------
// Speaker click-and-hold glow handlers
// Adds a glow behind the speaker cabinet while the user holds the click.
// ------------------------------------------------------------------
function initSpeakerGlowHandlers() {
  ids.forEach(id => {
    const wrapper = document.getElementById(`speaker-wrapper-${id}`);
    if (wrapper) {
      const addGlow = () => {
        wrapper.classList.add("speaker-clicked-glow");
      };
      
      const removeGlow = () => {
        wrapper.classList.remove("speaker-clicked-glow");
      };

      wrapper.addEventListener("mousedown", addGlow);
      wrapper.addEventListener("touchstart", addGlow, { passive: true });
      
      wrapper.addEventListener("mouseup", removeGlow);
      wrapper.addEventListener("mouseleave", removeGlow);
      wrapper.addEventListener("touchend", removeGlow);
      wrapper.addEventListener("touchcancel", removeGlow);
    }
  });
}

// ------------------------------------------------------------------
// Speaker Solo / Isolate — click a speaker cabinet to hear it alone.
// Clicking the same speaker again restores every channel to the level
// it had before the solo test started.
// ------------------------------------------------------------------
function initSpeakerSoloHandlers() {
  ids.forEach(id => {
    const wrapper = document.getElementById(`speaker-wrapper-${id}`);
    if (wrapper) {
      wrapper.addEventListener("click", () => toggleSpeakerSolo(id));
    }
  });
}

async function toggleSpeakerSolo(id) {
  const idx = channelIndexMap[id];

  if (state.solo.active && state.solo.channel === idx) {
    // Same speaker clicked again -> stop solo, restore prior levels
    const res = await apiPost("/api/solo/stop");
    if (res && res.status === "success") {
      state.solo = { active: false, channel: null };
      applySoloVisuals();
      showToast("Isolate Off", "Restored previous channel levels.", "brand-blue");
      updateAppStatus();
    }
    return;
  }

  const res = await apiPost("/api/solo/start", { channel: idx });
  if (res && res.status === "success") {
    state.solo = { active: true, channel: idx };
    applySoloVisuals();
    showToast("Speaker Isolated", `Playing ${labelForChannel(id)} alone at 100%. Click it again to restore.`, "brand-blue");
    updateAppStatus();
  }
}

function labelForChannel(id) {
  const labels = {
    towerL: "Front Left", towerR: "Front Right", center: "Center",
    subwoofer: "Subwoofer", surroundL: "Surround Left", surroundR: "Surround Right"
  };
  return labels[id] || id;
}

function applySoloVisuals() {
  ids.forEach(id => {
    const idx = channelIndexMap[id];
    const wrapper = document.getElementById(`speaker-wrapper-${id}`);
    const card = document.getElementById(`card-${id}`);
    if (!wrapper) return;

    if (state.solo.active && state.solo.channel === idx) {
      wrapper.classList.add("speaker-solo-active");
      wrapper.classList.remove("speaker-solo-dimmed");
      if (card) card.classList.add("card-solo-active");
    } else if (state.solo.active) {
      wrapper.classList.remove("speaker-solo-active");
      wrapper.classList.add("speaker-solo-dimmed");
      if (card) card.classList.remove("card-solo-active");
    } else {
      wrapper.classList.remove("speaker-solo-active", "speaker-solo-dimmed");
      if (card) card.classList.remove("card-solo-active");
    }
  });
}

// ------------------------------------------------------------------
// Individual Speaker Channel Muting Control
// Click the fader's Mute icon to silence that specific speaker.
// ------------------------------------------------------------------
let preMuteVolumes = {};

function initSpeakerChannelMuting() {
  ids.forEach(id => {
    const muteBtn = document.getElementById("mute-chan-" + id);
    if (muteBtn) {
      muteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleSpeakerMute(id);
      });
    }
  });
}

function toggleSpeakerMute(id) {
  const slider = document.getElementById("slider-" + id);
  if (!slider) return;
  const currentVol = parseInt(slider.value);
  
  if (currentVol > 0) {
    preMuteVolumes[id] = currentVol;
    slider.value = 0;
    state.volumes[id] = 0;
    updateFaderUI(id, 0);
    
    const idx = channelIndexMap[id];
    sendChannelVolume(idx, 0);
    saveUserPreset();
    showToast("Channel Muted", `${labelForChannel(id)} speaker volume set to 0%`, "brand-amber");
  } else {
    const restoredVol = preMuteVolumes[id] || 80;
    slider.value = restoredVol;
    state.volumes[id] = restoredVol;
    updateFaderUI(id, restoredVol);

    const idx = channelIndexMap[id];
    sendChannelVolume(idx, restoredVol);
    saveUserPreset();
    showToast("Channel Active", `${labelForChannel(id)} speaker volume restored to ${restoredVol}%`, "brand-blue");
  }
}

// ------------------------------------------------------------------
// Locked subwoofer slider — clicking/dragging it does nothing to the
// audio (it's hardware-locked at 100%) but surfaces a clear native
// Windows notification + in-app toast explaining why.
// ------------------------------------------------------------------
function initSubwooferLockOverlay() {
  const overlay = document.getElementById("subwoofer-lock-overlay");
  if (!overlay) return;

  const notifyLocked = async () => {
    showToast("Subwoofer Locked", "Subwoofer level is fixed at 100%. Use the remote control to change it.", "brand-amber");
    await apiPost("/api/subwoofer_lock_notice");
  };

  overlay.addEventListener("click", notifyLocked);
  overlay.addEventListener("mousedown", notifyLocked);
  overlay.addEventListener("touchstart", notifyLocked);
}

// ------------------------------------------------------------------
// App Settings (Settings tab): native notifications, launch-on-startup,
// minimize-to-tray-on-close. Persisted server-side via config_manager.
// ------------------------------------------------------------------
function setToggleUI(btnId, knobId, active) {
  const btn = document.getElementById(btnId);
  const knob = document.getElementById(knobId);
  if (!btn || !knob) return;
  btn.dataset.active = active ? "true" : "false";
  if (active) {
    btn.className = "w-12 h-6 rounded-full bg-amber-500 relative transition-all flex-shrink-0";
    knob.className = "absolute top-0.5 left-6 w-5 h-5 rounded-full bg-black transition-all";
  } else {
    btn.className = "w-12 h-6 rounded-full bg-zinc-800 border border-zinc-700 relative transition-all flex-shrink-0";
    knob.className = "absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-zinc-400 transition-all";
  }
}

async function initAppSettings() {
  const data = await apiGet("/api/settings");
  if (data && data.status === "success") {
    state.settings = data.settings || state.settings;
    state.startupEnabled = !!data.startup_enabled;

    setToggleUI("toggle-startup", "toggle-startup-knob", state.startupEnabled);
    setToggleUI("toggle-notifications", "toggle-notifications-knob", state.settings.notifications_enabled !== false);
    setToggleUI("toggle-minimize-tray", "toggle-minimize-tray-knob", state.settings.minimize_to_tray_on_close !== false);

    if (state.settings.crossover_hz) {
      const crossoverSelect = document.getElementById("set-crossover");
      const crossoverDisplay = document.getElementById("infoCrossoverVal");
      if (crossoverSelect) crossoverSelect.value = String(state.settings.crossover_hz);
      if (crossoverDisplay) crossoverDisplay.innerText = `${state.settings.crossover_hz} Hz`;
    }

    // Restore and apply Room Calibration settings
    applyCalibrationUI();
    // Highlight the active audio preset
    if (state.settings.active_profile) {
      highlightPreset(state.settings.active_profile);
    }
  }

  const startupBtn = document.getElementById("toggle-startup");
  if (startupBtn) {
    startupBtn.addEventListener("click", async () => {
      const newState = startupBtn.dataset.active !== "true";
      const res = await apiPost("/api/startup/toggle", { enabled: newState });
      if (res && res.status === "success") {
        state.startupEnabled = res.enabled;
        setToggleUI("toggle-startup", "toggle-startup-knob", res.enabled);
        showToast("Startup Setting Updated",
          res.enabled ? "App will launch automatically with Windows." : "App will no longer launch automatically.",
          "brand-blue");
      } else {
        showToast("Startup Update Failed", "Could not update the Windows startup registration.", "brand-amber");
      }
    });
  }

  const notifBtn = document.getElementById("toggle-notifications");
  if (notifBtn) {
    notifBtn.addEventListener("click", async () => {
      const newState = notifBtn.dataset.active !== "true";
      const res = await apiPost("/api/settings/update", { notifications_enabled: newState });
      if (res && res.status === "success") {
        state.settings = res.settings;
        setToggleUI("toggle-notifications", "toggle-notifications-knob", newState);
        showToast("Notifications " + (newState ? "Enabled" : "Disabled"),
          newState ? "Native Windows toast alerts are now on." : "Native Windows toast alerts are now off.",
          "brand-blue");
      }
    });
  }

  const minTrayBtn = document.getElementById("toggle-minimize-tray");
  if (minTrayBtn) {
    minTrayBtn.addEventListener("click", async () => {
      const newState = minTrayBtn.dataset.active !== "true";
      const res = await apiPost("/api/settings/update", { minimize_to_tray_on_close: newState });
      if (res && res.status === "success") {
        state.settings = res.settings;
        setToggleUI("toggle-minimize-tray", "toggle-minimize-tray-knob", newState);
        showToast("Setting Updated",
          newState ? "Closing the window will minimize to tray." : "Closing the window will exit the app.",
          "brand-blue");
      }
    });
  }
}

// Tab Navigation Transitions
function initTabsNavigation() {
  const tabs = [
    { tab: "studio", view: "view-mixer" },
    { tab: "room-cal", view: "view-room-cal" },
    { tab: "receiver", view: "view-receiver" },
    { tab: "settings", view: "view-settings" }
  ];
  
  tabs.forEach(item => {
    const btn = document.getElementById(`tab-${item.tab}`);
    if (btn) {
      btn.addEventListener("click", () => {
        // Change view
        tabs.forEach(t => {
          const subview = document.getElementById(t.view);
          const tabBtn = document.getElementById(`tab-${t.tab}`);
          if (subview) {
            if (t.tab === item.tab) {
              subview.classList.remove("hidden");
              subview.classList.add("flex");
            } else {
              subview.classList.add("hidden");
              subview.classList.remove("flex");
            }
          }
          if (tabBtn) {
            if (t.tab === item.tab) {
              tabBtn.className = "px-4 py-2 rounded-xl text-xs font-bold tracking-wider font-mono uppercase bg-amber-500 text-black hover:bg-amber-400 transition-all flex items-center gap-2";
            } else {
              tabBtn.className = "px-4 py-2 rounded-xl text-xs font-bold tracking-wider font-mono uppercase bg-zinc-950 border border-zinc-850 text-zinc-400 hover:text-white transition-all flex items-center gap-2";
            }
          }
        });

        // Set contextual helper text
        const helper = document.getElementById("infoHelperText");
        if (helper) {
          if (item.tab === "studio") {
            helper.innerText = "Mixer cards simulate hardware output cabinets. Each cone dynamically vibrates to show active acoustic pressure.";
          } else if (item.tab === "room-cal") {
            helper.innerText = "Acoustic Room Corrections calibrate sound phase timings to establish optimal sweet-spot focus.";
          } else if (item.tab === "receiver") {
            helper.innerText = "Receiver Console manages dynamic source profiles, hardware inputs, and ambient soundstage presets.";
          } else if (item.tab === "settings") {
            helper.innerText = "Studio configuration parameters controls LFE crossovers, latency modes, and accent theme aesthetics.";
          }
        }

        state.currentView = item.tab;
        showToast("View Updated", `Switched layout viewport to ${item.tab.replace("-", " ").toUpperCase()}`, "brand-blue");
      });
    }
  });
}

// Room Calibrations slider bindings & labels sync
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

function applyCalibrationUI() {
  const settings = state.settings;
  const enabled = settings.calibration_enabled !== false;
  
  const btn = document.getElementById("toggle-calibration");
  const indicator = document.getElementById("calibration-indicator");
  const btnText = document.getElementById("calibration-btn-text");
  
  if (btn && indicator && btnText) {
    if (enabled) {
      btnText.innerText = "Active";
      btnText.className = "text-zinc-300";
      indicator.className = "w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]";
    } else {
      btnText.innerText = "Bypassed";
      btnText.className = "text-zinc-505";
      indicator.className = "w-1.5 h-1.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.7)]";
    }
  }

  const delayGrid = document.querySelector("#view-room-cal .grid");
  const eqGrid = document.querySelector("#view-room-cal .flex-col.gap-3.5");
  const calSvg = document.getElementById("cal-svg");

  if (enabled) {
    if (delayGrid) delayGrid.classList.remove("calibration-dimmed");
    if (eqGrid) eqGrid.classList.remove("calibration-dimmed");
    if (calSvg) calSvg.classList.remove("calibration-dimmed");
  } else {
    if (delayGrid) delayGrid.classList.add("calibration-dimmed");
    if (eqGrid) eqGrid.classList.add("calibration-dimmed");
    if (calSvg) calSvg.classList.add("calibration-dimmed");
  }

  const clickX = settings.calibration_focus_x ?? 200;
  const clickY = settings.calibration_focus_y ?? 240;

  const focusPoint = document.getElementById("focus-point");
  const focusGlow = document.getElementById("focus-glow-circle");
  
  if (focusPoint) {
    focusPoint.setAttribute("cx", clickX);
    focusPoint.setAttribute("cy", clickY);
  }
  if (focusGlow) {
    focusGlow.setAttribute("cx", clickX);
    focusGlow.setAttribute("cy", clickY);
    focusGlow.style.transformOrigin = `${clickX}px ${clickY}px`;
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
      if (lblDist) lblDist.innerText = `${meters} m`;
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
}

// Room Calibrations slider bindings & labels sync
function initRoomCalibrations() {
  const calIds = ["surroundL", "towerL", "center", "subwoofer", "towerR", "surroundR"];
  
  const speakers = {
    towerL: { x: 100, y: 80 },
    towerR: { x: 300, y: 80 },
    center: { x: 200, y: 60 },
    subwoofer: { x: 270, y: 60 },
    surroundL: { x: 70, y: 300 },
    surroundR: { x: 330, y: 300 }
  };

  const calSvg = document.getElementById("cal-svg");
  if (calSvg) {
    calSvg.addEventListener("click", async (e) => {
      const rect = calSvg.getBoundingClientRect();
      const clickX = ((e.clientX - rect.left) / rect.width) * 400;
      const clickY = ((e.clientY - rect.top) / rect.height) * 400;

      const focusPoint = document.getElementById("focus-point");
      const focusGlow = document.getElementById("focus-glow-circle");
      
      if (focusPoint) {
        focusPoint.setAttribute("cx", clickX);
        focusPoint.setAttribute("cy", clickY);
      }
      if (focusGlow) {
        focusGlow.setAttribute("cx", clickX);
        focusGlow.setAttribute("cy", clickY);
        focusGlow.style.transformOrigin = `${clickX}px ${clickY}px`;
      }

      calIds.forEach(id => {
        const line = document.getElementById(`line-${id}`);
        if (line) {
          line.setAttribute("x2", clickX);
          line.setAttribute("y2", clickY);
        }
      });

      // Post coordinates to backend for physical delays calculation
      const res = await apiPost("/api/calibration/optimize", { x: clickX, y: clickY });
      if (res && res.status === "success") {
        state.settings.calibration_focus_x = clickX;
        state.settings.calibration_focus_y = clickY;
        state.settings.calibration_delays = res.delays;
        
        calIds.forEach(id => {
          const rawVal = res.delays[id];
          const meters = res.distances[id];
          const ms = (rawVal / 10).toFixed(1);

          const slider = document.getElementById(`delay-${id}`);
          const lblDelay = document.getElementById(`lbl-delay-${id}`);
          const lblDist = document.getElementById(`lbl-dist-${id}`);

          if (slider) slider.value = rawVal;
          if (lblDelay) lblDelay.innerText = `${ms} ms`;
          if (lblDist) lblDist.innerText = `${meters} m`;
        });
        showToast("Sweet-Spot Focused", `Recalibrated sound phase focal target to coordinates [${Math.round(clickX)}, ${Math.round(clickY)}].`, "brand-blue");
      }
    });
  }
  
  calIds.forEach(id => {
    const slider = document.getElementById(`delay-${id}`);
    if (slider) {
      slider.addEventListener("input", (e) => {
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

  // EQ sliders
  const eqBands = ["bass", "mid", "treble"];
  eqBands.forEach(band => {
    const slider = document.getElementById(`eq-${band}`);
    if (slider) {
      slider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        const lbl = document.getElementById(`lbl-eq-${band}`);
        if (lbl) {
          lbl.innerText = (val >= 0 ? "+" : "") + val.toFixed(1) + " dB";
        }
        saveCalibrationEQ();
      });
    }
  });

  // Correction optimize button
  const optBtn = document.getElementById("btnAcousticCorrection");
  if (optBtn) {
    optBtn.addEventListener("click", async () => {
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

  // Room Calibration toggle button binding
  const calToggleBtn = document.getElementById("toggle-calibration");
  if (calToggleBtn) {
    calToggleBtn.addEventListener("click", async () => {
      const current = state.settings.calibration_enabled !== false;
      const newState = !current;
      
      const res = await apiPost("/api/settings/update", { calibration_enabled: newState });
      if (res && res.status === "success") {
        state.settings.calibration_enabled = newState;
        applyCalibrationUI();
        
        if (newState) {
          showToast("Calibration Active", "Room acoustic corrections and phase delay offsets applied.", "brand-blue");
        } else {
          showToast("Calibration Bypassed", "Phase delays and equalization bypassed (Raw stream output).", "brand-amber");
        }
      }
    });
  }
}

// Home Theater Receiver selections bindings
function initReceiverConsole() {
  const sources = [
    { btn: "btnSrcHdmi1", name: "HDMI 1 / eARC" },
    { btn: "btnSrcHdmi2", name: "HDMI 2 Source" },
    { btn: "btnSrcOptical", name: "Optical S/PDIF" },
    { btn: "btnSrcBluetooth", name: "Bluetooth 5.0" }
  ];

  sources.forEach(src => {
    const btn = document.getElementById(src.btn);
    if (btn) {
      btn.addEventListener("click", () => {
        // Toggle active states
        sources.forEach(s => {
          const b = document.getElementById(s.btn);
          if (b) {
            if (s.name === src.name) {
              b.className = "py-2.5 rounded-xl text-xs font-mono font-bold bg-amber-500 text-black uppercase transition-all";
            } else {
              b.className = "py-2.5 rounded-xl text-xs font-mono font-bold bg-zinc-950 border border-zinc-850 text-zinc-400 hover:text-white uppercase transition-all";
            }
          }
        });
        
        state.receiverInput = src.name;
        const inputDisplay = document.getElementById("avrDisplayInput");
        if (inputDisplay) inputDisplay.innerText = src.name;
        showToast("Source Changed", `AV receiver input set to ${src.name}`, "brand-blue");
      });
    }
  });

  const dspModes = [
    { btn: "btnDspAtmos", name: "ATMOS STANDARD" },
    { btn: "btnDspCinema", name: "STUDIO CINEMA" },
    { btn: "btnDspDirect", name: "PURE DIRECT" },
    { btn: "btnDspGame", name: "GAME PRO" }
  ];

  dspModes.forEach(dsp => {
    const btn = document.getElementById(dsp.btn);
    if (btn) {
      btn.addEventListener("click", () => {
        // Toggle active states
        dspModes.forEach(d => {
          const b = document.getElementById(d.btn);
          if (b) {
            if (d.name === dsp.name) {
              b.className = "py-2 rounded-xl text-[10px] font-mono font-bold bg-amber-500 text-black uppercase transition-all";
            } else {
              b.className = "py-2 rounded-xl text-[10px] font-mono font-bold bg-zinc-950 border border-zinc-850 text-zinc-400 hover:text-white uppercase transition-all";
            }
          }
        });

        state.receiverDSP = dsp.name;
        const dspDisplay = document.getElementById("avrDisplayDSP");
        if (dspDisplay) dspDisplay.innerText = dsp.name;
        showToast("DSP Mode Active", `Surround sound field presets set to ${dsp.name}`, "brand-blue");
      });
    }
  });

  // DRC button
  const drcBtn = document.getElementById("btnToggleDRC");
  if (drcBtn) {
    drcBtn.addEventListener("click", () => {
      state.drcActive = !state.drcActive;
      const drcDisplay = document.getElementById("lblDRC");
      if (state.drcActive) {
        drcBtn.innerText = "Active";
        drcBtn.className = "px-4 py-1.5 rounded-lg bg-emerald-600 text-white font-mono text-[10px] font-bold uppercase transition-all";
        if (drcDisplay) drcDisplay.innerText = "NIGHT MODE (ON)";
        showToast("DRC Enabled", "Dynamic Range Compression active (Night Mode).", "brand-blue");
      } else {
        drcBtn.innerText = "Bypass";
        drcBtn.className = "px-4 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-400 font-mono text-[10px] font-bold uppercase transition-all";
        if (drcDisplay) drcDisplay.innerText = "BYPASS (RAW DYNAMIC)";
        showToast("DRC Disabled", "Dynamic Range Compression disabled (Raw Dynamic).", "brand-blue");
      }
    });
  }
}

// Settings Low-pass Crossover
function initSettingsView() {
  const crossoverSelect = document.getElementById("set-crossover");
  if (crossoverSelect) {
    crossoverSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      state.crossoverVal = `${val} Hz`;
      
      const crossoverDisplay = document.getElementById("infoCrossoverVal");
      if (crossoverDisplay) crossoverDisplay.innerText = state.crossoverVal;
      showToast("Crossover Updated", `LFE low-pass cutoff filter set to ${val} Hz.`, "brand-blue");
    });
  }
}

// Update fader track/thumb progress bar widths
function updateFaderUI(id, value) {
  const valDisplay = document.getElementById('val-' + id);
  const track = document.getElementById('track-' + id);
  const thumb = document.getElementById('thumb-' + id);
  const muteIcon = document.getElementById('mute-icon-' + id);

  if (valDisplay) {
    valDisplay.innerText = state.isSystemMuted ? "MUTE" : value + "%";
  }

  const fillPercent = state.isSystemMuted ? 0 : value;
  if (track) track.style.width = fillPercent + "%";
  if (thumb) thumb.style.left = fillPercent + "%";

  if (muteIcon) {
    if (value === 0 || state.isSystemMuted) {
      muteIcon.className = "fa-solid fa-volume-xmark text-[8px] text-red-500";
    } else {
      muteIcon.className = "fa-solid fa-volume-high text-[8px] text-zinc-650";
    }
  }
}

function updateMasterUI(value) {
  const valDisplay = document.getElementById('val-master');
  const track = document.getElementById('track-master');
  const thumb = document.getElementById('thumb-master');

  if (valDisplay) {
    valDisplay.innerText = state.isSystemMuted ? "MUTE" : value + "%";
  }

  const fillPercent = state.isSystemMuted ? 0 : value;
  if (track) track.style.height = fillPercent + "%";
  if (thumb) thumb.style.bottom = fillPercent + "%";
  
  // Sync Receiver display volume
  const avrVolDisplay = document.getElementById("avrDisplayVol");
  if (avrVolDisplay) avrVolDisplay.innerText = state.isSystemMuted ? "MUTE" : value + "%";
}

function updateAllFadersUI() {
  ids.forEach(id => {
    updateFaderUI(id, state.volumes[id]);
  });
  updateMasterUI(state.volumes["master"]);
}

// Refresh Audio Devices list
async function refreshDevices() {
  const icon = document.getElementById("iconRefresh");
  if (icon) icon.classList.add("fa-spin");
  
  const data = await apiGet("/api/devices");
  if (icon) icon.classList.remove("fa-spin");

  if (!data) return;

  const selector = document.getElementById("deviceSelector");
  selector.innerHTML = "";

  if (data.devices && data.devices.length > 0) {
    data.devices.forEach(dev => {
      const opt = document.createElement("option");
      opt.value = dev;
      opt.textContent = dev;
      if (dev === data.active_device) {
        opt.selected = true;
      }
      selector.appendChild(opt);
    });
    showToast("Audio Devices Loaded", "System output hardware configurations synced.", "brand-blue");
    updateAppStatus();
  } else {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No Devices Detected";
    opt.disabled = true;
    opt.selected = true;
    selector.appendChild(opt);
    showToast("Hardware Warning", "No active output devices found.", "brand-amber");
  }
}

// Selector updates
async function onDeviceSelected() {
  const selector = document.getElementById("deviceSelector");
  const res = await apiPost("/api/select_device", { device: selector.value });
  if (res && res.status === "success") {
    showToast("Output Updated", `Active output device set to ${selector.value}`, "brand-blue");
    updateAppStatus();
  }
}

// Sync volume from sliders
const sendChannelVolume = debounce((idx, value) => {
  apiPost("/api/channel_volume", { channel: idx, volume: value });
}, 80);

const sendMasterVolume = debounce((value) => {
  apiPost("/api/master_volume", { volume: value });
}, 80);

// Polling daemon
async function pollVolumeChanges() {
  if (state.isUserDragging || state.sweepActive) return;
  updateAppStatus();
}

// Sync values from backend to frontend
async function updateAppStatus() {
  const data = await apiGet("/api/status");
  if (!data || data.status !== "success") return;

  state.channelCount = data.channel_count;
  state.isSystemMuted = data.muted;
  state.currentDeviceName = data.active_device;

  // Update System Mute button text/styles
  const sysMuteBtn = document.getElementById("mute-btn");
  const muteIcon = document.getElementById("muteIcon");
  if (sysMuteBtn) {
    if (state.isSystemMuted) {
      sysMuteBtn.className = "w-10 h-10 rounded-full bg-red-600 hover:bg-red-500 text-white flex items-center justify-center shadow-lg shadow-red-950/40 border border-red-500/20 transition-all cursor-pointer";
      if (muteIcon) muteIcon.className = "fa-solid fa-volume-xmark text-xs";
    } else {
      sysMuteBtn.className = "w-10 h-10 rounded-full bg-zinc-950 hover:bg-zinc-900 border border-zinc-850 text-zinc-300 flex items-center justify-center shadow-lg transition-all cursor-pointer";
      if (muteIcon) muteIcon.className = "fa-solid fa-volume-high text-xs";
    }
  }

  // Handle active channel displays
  const isStereo = state.channelCount === 2;
  const sysMode = document.getElementById("systemMode");
  if (sysMode) {
    const fs = document.getElementById("formatSelector");
    if (fs) {
      if (fs.value === "dolby-digital") {
        sysMode.innerText = "Dolby Digital Live 5.1";
      } else if (fs.value === "24-48000") {
        sysMode.innerText = isStereo ? "Stereo 24-bit / 48kHz" : "24-bit / 48kHz PCM";
      } else if (fs.value === "24-44100") {
        sysMode.innerText = isStereo ? "Stereo 24-bit / 44.1kHz" : "24-bit / 44.1kHz PCM";
      } else if (fs.value === "16-48000") {
        sysMode.innerText = isStereo ? "Stereo 16-bit / 48kHz" : "16-bit / 48kHz PCM";
      } else if (fs.value === "16-44100") {
        sysMode.innerText = isStereo ? "Stereo 16-bit / 44.1kHz" : "16-bit / 44.1kHz CD";
      } else if (fs.value === "16-32000") {
        sysMode.innerText = isStereo ? "Stereo 16-bit / 32kHz" : "16-bit / 32kHz FM";
      }
    } else {
      sysMode.innerText = isStereo ? "Stereo 2.0 Mode" : "Dolby Digital for a Hometheater";
    }
  }

  // Master Volume sync
  if (!state.isUserDragging) {
    state.volumes["master"] = data.master_volume;
    const masterSlider = document.getElementById("slider-master");
    if (masterSlider) masterSlider.value = data.master_volume;
  }

  // Channels sync
  ids.forEach(id => {
    const isInactive = isStereo && (id === "center" || id === "subwoofer" || id === "surroundL" || id === "surroundR");
    const card = document.getElementById(`card-${id}`);
    const slider = document.getElementById(`slider-${id}`);

    if (card) {
      if (isInactive) {
        card.classList.add("opacity-25", "pointer-events-none");
      } else {
        card.classList.remove("opacity-25", "pointer-events-none");
      }
    }

    if (slider && !state.isUserDragging) {
      const idx = channelIndexMap[id];
      if (data.channel_volumes && data.channel_volumes[idx] !== undefined) {
        const val = data.channel_volumes[idx];
        state.volumes[id] = val;
        slider.value = val;

        const muteIcon = document.getElementById("mute-icon-" + id);
        if (muteIcon) {
          if (val === 0) {
            muteIcon.className = "fa-solid fa-volume-xmark text-[8px] text-red-500";
          } else {
            muteIcon.className = "fa-solid fa-volume-high text-[8px] text-zinc-650";
          }
        }
      }
    }
  });

  updateAllFadersUI();

  // Sync speaker solo/isolate state (server is the source of truth, so this
  // stays correct even if the tray, another browser tab, or a page reload
  // changed it).
  if (data.solo) {
    const changed = data.solo.active !== state.solo.active || data.solo.channel !== state.solo.channel;
    state.solo = { active: !!data.solo.active, channel: data.solo.channel };
    if (changed) applySoloVisuals();
  }
}

// Toggle global system mute
async function toggleSystemMute() {
  const res = await apiPost("/api/toggle_mute");
  if (res && res.status === "success") {
    state.isSystemMuted = res.muted;
    showToast(
      state.isSystemMuted ? "System Muted" : "System Active",
      state.isSystemMuted ? "Hardware master output silenced." : "Acoustic channels active.",
      state.isSystemMuted ? "brand-amber" : "brand-blue"
    );
    updateAppStatus();
  }
}

// Reset fader balances
async function resetBalance() {
  showToast("Reset Balance", "Resetting all speaker channels to 100% gain...", "brand-blue");
  saveUserPreset();
  const res = await apiPost("/api/reset_balance");
  if (res && res.status === "success") {
    updateAppStatus();
  }
}

// Sequential sound sweeps
async function runSequentialSweep() {
  const testIcon = document.getElementById('testIcon');
  if (state.sweepActive) {
    clearInterval(state.sweepInterval);
    state.sweepActive = false;
    if (testIcon) testIcon.className = "fa-solid fa-volume-high text-xs";
    clearSweepHighlights();
    showToast("Sweep Stopped", "Sequential channel check cancelled.", "brand-blue");
    return;
  }

  state.sweepActive = true;
  if (testIcon) testIcon.className = "fa-solid fa-circle-notch fa-spin text-xs text-blue-400";
  showToast("Sweep Active", "Triggering sequential surround sound diagnostic sweep...", "brand-blue");

  const sweepOrder = ["towerL", "center", "towerR", "surroundR", "surroundL", "subwoofer"];
  let currentIdx = 0;

  const playNextTone = async () => {
    if (!state.sweepActive) return;
    const activeKey = sweepOrder[currentIdx];
    const idx = channelIndexMap[activeKey];

    clearSweepHighlights();
    const activeCard = document.getElementById(`card-${activeKey}`);
    if (activeCard) {
      activeCard.classList.add('border-amber-500/80', 'bg-amber-950/10', 'scale-105', 'shadow-[0_0_15px_rgba(245,158,11,0.4)]');
    }

    await apiPost('/api/test_channel', { channel: idx });
    currentIdx = (currentIdx + 1) % sweepOrder.length;
  };

  await playNextTone();
  state.sweepInterval = setInterval(playNextTone, 1400); // 1.4s per speaker
}

function clearSweepHighlights() {
  ids.forEach(id => {
    const card = document.getElementById(`card-${id}`);
    if (card) {
      card.classList.remove(
        'border-purple-500/80', 'bg-purple-950/10',
        'border-amber-500/80', 'bg-amber-950/10', 'scale-105', 'shadow-[0_0_15px_rgba(245,158,11,0.4)]'
      );
    }
  });
}

// Oscilloscope & Bar Spectrum Canvas visualizer
let offset = 0;
let scopeCanvas, scopeCtx;
let visualizerMode = "waveform"; // cycles: waveform -> bars -> pixel

function initOscilloscope() {
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

  if (visualizerMode === "waveform") {
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

  } else if (visualizerMode === "bars") {
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
      
      // Draw neon glow top block
      scopeCtx.fillStyle = "rgba(255, 255, 255, 0.45)";
      scopeCtx.fillRect(x, y, barWidth, 1.2);
    }

  } else if (visualizerMode === "pixel") {
    scopeCtx.fillStyle = "#3b82f6"; // neon blue pixel matrix
    const step = 6;
    for (let x = 0; x < width; x += step) {
      let y = centerY;
      y += Math.sin(x * 0.03 + offset) * amp * volumeFactor;
      y += Math.cos(x * 0.07 - offset * 1.3) * (amp * 0.4) * volumeFactor;
      
      // Snap to 4px grid grid
      const gridY = Math.round(y / 4) * 4;
      scopeCtx.fillRect(x, gridY, 3, 3);
    }
  }

  // Speed of wave scrolling scales with the audio intensity
  const peakVal = Math.max(state.windowsAudioPeak, (window.mediaPlayerIsPlaying) ? 0.12 : 0.0);
  const speed = 0.06 + (peakVal * 0.12);
  offset += speed;
  requestAnimationFrame(animateScope);
}

// Speaker pulsing and driver vibrating animations loop
let pulseAngle = 0;
let peakHistory = [];
const historyLen = 12;
let currentBassGlow = 0.0;
let prevPeak = 0.0;

function animateSpeakerPulses() {
  if (!state.isSystemMuted) {
    pulseAngle += 0.10;
    
    // Use real-time audio peak, falling back to a subtle 15% idle pulse
    const localPeak = (window.mediaPlayerIsPlaying) ? (0.12 + Math.sin(Date.now() / 100) * 0.05) : 0.0;
    const peak = Math.max(state.windowsAudioPeak, localPeak);
    const pulse = peak > 0.015 ? peak : Math.sin(pulseAngle) * 0.15;
    
    // Beat detector algorithm
    peakHistory.push(peak);
    if (peakHistory.length > historyLen) {
      peakHistory.shift();
    }
    const averagePeak = peakHistory.reduce((sum, p) => sum + p, 0) / peakHistory.length;
    
    let bassIntensity = 0.0;
    const derivative = peak - prevPeak;
    if (peak > 0.18 && derivative > 0.08) {
      const threshold = 1.25;
      if (peak > averagePeak * threshold) {
        bassIntensity = Math.min(1.0, (peak - averagePeak * threshold) * 6 + 0.4);
      }
    }
    prevPeak = peak;

    // Smooth release decay
    if (bassIntensity > currentBassGlow) {
      currentBassGlow = bassIntensity; // instant attack
    } else {
      currentBassGlow = currentBassGlow * 0.83; // release decay
    }

    // Apply Subwoofer animations
    const neonRing = document.getElementById("subwoofer-neon-ring");
    const airRipple1 = document.getElementById("air-ripple-1");
    const airRipple2 = document.getElementById("air-ripple-2");

    if (neonRing) {
      neonRing.setAttribute("stroke-width", (currentBassGlow * 3.8).toFixed(1));
      neonRing.setAttribute("opacity", (currentBassGlow * 0.95).toFixed(2));
    }

    if (airRipple1) {
      airRipple1.setAttribute("opacity", (currentBassGlow * 0.90).toFixed(2));
      airRipple1.setAttribute("transform", `translate(0, ${currentBassGlow * 8})`);
    }

    if (airRipple2) {
      airRipple2.setAttribute("opacity", (currentBassGlow * 0.70).toFixed(2));
      airRipple2.setAttribute("transform", `translate(0, ${currentBassGlow * 15})`);
    }

    ids.forEach(id => {
      const vol = state.volumes[id] / 100;
      const speaker = document.getElementById('speaker-wrapper-' + id);
      if (speaker) {
        let multiplier = 0.05;
        let pulseValue = Math.abs(pulse);
        if (id === "subwoofer") {
          multiplier = 0.09;
          pulseValue = currentBassGlow; // Shake subwoofer cabinet only to bass kicks
        } else if (id === "surroundL" || id === "surroundR") {
          multiplier = 0.03;
        }

        const scale = 1 + (pulseValue * vol * multiplier);
        speaker.style.transform = "scale(" + scale + ")";
      }

      const cone = document.getElementById('cone-' + id);
      if (cone) {
        // Driver only vibrates physically when music is actually playing
        const driverVib = (id === "subwoofer") ? currentBassGlow : (peak > 0.015 ? peak : 0.0);
        const vibration = 1.0 + (vol * 0.07 * driverVib * (Math.random() * 0.4 + 0.6));
        cone.style.transform = `scale(${vibration})`;
      }

      // Dynamic speaker glow light positioning, scale and opacity
      const glowLight = document.getElementById('glow-light-' + id);
      if (glowLight) {
        if (vol === 0) {
          glowLight.style.opacity = '0';
          glowLight.style.transform = 'scale(0.8)';
        } else {
          // Glow intensity and scale react directly to the audio beat
          const pulseValue = (id === "subwoofer") ? currentBassGlow : Math.abs(pulse);
          const glowOpacity = vol * 0.45 * (0.85 + pulseValue * 0.15);
          const glowScale = 0.8 + vol * 0.4 + (pulseValue * 0.06);
          glowLight.style.opacity = glowOpacity;
          glowLight.style.transform = `scale(${glowScale})`;
        }
      }

      // Dynamic sound wave container opacity
      const waves = document.getElementById('waves-' + id);
      if (waves) {
        if (vol === 0 || peak <= 0.015) {
          waves.style.opacity = '0';
        } else {
          // Ripples grow stronger as the volume and system peak increase
          const wavePeak = (id === "subwoofer") ? currentBassGlow : peak;
          waves.style.opacity = (vol * 0.7 * wavePeak + 0.25).toString();
        }
      }
    });
  } else {
    // Reset bass glow elements when muted
    currentBassGlow = 0.0;
    const neonRing = document.getElementById("subwoofer-neon-ring");
    const airRipple1 = document.getElementById("air-ripple-1");
    const airRipple2 = document.getElementById("air-ripple-2");
    if (neonRing) {
      neonRing.setAttribute("stroke-width", "0");
      neonRing.setAttribute("opacity", "0");
    }
    if (airRipple1) {
      airRipple1.setAttribute("opacity", "0");
      airRipple1.setAttribute("transform", "translate(0, 0)");
    }
    if (airRipple2) {
      airRipple2.setAttribute("opacity", "0");
      airRipple2.setAttribute("transform", "translate(0, 0)");
    }

    ids.forEach(id => {
      const speaker = document.getElementById('speaker-wrapper-' + id);
      if (speaker) speaker.style.transform = "scale(1)";

      const cone = document.getElementById('cone-' + id);
      if (cone) cone.style.transform = '';

      const glowLight = document.getElementById('glow-light-' + id);
      if (glowLight) {
        glowLight.style.opacity = '0';
        glowLight.style.transform = 'scale(0.8)';
      }

      const waves = document.getElementById('waves-' + id);
      if (waves) {
        waves.style.opacity = '0';
      }
    });
  }
  requestAnimationFrame(animateSpeakerPulses);
}

// Debounce helper
function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// Floating Toast Alert replaced with native Windows Notification push
function showToast(title, desc, color) {
  apiPost("/api/notify", {
    title: title,
    message: desc,
    dedupe_key: title.toLowerCase().replace(/\s+/g, "_")
  });
}

// Establishes a persistent SSE connection to stream Windows audio peak levels
function initWindowsAudioSync() {
  const eventSource = new EventSource("/api/audio_stream");
  
  eventSource.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);
      if (data && typeof data.peak === "number") {
        // Low-pass filter (smoothing) to prevent sudden jumps
        state.windowsAudioPeak = state.windowsAudioPeak * 0.25 + data.peak * 0.75;
      }
    } catch (e) {
      console.error("Audio stream parse error:", e);
    }
  };

  eventSource.onerror = function(e) {
    eventSource.close();
    // Auto-reconnect after 3 seconds if the connection fails or drops
    setTimeout(initWindowsAudioSync, 3000);
  };
}

// Visual preset buttons highlights
function highlightPreset(profileName) {
  const buttons = document.querySelectorAll(".preset-btn");
  buttons.forEach(btn => {
    btn.className = "preset-btn px-4 py-2 rounded-xl text-[10px] font-mono font-bold uppercase transition-all duration-300 border border-zinc-900 bg-zinc-950 text-zinc-400 hover:text-zinc-200 cursor-pointer flex items-center gap-1.5";
  });
  
  if (profileName && profileName !== "Custom") {
    const activeBtn = document.getElementById(`preset-${profileName}`);
    if (activeBtn) {
      activeBtn.classList.add(`active-${profileName}`);
    }
  }
}

// Save user preset channels and highlight active User state
const saveUserPreset = debounce(() => {
  const channels = {};
  ids.forEach(id => {
    const slider = document.getElementById(`slider-${id}`);
    if (slider) {
      channels[id] = parseInt(slider.value);
    }
  });
  
  const masterSlider = document.getElementById("slider-master");
  const masterVal = masterSlider ? parseInt(masterSlider.value) : 85;

  state.settings.active_profile = "User";
  highlightPreset("User");
  
  apiPost("/api/settings/update", {
    active_profile: "User",
    user_preset_channels: channels,
    user_preset_master: masterVal
  });
}, 300);

// Binds clicks to request audio presets from backend
function initAcousticPresets() {
  const buttons = document.querySelectorAll(".preset-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", async () => {
      const preset = btn.dataset.preset;
      showToast("Applying Preset", `Loading acoustic parameters for ${preset}...`, "brand-blue");
      
      const res = await apiPost("/api/profile/apply", { profile: preset });
      if (res && res.status === "success") {
        state.settings.active_profile = preset;
        highlightPreset(preset);
        
        // Sync master volume from profile if returned
        if (res.master !== undefined && res.master !== null) {
          state.volumes["master"] = res.master;
          updateMasterUI(res.master);
          const masterSlider = document.getElementById("slider-master");
          if (masterSlider) masterSlider.value = res.master;
        }

        // Smoothly fade channel volumes to the new preset targets
        ids.forEach(id => {
          const idx = channelIndexMap[id];
          if (res.channels && res.channels[idx] !== undefined) {
            const targetVal = res.channels[idx];
            fadeChannelVolume(id, targetVal);
          }
        });
        
        showToast("Preset Applied", `${preset} soundstage mode activated.`, "brand-blue");
      }
    });
  });
}

// ------------------------------------------------------------------
// Smooth Preset Volume Fading
// Buttery-smooth visual interpolation in the UI (~60 FPS) with throttled 
// network updates to prevent Pycaw/network congestion.
// ------------------------------------------------------------------
let fadeIntervals = {};

function fadeChannelVolume(channelId, targetVol) {
  if (fadeIntervals[channelId]) clearInterval(fadeIntervals[channelId]);
  
  const startVol = state.volumes[channelId];
  if (startVol === targetVol) return;

  const duration = 500; // 0.5s transition
  const intervalTime = 16; // ~60 FPS
  const totalSteps = Math.round(duration / intervalTime);
  let currentStep = 0;
  
  fadeIntervals[channelId] = setInterval(() => {
    currentStep++;
    const progress = currentStep / totalSteps;
    
    // Cubic ease-out curve for premium feedback feel
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    const currentVal = Math.round(startVol + (targetVol - startVol) * easeProgress);
    
    state.volumes[channelId] = currentVal;
    updateFaderUI(channelId, currentVal);
    
    const slider = document.getElementById("slider-" + channelId);
    if (slider) slider.value = currentVal;

    // Send update to Pycaw server at throttled interval (every 96ms) or at final step
    if (currentStep % 6 === 0 || currentStep === totalSteps) {
      const idx = channelIndexMap[channelId];
      sendChannelVolume(idx, currentVal);
    }
    
    if (currentStep >= totalSteps) {
      clearInterval(fadeIntervals[channelId]);
    }
  }, intervalTime);
}

// ------------------------------------------------------------------
// Mini Media Player & Web Audio API Ambient Synthesizer
// Plays 100% client-side synthesized soundscapes so the system works
// completely offline while vibrantly animating the oscilloscope.
// ------------------------------------------------------------------
window.mediaPlayerIsPlaying = false;
let windowsMediaActive = false;
let lastWindowsMediaB64 = "";

function initMediaPlayer() {
  const playBtn = document.getElementById("player-play-btn");
  const prevBtn = document.getElementById("player-prev-btn");
  const nextBtn = document.getElementById("player-next-btn");

  if (playBtn) playBtn.addEventListener("click", togglePlay);
  if (prevBtn) prevBtn.addEventListener("click", playPrev);
  if (nextBtn) nextBtn.addEventListener("click", playNext);

  resetPlayerUI();
  
  // Poll Windows global media session state every 800ms
  setInterval(pollWindowsMedia, 800);
}

function togglePlay() {
  if (windowsMediaActive) {
    apiPost("/api/media/control", { action: "play_pause" });
  }
}

function playPrev() {
  if (windowsMediaActive) {
    apiPost("/api/media/control", { action: "previous" });
  }
}

function playNext() {
  if (windowsMediaActive) {
    apiPost("/api/media/control", { action: "next" });
  }
}

function resetPlayerUI() {
  const titleEl = document.getElementById("player-title");
  const artistEl = document.getElementById("player-artist");
  const badgeEl = document.getElementById("player-badge");
  const playIcon = document.getElementById("player-play-icon");
  const record = document.getElementById("player-record");
  const progressBar = document.getElementById("player-progress");
  const currentTimeEl = document.getElementById("player-current-time");
  const durationTimeEl = document.getElementById("player-duration");
  const artImg = document.getElementById("player-art-img");

  if (titleEl) titleEl.innerText = "No Active Media";
  if (artistEl) artistEl.innerText = "Play audio on Windows (e.g. YouTube, Spotify)";
  
  if (badgeEl) {
    badgeEl.innerText = "IDLE";
    badgeEl.className = "text-[7px] font-mono text-zinc-500 bg-zinc-500/10 px-1 py-0.2 rounded border border-zinc-500/20 font-bold flex-shrink-0";
  }

  if (playIcon) playIcon.className = "fa-solid fa-play text-xs ml-0.5";
  if (record) record.classList.add("paused-animation");
  if (progressBar) progressBar.style.width = "0%";
  if (currentTimeEl) currentTimeEl.innerText = "0:00";
  if (durationTimeEl) durationTimeEl.innerText = "0:00";
  if (artImg) {
    artImg.classList.add("hidden");
    artImg.src = "";
  }
  
  window.mediaPlayerIsPlaying = false;
  lastWindowsMediaB64 = "";
}

async function pollWindowsMedia() {
  try {
    const data = await apiGet("/api/media/status");
    if (data && data.status === "success") {
      windowsMediaActive = true;
      
      const titleEl = document.getElementById("player-title");
      const artistEl = document.getElementById("player-artist");
      const badgeEl = document.getElementById("player-badge");
      
      if (titleEl) titleEl.innerText = data.title || "Unknown Title";
      if (artistEl) {
        const sourceName = data.source ? data.source.split('.').pop() : "System";
        artistEl.innerText = `${data.artist || "Unknown Artist"} • ${sourceName}`;
      }
      
      if (badgeEl) {
        badgeEl.innerText = "SYSTEM";
        badgeEl.className = "text-[7px] font-mono text-blue-400 bg-blue-500/10 px-1 py-0.2 rounded border border-blue-500/20 font-bold flex-shrink-0";
      }

      // Windows playback_status playing is 4
      const isPlaying = data.playback_status === 4;
      window.mediaPlayerIsPlaying = isPlaying; // sync scope/speaker pulses!
      
      const playIcon = document.getElementById("player-play-icon");
      if (playIcon) {
        if (isPlaying) {
          playIcon.className = "fa-solid fa-pause text-xs";
        } else {
          playIcon.className = "fa-solid fa-play text-xs ml-0.5";
        }
      }

      const record = document.getElementById("player-record");
      if (record) {
        if (isPlaying) {
          record.classList.remove("paused-animation");
        } else {
          record.classList.add("paused-animation");
        }
      }

      // Update progress bar
      const progressBar = document.getElementById("player-progress");
      const currentTimeEl = document.getElementById("player-current-time");
      const durationTimeEl = document.getElementById("player-duration");
      
      const pos = data.position || 0;
      const dur = data.duration || 1;
      const percent = (pos / dur) * 100;
      if (progressBar) progressBar.style.width = Math.min(100, Math.max(0, percent)) + "%";

      const formatTime = (seconds) => {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60).toString().padStart(2, "0");
        return `${m}:${s}`;
      };
      
      if (currentTimeEl) currentTimeEl.innerText = formatTime(pos);
      if (durationTimeEl) durationTimeEl.innerText = formatTime(dur);

      // Update thumbnail image
      const artImg = document.getElementById("player-art-img");
      if (artImg) {
        if (data.thumbnail && data.thumbnail !== lastWindowsMediaB64) {
          lastWindowsMediaB64 = data.thumbnail;
          artImg.src = "data:image/png;base64," + data.thumbnail;
          artImg.classList.remove("hidden");
        } else if (!data.thumbnail) {
          artImg.classList.add("hidden");
          lastWindowsMediaB64 = "";
        }
      }

    } else {
      if (windowsMediaActive) {
        resetPlayerUI();
      }
    }
  } catch (err) {
    console.error("Error polling Windows media status:", err);
  }
}
