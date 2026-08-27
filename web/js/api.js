// API Client Module

export async function apiGet(endpoint) {
  try {
    const headers = {};
    const token = localStorage.getItem("access_token");
    if (token) {
      headers["X-Access-Token"] = token;
    }

    const response = await fetch(endpoint, { headers });
    if (response.status === 401) {
      handleUnauthorized();
      return null;
    }
    return await response.json();
  } catch (e) {
    console.error(`GET error ${endpoint}:`, e);
    return null;
  }
}

export async function apiPost(endpoint, data = {}) {
  try {
    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem("access_token");
    if (token) {
      headers["X-Access-Token"] = token;
    }

    const response = await fetch(endpoint, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(data)
    });
    if (response.status === 401) {
      handleUnauthorized();
      return null;
    }
    return await response.json();
  } catch (e) {
    console.error(`POST error ${endpoint}:`, e);
    return null;
  }
}

export function handleUnauthorized() {
  if (window.isPromptingAuth) return;
  window.isPromptingAuth = true;

  const userToken = prompt("Access Token Required.\nPlease enter the secure Access Token to connect to this Audioscape controller:");
  if (userToken) {
    localStorage.setItem("access_token", userToken.trim());
    window.isPromptingAuth = false;
    window.location.reload();
  } else {
    window.isPromptingAuth = false;
  }
}

export function showToast(title, desc, color) {
  apiPost("/api/notify", {
    title: title,
    message: desc,
    dedupe_key: title.toLowerCase().replace(/\s+/g, "_")
  });
}
