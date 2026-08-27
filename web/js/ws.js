// WebSocket Client Module for HomeTheaterX
// Provides real-time bi-directional connection for zero-latency audio peaks,
// system media metadata, and hardware volume sync.

import { state } from './state.js';
import { apiGet } from './api.js';

let socket = null;
let isConnected = false;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_DELAY = 5000;

// Listeners registry for custom message handlers
const messageListeners = new Set();

export function addWsListener(callback) {
  messageListeners.add(callback);
}

export function removeWsListener(callback) {
  messageListeners.delete(callback);
}

export function isWsConnected() {
  return isConnected;
}

export async function initWebSocket(handlers = {}) {
  if (socket && (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN)) {
    return;
  }

  // 1. Determine target port and host
  let wsPort = 5010;
  try {
    const wsInfo = await apiGet("/api/ws_info");
    if (wsInfo && wsInfo.ws_port) {
      wsPort = wsInfo.ws_port;
    }
  } catch (e) {
    const currentHttpPort = parseInt(window.location.port) || 5000;
    wsPort = currentHttpPort + 10;
  }

  const hostname = window.location.hostname || "localhost";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  
  // Retrieve token if present
  const token = localStorage.getItem("access_token") || "";
  const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : "";
  const wsUrl = `${protocol}//${hostname}:${wsPort}${tokenQuery}`;

  console.log(`[WS] Connecting to ${wsUrl}...`);

  try {
    socket = new WebSocket(wsUrl);
  } catch (err) {
    console.error("[WS] Initialization error:", err);
    scheduleReconnect(handlers);
    return;
  }

  socket.onopen = () => {
    console.log("[WS] Connection established.");
    isConnected = true;
    reconnectAttempts = 0;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    
    // Request full status snapshot immediately
    sendWsMessage({ type: "get_status" });
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (!payload || !payload.type) return;

      // Handle Core Events
      if (payload.type === "audio_peak") {
        if (typeof payload.peak === "number") {
          state.windowsAudioPeak = state.windowsAudioPeak * 0.25 + payload.peak * 0.75;
        }
      } else if (payload.type === "media_status") {
        if (handlers.onMediaUpdate && payload.data) {
          handlers.onMediaUpdate(payload.data);
        }
      } else if (payload.type === "volume_status") {
        if (handlers.onVolumeUpdate && !state.isUserDragging) {
          handlers.onVolumeUpdate(payload);
        }
      } else if (payload.type === "device_changed") {
        if (handlers.onDeviceChanged) {
          handlers.onDeviceChanged(payload);
        }
      } else if (payload.type === "full_status") {
        if (handlers.onFullStatus) {
          handlers.onFullStatus(payload);
        }
      }

      // Notify any generic listeners
      for (const listener of messageListeners) {
        try {
          listener(payload);
        } catch (err) {
          console.error("[WS] Listener dispatch error:", err);
        }
      }
    } catch (parseErr) {
      console.error("[WS] Message parsing error:", parseErr);
    }
  };

  socket.onclose = (event) => {
    console.warn(`[WS] Connection closed (code: ${event.code}). Scheduling reconnect...`);
    isConnected = false;
    scheduleReconnect(handlers);
  };

  socket.onerror = (error) => {
    console.error("[WS] Connection error:", error);
    try {
      socket.close();
    } catch (e) {}
  };
}

function scheduleReconnect(handlers) {
  if (reconnectTimer) return;
  reconnectAttempts++;
  const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), MAX_RECONNECT_DELAY);
  console.log(`[WS] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts})...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initWebSocket(handlers);
  }, delay);
}

export function sendWsMessage(obj) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    try {
      socket.send(JSON.stringify(obj));
      return true;
    } catch (e) {
      console.error("[WS] Send error:", e);
    }
  }
  return false;
}
