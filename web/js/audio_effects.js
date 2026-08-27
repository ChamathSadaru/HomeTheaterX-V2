// Audio Effects, Presets, and Channel Control Module
import { apiPost, showToast } from './api.js';
import { state, ids, channelIndexMap, lockPollFor, setUserDragging } from './state.js';

// Local Debounce helper
function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

export let preMuteVolumes = {};
let fadeIntervals = {};

// ---------------------------------------------------------------------------
// Smooth UI fader animation helpers
// ---------------------------------------------------------------------------
export function animateFaderTo(id, targetVal, durationMs = 220) {
  const startVal = state.volumes[id] || 0;
  const startTime = performance.now();

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(startVal + (targetVal - startVal) * eased);

    state.volumes[id] = current;
    const slider = document.getElementById('slider-' + id);
    if (slider) slider.value = current;
    updateFaderUI(id, current);

    if (progress < 1) requestAnimationFrame(step);
    else {
      state.volumes[id] = targetVal;
      if (slider) slider.value = targetVal;
      updateFaderUI(id, targetVal);
    }
  }
  requestAnimationFrame(step);
}

export function animateMasterTo(targetVal, durationMs = 220) {
  const startVal = state.volumes['master'] || 0;
  const startTime = performance.now();

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(startVal + (targetVal - startVal) * eased);

    state.volumes['master'] = current;
    const slider = document.getElementById('slider-master');
    if (slider) slider.value = current;
    updateMasterUI(current);

    if (progress < 1) requestAnimationFrame(step);
    else {
      state.volumes['master'] = targetVal;
      if (slider) slider.value = targetVal;
      updateMasterUI(targetVal);
    }
  }
  requestAnimationFrame(step);
}

export function updateFaderUI(id, value) {
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

export function updateMasterUI(value) {
  const valDisplay = document.getElementById('val-master');
  const track = document.getElementById('track-master');
  const thumb = document.getElementById('thumb-master');

  if (valDisplay) {
    valDisplay.innerText = state.isSystemMuted ? "MUTE" : value + "%";
  }

  const fillPercent = state.isSystemMuted ? 0 : value;
  if (track) track.style.height = fillPercent + "%";
  if (thumb) thumb.style.bottom = fillPercent + "%";

  // Sync Receiver physical console dial and text
  if (window.updateAVRConsoleUI) {
    window.updateAVRConsoleUI();
  }
}

export function updateAllFadersUI() {
  ids.forEach(id => {
    updateFaderUI(id, state.volumes[id]);
  });
  updateMasterUI(state.volumes["master"]);
}

export const sendChannelVolume = debounce((idx, value) => {
  apiPost("/api/channel_volume", { channel: idx, volume: value });
}, 80);

export const sendMasterVolume = debounce((value) => {
  apiPost("/api/master_volume", { volume: value });
}, 80);

export const saveUserPreset = debounce(() => {
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

// ------------------------------------------------------------------
// Dolby Digital Live (DDL)
// ------------------------------------------------------------------
export function initDdlToggle() {
  const btn = document.getElementById("ddl-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      toggleDdlMode();
    });
  }
}

export async function toggleDdlMode(suppressNotification = false) {
  const btn = document.getElementById("ddl-btn");
  const spinner = document.getElementById("ddl-spinner");

  if (!suppressNotification) {
    showToast("Dolby Live Automation...", "Automating sound card properties. Please wait...", "amber");
  }

  if (btn) btn.disabled = true;
  if (spinner) spinner.classList.remove("hidden");

  const res = await apiPost("/api/apo/toggle_ddl");

  if (spinner) spinner.classList.add("hidden");
  if (btn) btn.disabled = false;

  if (res && res.status === "success") {
    state.ddlActive = res.ddl_active;
    updateDdlButtonUI();
    
    if (res.calibration_disabled) {
      state.settings.calibration_enabled = false;
      // Dynamically import to resolve circular dependency at runtime
      import('./calibration.js').then(m => m.applyCalibrationUI());
      setTimeout(() => {
        showToast("Calibration Disabled", "Room Calibration was automatically disabled — Room Calibration and Dolby Live cannot run simultaneously.", "brand-amber");
      }, 1200);
    }

    if (!suppressNotification) {
      if (state.ddlActive) {
        showToast("Dolby Digital Engaged", "Samsung Home Theater surround stream active.", "amber");
      } else {
        showToast("Dolby Digital Bypassed", "Restored standard sound configuration.", "brand-blue");
      }
    }
    if (window.updateAppStatus) window.updateAppStatus();
  } else {
    if (!suppressNotification) {
      showToast("DDL Automation Error", res ? res.message : "Failed to toggle Dolby settings.", "red");
    }
  }
}

export function updateDdlButtonUI() {
  const btn = document.getElementById("ddl-btn");
  if (btn) {
    if (state.channelCount <= 2) {
      btn.disabled = true;
      btn.classList.remove("ddl-active");
      btn.classList.add("opacity-30", "pointer-events-none", "cursor-not-allowed");
      btn.title = "Dolby Digital Live (Unavailable for Stereo/Headphones)";
      return;
    }
    btn.disabled = false;
    btn.classList.remove("opacity-30", "pointer-events-none", "cursor-not-allowed");
    btn.title = "Toggle Dolby Digital Live";
    if (state.ddlActive) {
      btn.classList.add("ddl-active");
    } else {
      btn.classList.remove("ddl-active");
    }
  }
}

// ------------------------------------------------------------------
// 8D Spatial Audio Rotation
// ------------------------------------------------------------------
export function initEightdRotation() {
  const btn = document.getElementById("eightd-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      toggleEightdRotation();
    });
  }
}

export async function toggleEightdRotation() {
  const btn = document.getElementById("eightd-btn");
  if (state.eightd.active) {
    const shouldRestore = state.eightd.shouldRestoreDolby;
    const eightdSpinner = document.getElementById("eightd-spinner");
    const eightdText = document.getElementById("eightd-text");

    if (shouldRestore) {
      if (btn) btn.disabled = true;
      if (eightdSpinner) eightdSpinner.classList.remove("hidden");
      if (eightdText) eightdText.classList.add("hidden");
    }

    await stopEightdRotation();
    if (btn) btn.classList.remove("eightd-active");
    showToast("8D Mode Off", "Restored standard multi-channel gains.", "brand-blue");

    if (shouldRestore) {
      await toggleDdlMode(true);
      state.eightd.shouldRestoreDolby = false;

      if (eightdText) eightdText.classList.remove("hidden");
      if (eightdSpinner) eightdSpinner.classList.add("hidden");
      if (btn) btn.disabled = false;
    }
  } else {
    if (state.sweepActive) {
      stopSequentialSweep();
    }
    if (state.solo.active) {
      const res = await apiPost("/api/solo/stop");
      if (res && res.status === "success") {
        state.solo = { active: false, channel: null };
        applySoloVisuals();
      }
    }

    if (state.ddlActive) {
      const eightdSpinner = document.getElementById("eightd-spinner");
      const eightdText = document.getElementById("eightd-text");

      state.eightd.shouldRestoreDolby = true;

      if (btn) btn.disabled = true;
      if (eightdSpinner) eightdSpinner.classList.remove("hidden");
      if (eightdText) eightdText.classList.add("hidden");

      await toggleDdlMode(true);

      if (eightdText) eightdText.classList.remove("hidden");
      if (eightdSpinner) eightdSpinner.classList.add("hidden");
      if (btn) btn.disabled = false;
    } else {
      state.eightd.shouldRestoreDolby = false;
    }

    await startEightdRotation();
    if (btn) btn.classList.add("eightd-active");
    showToast("8D Spatial Audio Active", "Audio rotating across surround soundstage.", "amber");
  }
}

async function startEightdRotation() {
  state.eightd.active = true;
  document.body.classList.add("eightd-mode-active");

  await apiPost("/api/apo/toggle_8d", { enabled: true });

  ids.forEach(id => {
    state.eightd.originalVolumes[id] = state.volumes[id];
  });

  state.eightd.angle = 0;

  const speakerAngles = {
    towerL: Math.PI * 0.75,
    center: Math.PI * 0.5,
    towerR: Math.PI * 0.25,
    surroundR: Math.PI * 1.75,
    surroundL: Math.PI * 1.25
  };

  state.eightd.interval = setInterval(async () => {
    state.eightd.angle += state.eightd.speed;
    if (state.eightd.angle >= 2 * Math.PI) {
      state.eightd.angle -= 2 * Math.PI;
    }

    const nextVols = {};

    ids.forEach(id => {
      if (id === "subwoofer") {
        const origSub = state.eightd.originalVolumes["subwoofer"] ?? 100;
        nextVols[channelIndexMap[id]] = origSub;
        state.volumes[id] = origSub;
        updateFaderUI(id, origSub);
        return;
      }

      const targetAngle = speakerAngles[id];
      const alignment = Math.cos(state.eightd.angle - targetAngle);
      const intensity = Math.pow((alignment + 1) / 2, 2.5);
      const targetVol = Math.round(intensity * 100);

      nextVols[channelIndexMap[id]] = targetVol;
      state.volumes[id] = targetVol;
      updateFaderUI(id, targetVol);
    });

    await apiPost("/api/channel_volumes_multi", { volumes: nextVols });
  }, 80);
}

async function stopEightdRotation() {
  state.eightd.active = false;
  document.body.classList.remove("eightd-mode-active");
  if (state.eightd.interval) {
    clearInterval(state.eightd.interval);
    state.eightd.interval = null;
  }

  await apiPost("/api/apo/toggle_8d", { enabled: false });

  const restoreVols = {};
  ids.forEach(id => {
    const orig = state.eightd.originalVolumes[id] ?? 100;
    state.volumes[id] = orig;
    updateFaderUI(id, orig);
    restoreVols[channelIndexMap[id]] = orig;
  });

  await apiPost("/api/channel_volumes_multi", { volumes: restoreVols });
}

// ------------------------------------------------------------------
// Speaker Solo / Isolate
// ------------------------------------------------------------------
export function initSpeakerSoloHandlers() {
  ids.forEach(id => {
    const wrapper = document.getElementById(`speaker-wrapper-${id}`);
    if (wrapper) {
      wrapper.addEventListener("click", () => toggleSpeakerSolo(id));
    }
  });
}

export function applySubwooferBassManagementVisuals() {
  const wrapper = document.getElementById("speaker-wrapper-subwoofer");
  if (wrapper) {
    if (state.bassManagementActive) {
      wrapper.classList.add("speaker-solo-active");
    } else {
      wrapper.classList.remove("speaker-solo-active");
    }
  }
}

export async function toggleSpeakerSolo(id) {
  if (state.eightd.active) {
    stopEightdRotation();
    const btn = document.getElementById("eightd-btn");
    if (btn) btn.classList.remove("eightd-active");
  }

  const idx = channelIndexMap[id];

  if (state.solo.active && state.solo.channel === idx) {
    const res = await apiPost("/api/solo/stop");
    if (res && res.status === "success") {
      state.solo = { active: false, channel: null };
      lockPollFor(500);

      ids.forEach(sid => {
        if (sid === "subwoofer") return;
        animateFaderTo(sid, state.volumes[sid], 200);
      });

      if (id === "subwoofer") {
        const apoRes = await apiPost("/api/apo/toggle_bass", { enabled: false });
        if (apoRes && apoRes.status === "success") {
          state.bassManagementActive = false;
        }
      }

      applySoloVisuals();
      showToast("Isolate Off", "Restored previous channel levels.", "brand-blue");
      if (window.updateAppStatus) window.updateAppStatus();
    }
    return;
  }

  if (state.bassManagementActive && id !== "subwoofer") {
    const apoRes = await apiPost("/api/apo/toggle_bass", { enabled: false });
    if (apoRes && apoRes.status === "success") {
      state.bassManagementActive = false;
    }
  }

  const res = await apiPost("/api/solo/start", { channel: idx });
  if (res && res.status === "success") {
    state.solo = { active: true, channel: idx };
    lockPollFor(400);

    ids.forEach(sid => {
      const sidx = channelIndexMap[sid];
      if (sid === "subwoofer") return;
      const targetVol = (sidx === idx) ? 100 : 0;
      animateFaderTo(sid, targetVol, 150);
    });

    if (id === "subwoofer") {
      const apoRes = await apiPost("/api/apo/toggle_bass", { enabled: true });
      if (apoRes && apoRes.status === "success") {
        state.bassManagementActive = true;
      }
    }

    applySoloVisuals();
    if (id === "subwoofer") {
      showToast("Subwoofer Isolated", "Playing 60Hz crossover tone & enabled Equalizer APO Bass Management.", "amber");
    } else {
      showToast("Speaker Isolated", `Playing ${labelForChannel(id)} alone at 100%. Click it again to restore.`, "brand-blue");
    }
    if (window.updateAppStatus) window.updateAppStatus();
  }
}

export function labelForChannel(id) {
  const labels = {
    towerL: "Front Left", towerR: "Front Right", center: "Center",
    subwoofer: "Subwoofer", surroundL: "Surround Left", surroundR: "Surround Right"
  };
  return labels[id] || id;
}

export function applySoloVisuals() {
  ids.forEach(id => {
    const idx = channelIndexMap[id];
    const wrapper = document.getElementById(`speaker-wrapper-${id}`);
    if (!wrapper) return;

    if (state.solo.active && state.solo.channel === idx) {
      wrapper.classList.add("speaker-solo-active");
      wrapper.classList.remove("speaker-solo-dimmed");
    } else if (state.solo.active) {
      wrapper.classList.remove("speaker-solo-active");
      wrapper.classList.add("speaker-solo-dimmed");
    } else {
      wrapper.classList.remove("speaker-solo-dimmed");
      if (id === "subwoofer") {
        if (state.bassManagementActive) {
          wrapper.classList.add("speaker-solo-active");
        } else {
          wrapper.classList.remove("speaker-solo-active");
        }
      } else {
        wrapper.classList.remove("speaker-solo-active");
      }
    }
  });
}

// ------------------------------------------------------------------
// Speaker Channel Muting Control
// ------------------------------------------------------------------
export function initSpeakerChannelMuting() {
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

export function toggleSpeakerMute(id) {
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
// Locked subwoofer slider
// ------------------------------------------------------------------
export function initSubwooferLockOverlay() {
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
// Reset Balance
// ------------------------------------------------------------------
export async function resetBalance() {
  showToast("Reset Balance", "Resetting all speaker channels to 100% gain...", "brand-blue");
  saveUserPreset();

  lockPollFor(500);
  ids.forEach(id => {
    if (id !== "subwoofer") animateFaderTo(id, 100, 250);
  });
  animateMasterTo(state.volumes['master'], 250);

  const res = await apiPost("/api/reset_balance");
  if (res && res.status === "success") {
    if (window.updateAppStatus) window.updateAppStatus();
  }
}

// ------------------------------------------------------------------
// Sequential sound sweeps
// ------------------------------------------------------------------
export async function runSequentialSweep() {
  if (state.eightd.active) {
    stopEightdRotation();
    const btn = document.getElementById("eightd-btn");
    if (btn) btn.classList.remove("eightd-active");
  }

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
  state.sweepInterval = setInterval(playNextTone, 1400);
}

export function stopSequentialSweep() {
  const testIcon = document.getElementById('testIcon');
  if (state.sweepActive) {
    clearInterval(state.sweepInterval);
    state.sweepActive = false;
    if (testIcon) testIcon.className = "fa-solid fa-volume-high text-xs";
    clearSweepHighlights();
  }
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

// ------------------------------------------------------------------
// Acoustic Presets
// ------------------------------------------------------------------
export function highlightPreset(profileName) {
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

export function initAcousticPresets() {
  const buttons = document.querySelectorAll(".preset-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", async () => {
      if (state.eightd.active) {
        stopEightdRotation();
        const btn8d = document.getElementById("eightd-btn");
        if (btn8d) btn8d.classList.remove("eightd-active");
      }

      const preset = btn.dataset.preset;
      showToast("Applying Preset", `Loading acoustic parameters for ${preset}...`, "brand-blue");

      const res = await apiPost("/api/profile/apply", { profile: preset });
      if (res && res.status === "success") {
        state.settings.active_profile = preset;
        highlightPreset(preset);

        if (res.master !== undefined && res.master !== null) {
          state.volumes["master"] = res.master;
          updateMasterUI(res.master);
          const masterSlider = document.getElementById("slider-master");
          if (masterSlider) masterSlider.value = res.master;
        }

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

export function fadeChannelVolume(channelId, targetVol) {
  if (fadeIntervals[channelId]) clearInterval(fadeIntervals[channelId]);

  const startVol = state.volumes[channelId];
  if (startVol === targetVol) return;

  const duration = 500;
  const intervalTime = 16;
  const totalSteps = Math.round(duration / intervalTime);
  let currentStep = 0;

  fadeIntervals[channelId] = setInterval(() => {
    currentStep++;
    const progress = currentStep / totalSteps;
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    const currentVal = Math.round(startVol + (targetVol - startVol) * easeProgress);

    state.volumes[channelId] = currentVal;
    updateFaderUI(channelId, currentVal);

    const slider = document.getElementById("slider-" + channelId);
    if (slider) slider.value = currentVal;

    if (currentStep % 6 === 0 || currentStep === totalSteps) {
      const idx = channelIndexMap[channelId];
      sendChannelVolume(idx, currentVal);
    }

    if (currentStep >= totalSteps) {
      clearInterval(fadeIntervals[channelId]);
    }
  }, intervalTime);
}

export function initFilterPresets() {
  const buttons = document.querySelectorAll(".preset-filter-btn");
  buttons.forEach(btn => {
    btn.addEventListener("click", async () => {
      const preset = btn.dataset.preset;
      const isActive = btn.classList.contains("preset-filter-active");
      const presetName = btn.dataset.name || preset;
      
      // Disable the button during request to prevent spamming
      btn.disabled = true;
      const spinner = btn.querySelector(".preset-spinner");
      const icon = btn.querySelector(".preset-icon");
      if (spinner) spinner.classList.remove("hidden");
      if (icon) icon.classList.add("hidden");
      
      const res = await apiPost("/api/apo/toggle_preset", {
        preset: preset,
        enabled: !isActive
      });
      
      if (spinner) spinner.classList.add("hidden");
      if (icon) icon.classList.remove("hidden");
      btn.disabled = false;
      
      if (res && res.status === "success") {
        state.settings.active_preset = res.active_preset;
        updatePresetButtonsUI();
        
        // If the preset turned ON:
        if (res.active_preset === preset) {
          showToast(`${presetName} Preset Active`, "APO filters applied. Other surround processing bypassed.", "amber");
          
          // Sync state values based on what was automatically disabled
          if (res.ddl_disabled) {
            state.ddlActive = false;
            updateDdlButtonUI();
          }
          if (res.eightd_disabled) {
            stopEightdRotation();
            const btn8d = document.getElementById("eightd-btn");
            if (btn8d) btn8d.classList.remove("eightd-active");
          }
          if (res.calibration_disabled) {
            state.settings.calibration_enabled = false;
            import('./calibration.js').then(m => m.applyCalibrationUI());
          }
        } else {
          showToast(`${presetName} Preset Off`, "APO filters bypassed. Restored previous audio setup.", "brand-blue");
          
          // Sync state values based on what was automatically restored
          if (res.ddl_restored) {
            state.ddlActive = true;
            updateDdlButtonUI();
          }
          if (res.eightd_restored) {
            startEightdRotation();
            const btn8d = document.getElementById("eightd-btn");
            if (btn8d) btn8d.classList.add("eightd-active");
          }
          if (res.calibration_restored) {
            state.settings.calibration_enabled = true;
            import('./calibration.js').then(m => m.applyCalibrationUI());
          }
        }
        
        if (window.updateAppStatus) window.updateAppStatus();
      } else {
        showToast("Preset Error", res ? res.message : "Failed to toggle preset.", "red");
      }
    });
  });
}

export function updatePresetButtonsUI() {
  const activePreset = state.settings.active_preset;
  const buttons = document.querySelectorAll(".preset-filter-btn");
  buttons.forEach(btn => {
    const preset = btn.dataset.preset;
    if (activePreset === preset) {
      btn.classList.add("preset-filter-active");
      btn.classList.remove("text-zinc-400", "bg-zinc-950", "border-zinc-850");
      btn.classList.add("text-amber-500", "bg-amber-500/10", "border-amber-500/50");
    } else {
      btn.classList.remove("preset-filter-active", "text-amber-500", "bg-amber-500/10", "border-amber-500/50");
      btn.classList.add("text-zinc-400", "bg-zinc-950", "border-zinc-850");
    }
  });
}
