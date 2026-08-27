// Global Shared State Module

export const ids = ["surroundL", "towerL", "subwoofer", "center", "towerR", "surroundR"];

export const channelIndexMap = {
  "towerL": 0,
  "towerR": 1,
  "center": 2,
  "subwoofer": 3,
  "surroundL": 4,
  "surroundR": 5
};

export const state = {
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

  // Poll suppression
  pollLockUntil: 0,

  // Custom View States
  currentView: "studio",
  receiverInput: "HDMI 1 / eARC",
  receiverDSP: "ATMOS STANDARD",
  drcActive: true,
  crossoverVal: "80 Hz",

  // Speaker solo/isolate state
  solo: { active: false, channel: null },

  eightd: {
    active: false,
    angle: 0,
    interval: null,
    speed: 0.056,
    originalVolumes: {},
    shouldRestoreDolby: false
  },

  bassManagementActive: false,
  ddlActive: false,

  // Settings toggles
  settings: {
    notifications_enabled: true,
    minimize_to_tray_on_close: true,
    calibration_mode: "sweetspot"
  },
  startupEnabled: false
};

// State update locks
export function setUserDragging() {
  state.isUserDragging = true;
  clearTimeout(state.userDraggingTimeout);
  state.userDraggingTimeout = setTimeout(() => {
    state.isUserDragging = false;
  }, 1200);
}

export function lockPollFor(ms) {
  state.pollLockUntil = Date.now() + ms;
}
