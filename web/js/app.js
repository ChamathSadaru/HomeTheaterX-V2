// Main Coordinator / Bootstrap Module
import { apiGet, apiPost, showToast } from './api.js';
import { state, ids, channelIndexMap, setUserDragging, lockPollFor } from './state.js';
import { initOscilloscope, visualizerState } from './visualizer.js';
import { initRoomCalibrations, applyCalibrationUI } from './calibration.js';
import { initWebSocket, sendWsMessage, isWsConnected } from './ws.js';
import {
  initDdlToggle,
  initEightdRotation,
  initSpeakerSoloHandlers,
  initSpeakerChannelMuting,
  initSubwooferLockOverlay,
  initAcousticPresets,
  updateAllFadersUI,
  updateFaderUI,
  updateMasterUI,
  sendChannelVolume,
  sendMasterVolume,
  saveUserPreset,
  resetBalance,
  runSequentialSweep,
  highlightPreset,
  applySoloVisuals,
  applySubwooferBassManagementVisuals,
  updateDdlButtonUI,
  initFilterPresets,
  updatePresetButtonsUI
} from './audio_effects.js';

// Expose updateAppStatus globally so helper files can query it
window.updateAppStatus = updateAppStatus;

// Receiver Console state and tracks
export const avrTracks = [
  { title: "Quantum Solace (Overture)", artist: "David Arnold", bpm: 110, duration: "3:42" },
  { title: "GoldenEye (Theme)", artist: "Tina Turner", bpm: 92, duration: "4:46" },
  { title: "Skyfall", artist: "Adele", bpm: 76, duration: "4:48" },
  { title: "No Time To Die", artist: "Billie Eilish", bpm: 74, duration: "4:02" },
  { title: "Another Way To Die", artist: "Jack White & Alicia Keys", bpm: 138, duration: "4:23" },
  { title: "Writing's On The Wall", artist: "Sam Smith", bpm: 66, duration: "4:38" },
  { title: "The Writing's On The Wall", artist: "OK Go", bpm: 104, duration: "3:18" }
];

export const avrState = {
  power: true,
  source: 'OPTICAL', // 'BLU-RAY', 'BLUETOOTH', 'FM-RADIO', 'OPTICAL'
  equalizer: 'FLAT', // 'FLAT', 'CINEMA', 'MUSIC', 'BASS-PRO'
  discTrayOpen: false,
  isPlaying: false,
  currentTrackIndex: 0,
  trackPosition: 0,
  playInterval: null
};

// Expose avrState on window so visualizer.js can query it
window.avrState = avrState;

function trackDurationToSeconds(duration) {
  const parts = duration.split(':');
  return parseInt(parts[0]) * 60 + parseInt(parts[1]);
}

function formatSeconds(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function updateAVRConsoleUI() {
  const powerBtn = document.getElementById("avr-power-btn");
  const powerStatus = document.getElementById("avr-power-status");
  const screen = document.getElementById("avr-screen");
  const screenOn = document.getElementById("avr-screen-on");
  const screenOff = document.getElementById("avr-screen-off");
  const bottomPanel = document.getElementById("avr-bottom-panel");
  const volumeText = document.getElementById("avr-volume-text");
  const dialIndicator = document.getElementById("avr-dial-indicator");
  const volumeDial = document.getElementById("avr-volume-dial");

  if (!powerBtn) return;

  if (avrState.power) {
    powerBtn.className = "group w-14 h-14 rounded-full flex items-center justify-center border-2 border-amber-500/80 text-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.35)] scale-102 bg-zinc-950 transition-all duration-300 cursor-pointer active:scale-95";
    powerStatus.innerText = "POWER ACTIVE";
    powerStatus.className = "text-[10px] font-bold mt-1 text-amber-500 uppercase tracking-widest";

    screen.className = "w-full min-h-[105px] bg-black rounded-2xl border border-amber-500/20 p-4 flex flex-col justify-between shadow-inner relative transition-all duration-500 shadow-[inset_0_0_15px_rgba(245,158,11,0.03)]";
    screenOn.classList.remove("hidden");
    screenOff.classList.add("hidden");
    bottomPanel.classList.remove("hidden");
    bottomPanel.style.display = "flex";

    const masterVol = state.volumes["master"];
    volumeText.innerText = state.isSystemMuted ? "MUTE" : masterVol + "%";
    volumeText.className = "text-xl font-mono font-extrabold tracking-wider mt-1 text-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.2)]";
    dialIndicator.className = "absolute top-1 w-1 h-2 rounded-full bg-amber-500 shadow-[0_0_5px_#f59e0b] transition-colors duration-300";

    const rotation = (masterVol / 100) * 270 - 135;
    volumeDial.style.transform = `rotate(${rotation}deg)`;
    volumeDial.className = "w-16 h-16 rounded-full bg-gradient-to-tr from-zinc-950 via-zinc-900 to-zinc-800 border-2 border-zinc-700 shadow-xl flex items-center justify-center relative cursor-pointer select-none transition-all duration-300 hover:border-amber-500/50";

    const dispSource = document.getElementById("avr-disp-source");
    if (dispSource) dispSource.innerText = avrState.source;

    const dispSurround = document.getElementById("avr-disp-surround");
    const dispBoost = document.getElementById("avr-disp-boost");

    if (dispSurround) {
      if (avrState.source === "BLU-RAY" || avrState.source === "OPTICAL") {
        dispSurround.className = "text-amber-500";
      } else {
        dispSurround.className = "text-zinc-700";
      }
    }
    if (dispBoost) {
      if (avrState.equalizer === "BASS-PRO") {
        dispBoost.className = "text-amber-500";
      } else {
        dispBoost.className = "text-zinc-700";
      }
    }

    const dispTitle = document.getElementById("avr-disp-title");
    const dispArtist = document.getElementById("avr-disp-artist");
    const dispProgress = document.getElementById("avr-disp-progress");
    const dispCurrentTime = document.getElementById("avr-disp-current-time");
    const dispDuration = document.getElementById("avr-disp-duration");

    const progressContainer = document.getElementById("avr-progress-container");
    const avrCanvas = document.getElementById("avr-vis-canvas");
    if (avrState.source === "OPTICAL") {
      if (progressContainer) progressContainer.classList.add("hidden");
      if (avrCanvas) avrCanvas.classList.remove("hidden");
    } else {
      if (progressContainer) progressContainer.classList.remove("hidden");
      if (avrCanvas) avrCanvas.classList.add("hidden");
    }

    if (avrState.source === "BLU-RAY") {
      const track = avrTracks[avrState.currentTrackIndex];
      dispTitle.innerText = avrState.isPlaying ? track.title.toUpperCase() : "BLU-RAY READY";
      dispArtist.innerText = avrState.isPlaying ? `${track.artist} | ${track.bpm} BPM` : "INSERT BLU-RAY DISC";

      const trackSecs = trackDurationToSeconds(track.duration);
      const pct = (avrState.trackPosition / trackSecs) * 100;
      dispProgress.style.width = pct + "%";
      dispCurrentTime.innerText = formatSeconds(avrState.trackPosition);
      dispDuration.innerText = track.duration;
    } else if (avrState.source === "BLUETOOTH") {
      const winTitle = document.getElementById("player-title") ? document.getElementById("player-title").innerText : "NO ACTIVE MEDIA";
      const winArtist = document.getElementById("player-artist") ? document.getElementById("player-artist").innerText : "PAIR BLUETOOTH SOURCE";

      dispTitle.innerText = winTitle.toUpperCase();
      dispArtist.innerText = winArtist.toUpperCase();

      const winProgress = document.getElementById("player-progress");
      dispProgress.style.width = winProgress ? winProgress.style.width : "0%";

      const winCurrentTime = document.getElementById("player-current-time");
      const winDuration = document.getElementById("player-duration");
      dispCurrentTime.innerText = winCurrentTime ? winCurrentTime.innerText : "0:00";
      dispDuration.innerText = winDuration ? winDuration.innerText : "0:00";
    } else if (avrState.source === "FM-RADIO") {
      dispTitle.innerText = "FM 102.5 MHz";
      dispArtist.innerText = "SAMSUNG RDS FM TUNER";
      dispProgress.style.width = "40%";
      dispCurrentTime.innerText = "STEREO";
      dispDuration.innerText = "SIGNAL MAX";
    } else if (avrState.source === "OPTICAL") {
      const winTitle = document.getElementById("player-title") ? document.getElementById("player-title").innerText : "";
      const winArtist = document.getElementById("player-artist") ? document.getElementById("player-artist").innerText : "";
      const hasActiveMedia = winTitle && winTitle !== "No Active Media";

      if (hasActiveMedia) {
        dispTitle.innerText = winTitle.toUpperCase();
        dispArtist.innerText = winArtist.toUpperCase();
      } else {
        dispTitle.innerText = "PCM DIGITAL INPUT";
        dispArtist.innerText = "WAITING FOR OPTICAL LOCK...";
      }

      dispCurrentTime.innerText = "96 KHZ";
      dispDuration.innerText = "24 BIT";
    }

    const trayPanel = document.getElementById("avr-tray-panel");
    if (avrState.source === "BLU-RAY") {
      trayPanel.classList.remove("hidden");
      trayPanel.style.display = "flex";

      const ejectBtn = document.getElementById("avr-btn-eject");
      const txtTray = document.getElementById("avr-txt-tray");
      const lblEject = document.getElementById("avr-lbl-eject");

      if (avrState.discTrayOpen) {
        ejectBtn.className = "p-2 rounded-lg border border-yellow-500/40 bg-yellow-500/10 text-yellow-400 shadow-[0_0_8px_rgba(234,179,8,0.1)] flex items-center gap-2 text-[10px] font-mono font-bold uppercase transition-all cursor-pointer";
        txtTray.innerText = "💿 Tray Ejected. Drop a sound disc in!";
        lblEject.innerText = "Close Disc Tray";
      } else {
        ejectBtn.className = "p-2 rounded-lg border border-zinc-800 bg-zinc-900 text-zinc-300 hover:text-white flex items-center gap-2 text-[10px] font-mono font-bold uppercase transition-all cursor-pointer";
        txtTray.innerText = "💿 Blu-Ray Disc nested inside slot drive.";
        lblEject.innerText = "Eject / Insert Disc";
      }

      const playIcon = document.getElementById("avr-icon-play");
      const playBtn = document.getElementById("avr-btn-play");
      if (avrState.isPlaying) {
        playIcon.className = "fa-solid fa-square text-[10px]";
        playBtn.className = "p-2 rounded-full border border-amber-500/40 bg-amber-500/10 text-amber-500 flex items-center justify-center cursor-pointer";
      } else {
        playIcon.className = "fa-solid fa-play text-[10px]";
        playBtn.className = "p-2 rounded-full border border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-white flex items-center justify-center cursor-pointer";
      }

      const trackIdxLbl = document.getElementById("avr-lbl-track-idx");
      if (trackIdxLbl) trackIdxLbl.innerText = avrState.currentTrackIndex + 1;
    } else {
      trayPanel.classList.add("hidden");
      trayPanel.style.display = "none";
    }

    const sourcesMap = {
      'BLU-RAY': 'avr-src-bluray',
      'BLUETOOTH': 'avr-src-bluetooth',
      'FM-RADIO': 'avr-src-fm',
      'OPTICAL': 'avr-src-optical'
    };

    Object.keys(sourcesMap).forEach(srcKey => {
      const btn = document.getElementById(sourcesMap[srcKey]);
      if (btn) {
        if (avrState.source === srcKey) {
          btn.className = "avr-src-btn px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold tracking-wider flex items-center gap-1.5 border border-amber-500/50 bg-amber-500/10 text-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.15)] transition-all cursor-pointer";
        } else {
          btn.className = "avr-src-btn px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold tracking-wider flex items-center gap-1.5 border border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200 transition-all cursor-pointer";
        }
      }
    });

    const eqMap = {
      'FLAT': 'avr-eq-flat',
      'CINEMA': 'avr-eq-cinema',
      'MUSIC': 'avr-eq-music',
      'BASS-PRO': 'avr-eq-basspro'
    };

    Object.keys(eqMap).forEach(eqKey => {
      const btn = document.getElementById(eqMap[eqKey]);
      if (btn) {
        if (avrState.equalizer === eqKey) {
          btn.className = "avr-eq-btn px-2.5 py-1 rounded-md text-[9px] font-mono font-bold tracking-wider border border-white/20 bg-white/10 text-white shadow-md transition-all cursor-pointer";
        } else {
          btn.className = "avr-eq-btn px-2.5 py-1 rounded-md text-[9px] font-mono font-bold tracking-wider border border-zinc-800/80 bg-zinc-900/50 text-zinc-500 hover:text-zinc-300 transition-all cursor-pointer";
        }
      }
    });

  } else {
    powerBtn.className = "group w-14 h-14 rounded-full flex items-center justify-center border-2 border-zinc-700 text-zinc-500 hover:text-zinc-400 bg-gradient-to-b from-zinc-800 to-zinc-900 transition-all duration-300 cursor-pointer active:scale-95";
    powerStatus.innerText = "STANDBY MODE";
    powerStatus.className = "text-[10px] font-bold mt-1 text-zinc-600 uppercase tracking-widest";

    screen.className = "w-full min-h-[105px] bg-black rounded-2xl border border-zinc-850 p-4 flex flex-col justify-between shadow-inner relative transition-all duration-500";
    screenOn.classList.add("hidden");
    screenOff.classList.remove("hidden");
    bottomPanel.classList.add("hidden");
    bottomPanel.style.display = "none";

    volumeText.innerText = "OFF";
    volumeText.className = "text-xl font-extrabold tracking-wider mt-1 text-zinc-600";
    dialIndicator.className = "absolute top-1 w-1 h-2 rounded-full bg-zinc-700 transition-colors duration-300";

    volumeDial.style.transform = "rotate(-135deg)";
    volumeDial.className = "w-16 h-16 rounded-full bg-gradient-to-tr from-zinc-950 via-zinc-900 to-zinc-800 border-2 border-zinc-800 shadow-xl flex items-center justify-center relative cursor-pointer select-none transition-all duration-300";

    const progressContainer = document.getElementById("avr-progress-container");
    const avrCanvas = document.getElementById("avr-vis-canvas");
    if (progressContainer) progressContainer.classList.remove("hidden");
    if (avrCanvas) avrCanvas.classList.add("hidden");
  }
}

// Expose updateAVRConsoleUI globally so fader updates can invoke it
window.updateAVRConsoleUI = updateAVRConsoleUI;

function handleVolumeScroll(delta) {
  if (!avrState.power) return;
  const currentVol = state.volumes["master"];
  const newVol = Math.max(0, Math.min(100, currentVol + delta));

  state.volumes["master"] = newVol;
  updateMasterUI(newVol);
  sendMasterVolume(newVol);
  saveUserPreset();

  const rotation = (newVol / 100) * 270 - 135;
  const dial = document.getElementById("avr-volume-dial");
  if (dial) dial.style.transform = `rotate(${rotation}deg)`;

  const volumeText = document.getElementById("avr-volume-text");
  if (volumeText) volumeText.innerText = state.isSystemMuted ? "MUTE" : newVol + "%";
}

async function applyAVREQ(eq) {
  if (!avrState.power) return;
  avrState.equalizer = eq;
  updateAVRConsoleUI();

  const eqProfileMap = {
    'FLAT': 'Night',
    'CINEMA': 'Movie',
    'MUSIC': 'Music',
    'BASS-PRO': 'Game'
  };
  const targetProfile = eqProfileMap[eq];
  showToast("AVR Equalizer Sync", `Applying ${eq} sound profile configurations...`, "brand-blue");

  const res = await apiPost("/api/profile/apply", { profile: targetProfile });
  if (res && res.status === "success") {
    state.settings.active_profile = targetProfile;
    highlightPreset(targetProfile);
    lockPollFor(500);

    if (res.master !== undefined && res.master !== null) {
      animateMasterTo(res.master, 220);
    }

    ids.forEach(id => {
      const idx = channelIndexMap[id];
      if (res.channels && res.channels[idx] !== undefined) {
        const targetVal = res.channels[idx];
        animateFaderTo(id, targetVal, 220);
      }
    });
  }
}

function initReceiverConsole() {
  const powerBtn = document.getElementById("avr-power-btn");
  if (!powerBtn) return;

  powerBtn.addEventListener("click", () => {
    avrState.power = !avrState.power;
    if (!avrState.power) {
      avrState.isPlaying = false;
      if (avrState.playInterval) clearInterval(avrState.playInterval);
      avrState.playInterval = null;
    }
    updateAVRConsoleUI();
    showToast(avrState.power ? "AVR Console Active" : "AVR Console Standby", avrState.power ? "Receiver physical control plate booted." : "Receiver placed in low-power standby mode.", avrState.power ? "brand-blue" : "brand-amber");
  });

  const sourcesMap = {
    'avr-src-bluray': 'BLU-RAY',
    'avr-src-bluetooth': 'BLUETOOTH',
    'avr-src-fm': 'FM-RADIO',
    'avr-src-optical': 'OPTICAL'
  };

  Object.keys(sourcesMap).forEach(btnId => {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.addEventListener("click", () => {
        if (!avrState.power) return;
        const src = sourcesMap[btnId];
        avrState.source = src;
        avrState.trackPosition = 0;

        if (src !== 'BLU-RAY') {
          avrState.isPlaying = false;
          if (avrState.playInterval) clearInterval(avrState.playInterval);
          avrState.playInterval = null;
        }
        updateAVRConsoleUI();
        showToast("AVR Source Selected", `Receiver input source set to ${src}`, "brand-blue");
      });
    }
  });

  const eqMap = {
    'avr-eq-flat': 'FLAT',
    'avr-eq-cinema': 'CINEMA',
    'avr-eq-music': 'MUSIC',
    'avr-eq-basspro': 'BASS-PRO'
  };

  Object.keys(eqMap).forEach(btnId => {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.addEventListener("click", () => applyAVREQ(eqMap[btnId]));
    }
  });

  const ejectBtn = document.getElementById("avr-btn-eject");
  if (ejectBtn) {
    ejectBtn.addEventListener("click", () => {
      if (!avrState.power || avrState.source !== "BLU-RAY" || avrState.discTrayOpen) return;
      avrState.discTrayOpen = !avrState.discTrayOpen;
      if (avrState.discTrayOpen) {
        avrState.isPlaying = false;
        if (avrState.playInterval) clearInterval(avrState.playInterval);
        avrState.playInterval = null;
      }
      updateAVRConsoleUI();
      showToast(avrState.discTrayOpen ? "Disc Ejected" : "Disc Loaded", avrState.discTrayOpen ? "Tray open. Sound disc removed." : "Disc inserted. Initializing audio stream...", "brand-blue");
    });
  }

  const playBtn = document.getElementById("avr-btn-play");
  if (playBtn) {
    playBtn.addEventListener("click", () => {
      if (!avrState.power || avrState.source !== "BLU-RAY" || avrState.discTrayOpen) return;
      avrState.isPlaying = !avrState.isPlaying;

      if (avrState.isPlaying) {
        avrState.playInterval = setInterval(() => {
          const track = avrTracks[avrState.currentTrackIndex];
          const maxSecs = trackDurationToSeconds(track.duration);

          avrState.trackPosition++;
          if (avrState.trackPosition >= maxSecs) {
            avrState.trackPosition = 0;
            avrState.currentTrackIndex = (avrState.currentTrackIndex + 1) % avrTracks.length;
          }
          updateAVRConsoleUI();
        }, 1000);
      } else {
        if (avrState.playInterval) clearInterval(avrState.playInterval);
        avrState.playInterval = null;
      }
      updateAVRConsoleUI();
    });
  }

  const nextBtn = document.getElementById("avr-btn-next");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (!avrState.power || avrState.source !== "BLU-RAY" || avrState.discTrayOpen) return;
      avrState.trackPosition = 0;
      avrState.currentTrackIndex = (avrState.currentTrackIndex + 1) % avrTracks.length;
      updateAVRConsoleUI();
    });
  }

  const volumeDial = document.getElementById("avr-volume-dial");
  if (volumeDial) {
    volumeDial.addEventListener("click", () => handleVolumeScroll(5));
    volumeDial.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      handleVolumeScroll(-5);
    });
  }

  updateAVRConsoleUI();
}

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

async function onDeviceSelected() {
  const selector = document.getElementById("deviceSelector");
  const res = await apiPost("/api/select_device", { device: selector.value });
  if (res && res.status === "success") {
    showToast("Output Updated", `Active output device set to ${selector.value}`, "brand-blue");
    updateAppStatus();
  }
}

export function applyVolumeStatus(data) {
  if (!data) return;
  if (state.isUserDragging || state.sweepActive) return;
  if (Date.now() < state.pollLockUntil) return;

  if (typeof data.master === "number") {
    state.volumes["master"] = data.master;
    const masterSlider = document.getElementById("slider-master");
    if (masterSlider) masterSlider.value = data.master;
  }

  if (typeof data.muted === "boolean") {
    state.isSystemMuted = data.muted;
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
  }

  if (data.channels) {
    ids.forEach(id => {
      const idx = channelIndexMap[id];
      if (data.channels[idx] !== undefined) {
        const val = data.channels[idx];
        state.volumes[id] = val;
        const slider = document.getElementById(`slider-${id}`);
        if (slider) slider.value = val;

        const muteIcon = document.getElementById("mute-icon-" + id);
        if (muteIcon) {
          if (val === 0) {
            muteIcon.className = "fa-solid fa-volume-xmark text-[8px] text-red-500";
          } else {
            muteIcon.className = "fa-solid fa-volume-high text-[8px] text-zinc-650";
          }
        }
      }
    });
  }

  updateAllFadersUI();
}

async function pollVolumeChanges() {
  if (isWsConnected()) return;
  if (state.isUserDragging || state.sweepActive) return;
  if (Date.now() < state.pollLockUntil) return;
  updateAppStatus();
}

async function updateAppStatus() {
  const data = await apiGet("/api/status");
  if (!data || data.status !== "success") return;

  state.channelCount = data.channel_count;
  state.isSystemMuted = data.muted;
  state.currentDeviceName = data.active_device;

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

  if (!state.isUserDragging && Date.now() >= state.pollLockUntil) {
    state.volumes["master"] = data.master_volume;
    const masterSlider = document.getElementById("slider-master");
    if (masterSlider) masterSlider.value = data.master_volume;
  }

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

    if (slider && !state.isUserDragging && Date.now() >= state.pollLockUntil) {
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

  if (data.solo) {
    const changed = data.solo.active !== state.solo.active || data.solo.channel !== state.solo.channel;
    state.solo = { active: !!data.solo.active, channel: data.solo.channel };
    if (changed) applySoloVisuals();
  }

  if (data.bass_management !== undefined) {
    const changed = data.bass_management !== state.bassManagementActive;
    state.bassManagementActive = data.bass_management;
    if (changed) applySubwooferBassManagementVisuals();
  }

  if (data.ddl_active !== undefined) {
    state.ddlActive = data.ddl_active;
    updateDdlButtonUI();
  }

  if (data.active_preset !== undefined) {
    state.settings.active_preset = data.active_preset;
    updatePresetButtonsUI();
  }
}

// ------------------------------------------------------------------
// Mini Media Player
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
  setInterval(pollWindowsMedia, 800);
}

function togglePlay() {
  if (windowsMediaActive) {
    if (!sendWsMessage({ type: "media_control", action: "play_pause" })) {
      apiPost("/api/media/control", { action: "play_pause" });
    }
  }
}

function playPrev() {
  if (windowsMediaActive) {
    if (!sendWsMessage({ type: "media_control", action: "previous" })) {
      apiPost("/api/media/control", { action: "previous" });
    }
  }
}

function playNext() {
  if (windowsMediaActive) {
    if (!sendWsMessage({ type: "media_control", action: "next" })) {
      apiPost("/api/media/control", { action: "next" });
    }
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

export function applyMediaStatus(data) {
  if (!data) return;

  if (data.status === "success") {
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

    const isPlaying = data.playback_status === 4;
    window.mediaPlayerIsPlaying = isPlaying;

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

    if (avrState.power && (avrState.source === "BLUETOOTH" || avrState.source === "OPTICAL")) {
      updateAVRConsoleUI();
    }

  } else {
    if (windowsMediaActive) {
      resetPlayerUI();
    }
  }
}

async function pollWindowsMedia() {
  // If WebSocket is actively connected, skip redundant HTTP requests
  if (isWsConnected()) return;

  try {
    const data = await apiGet("/api/media/status");
    applyMediaStatus(data);
  } catch (err) {
    console.error("Error polling Windows media status:", err);
  }
}

// ------------------------------------------------------------------
// Speakers Cone Vibrating & Neon Glow Animations Loop
// ------------------------------------------------------------------
let pulseAngle = 0;
let peakHistory = [];
const historyLen = 12;
let currentBassGlow = 0.0;
let prevPeak = 0.0;

function animateSpeakerPulses() {
  if (!state.isSystemMuted) {
    pulseAngle += 0.10;

    const localPeak = (window.mediaPlayerIsPlaying) ? (0.12 + Math.sin(Date.now() / 100) * 0.05) : 0.0;
    const peak = Math.max(state.windowsAudioPeak, localPeak);
    const pulse = peak > 0.015 ? peak : Math.sin(pulseAngle) * 0.15;

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

    if (bassIntensity > currentBassGlow) {
      currentBassGlow = bassIntensity;
    } else {
      currentBassGlow = currentBassGlow * 0.83;
    }

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
          pulseValue = currentBassGlow;
        } else if (id === "surroundL" || id === "surroundR") {
          multiplier = 0.03;
        }

        const scale = 1 + (pulseValue * vol * multiplier);
        speaker.style.transform = "scale(" + scale + ")";
      }

      const cone = document.getElementById('cone-' + id);
      if (cone) {
        const driverVib = (id === "subwoofer") ? currentBassGlow : (peak > 0.015 ? peak : 0.0);
        const vibration = 1.0 + (vol * 0.07 * driverVib * (Math.random() * 0.4 + 0.6));
        cone.style.transform = `scale(${vibration})`;
      }

      const glowLight = document.getElementById('glow-light-' + id);
      if (glowLight) {
        if (vol === 0) {
          glowLight.style.opacity = '0';
          glowLight.style.transform = 'scale(0.8)';
        } else {
          const pulseValue = (id === "subwoofer") ? currentBassGlow : Math.abs(pulse);
          const glowOpacity = vol * 0.45 * (0.85 + pulseValue * 0.15);
          const glowScale = 0.8 + vol * 0.4 + (pulseValue * 0.06);
          glowLight.style.opacity = glowOpacity;
          glowLight.style.transform = `scale(${glowScale})`;
        }
      }
    });
  } else {
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
    });
  }
  requestAnimationFrame(animateSpeakerPulses);
}

// Speaker click-and-hold glow handlers
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

    applyCalibrationUI();
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

function initWindowsAudioSync() {
  // Initialize real-time WebSocket connection
  initWebSocket({
    onMediaUpdate: (mediaData) => {
      applyMediaStatus(mediaData);
    },
    onVolumeUpdate: (volData) => {
      applyVolumeStatus(volData);
    },
    onFullStatus: (fullData) => {
      if (fullData.media) {
        applyMediaStatus(fullData.media);
      }
      applyVolumeStatus({
        master: fullData.master,
        muted: fullData.muted,
        channels: fullData.channels
      });
    }
  });

  // Fallback SSE listener only if WebSockets are unsupported
  if (!window.WebSocket) {
    try {
      const eventSource = new EventSource("/api/audio_stream");
      eventSource.onmessage = function (event) {
        try {
          const data = JSON.parse(event.data);
          if (data && typeof data.peak === "number") {
            state.windowsAudioPeak = state.windowsAudioPeak * 0.25 + data.peak * 0.75;
          }
        } catch (e) {}
      };
      eventSource.onerror = function () {
        eventSource.close();
        setTimeout(initWindowsAudioSync, 3000);
      };
    } catch (sseErr) {}
  }
}

// DOMContentLoaded Bootstrap
document.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl = urlParams.get("token");
  if (tokenFromUrl) {
    localStorage.setItem("access_token", tokenFromUrl);
  }

  const isWidget = urlParams.get("view") === "widget";
  if (isWidget) {
    document.documentElement.classList.add("widget-mode");
    document.body.classList.add("widget-mode");
    setTimeout(() => {
      const tabReceiver = document.getElementById("tab-receiver");
      if (tabReceiver) tabReceiver.click();
    }, 100);
  }

  if (tokenFromUrl) {
    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname + (isWidget ? "?view=widget" : "");
    window.history.replaceState({ path: cleanUrl }, "", cleanUrl);
  }

  document.body.style.opacity = "1";

  initOscilloscope();
  animateSpeakerPulses();
  refreshDevices();
  updateAppStatus();
  setInterval(pollVolumeChanges, 600);

  document.getElementById("deviceSelector").addEventListener("change", onDeviceSelected);
  document.getElementById("btnRefresh").addEventListener("click", refreshDevices);

  const testBtn = document.getElementById("test-btn");
  if (testBtn) {
    testBtn.addEventListener("click", runSequentialSweep);
  }

  const btnVisMode = document.getElementById("btn-vis-mode");
  const lblVisMode = document.getElementById("lbl-vis-mode");
  if (btnVisMode) {
    btnVisMode.addEventListener("click", () => {
      if (visualizerState.mode === "waveform") {
        visualizerState.mode = "bars";
        if (lblVisMode) lblVisMode.innerText = "Spectrum";
      } else if (visualizerState.mode === "bars") {
        visualizerState.mode = "pixel";
        if (lblVisMode) lblVisMode.innerText = "Retro Dots";
      } else {
        visualizerState.mode = "waveform";
        if (lblVisMode) lblVisMode.innerText = "Waveform";
      }
    });
  }

  const formatSelector = document.getElementById("formatSelector");
  if (formatSelector) {
    formatSelector.addEventListener("change", () => {
      const selectedOption = formatSelector.options[formatSelector.selectedIndex].text;
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

  const muteBtn = document.getElementById("mute-btn");
  if (muteBtn) {
    muteBtn.addEventListener("click", toggleSystemMute);
  }

  const resetBtn = document.getElementById("reset-btn");
  if (resetBtn) {
    resetBtn.addEventListener("click", resetBalance);
  }

  const btnSweep = document.getElementById("btnSweep");
  if (btnSweep) {
    btnSweep.addEventListener("click", runSequentialSweep);
  }

  initSpeakerChannelMuting();

  const minBtn = document.getElementById("win-min-btn");
  if (minBtn) {
    minBtn.addEventListener("click", () => {
      document.body.style.opacity = "0";
      setTimeout(async () => {
        await apiPost("/api/window/minimize");
        document.body.style.opacity = "1";
      }, 250);
    });
  }

  const closeBtn = document.getElementById("win-close-btn");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      document.body.style.opacity = "0";
      setTimeout(async () => {
        await apiPost("/api/window/close");
        document.body.style.opacity = "1";
      }, 250);
    });
  }

  initTabsNavigation();
  initRoomCalibrations();
  initReceiverConsole();
  initSettingsView();
  initSpeakerSoloHandlers();
  initSpeakerGlowHandlers();
  initEightdRotation();
  initDdlToggle();
  initSubwooferLockOverlay();
  initAppSettings();
  initAcousticPresets();
  initFilterPresets();
  initMediaPlayer();
  initWindowsAudioSync();
});

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
