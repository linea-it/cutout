// Compatibility boundary for Aladin Lite v3.8.2. Keep Aladin-specific APIs here.
const ALADIN_LITE_VERSION = "3.8.2";
const ALADIN_LITE_SCRIPT_URL = `https://aladin.cds.unistra.fr/AladinLite/api/v3/${ALADIN_LITE_VERSION}/aladin.js`;
const SCRIPT_ID = "aladin-lite-js";
const MIN_FOV_DEG = (2 * 0.1) / 60;
const MAX_FOV_DEG = 180;
const GRID_COLOR = "#6fdc7a";
const overlayDrawKeys = new WeakMap();

function getAladinApi() {
  if (!window.A?.init) {
    throw new Error("Aladin Lite v3 API is unavailable");
  }
  return window.A;
}

export function loadAladinLite() {
  if (window.__cutoutAladinLiteLoading) {
    return window.__cutoutAladinLiteLoading;
  }
  if (window.A?.init) {
    return window.A.init;
  }

  window.__cutoutAladinLiteLoading = new Promise((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID);
    if (existing) {
      existing.addEventListener("load", () => {
        if (!window.A?.init) {
          reject(new Error("Aladin Lite v3 API is unavailable"));
          return;
        }
        window.A.init.then(resolve).catch(reject);
      });
      existing.addEventListener("error", () => reject(new Error("Failed to load Aladin Lite v3")));
      return;
    }

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = ALADIN_LITE_SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      if (!window.A?.init) {
        reject(new Error("Aladin Lite v3 API is unavailable"));
        return;
      }
      window.A.init.then(resolve).catch(reject);
    };
    script.onerror = () => reject(new Error("Failed to load Aladin Lite v3"));
    document.head.appendChild(script);
  });

  return window.__cutoutAladinLiteLoading;
}

export function probeHipsProperties(hips) {
  if (!hips?.url) {
    return Promise.resolve({ ok: false, status: 0 });
  }
  const url = `${String(hips.url).replace(/\/$/, "")}/properties`;
  return fetch(url, {
    credentials: hips.options?.requestCredentials === "include" ? "include" : "omit",
    mode: hips.options?.requestMode === "same-origin" ? "same-origin" : "cors",
  }).then(
    (response) => response,
    () => ({ ok: false, status: 0 }),
  );
}

export function fovForRadius(radiusArcmin, container, aladin) {
  const diameterDeg = (2 * Number(radiusArcmin)) / 60;
  const canvas = container?.querySelector?.("canvas");
  const width = canvas?.clientWidth || container?.clientWidth || aladin?.view?.width;
  const height = canvas?.clientHeight || container?.clientHeight || aladin?.view?.height;
  const aspect = Number(width) > 0 && Number(height) > 0 ? Number(width) / Number(height) : 1;
  // Aladin's scalar FoV follows the wide axis. Expand it so the short axis
  // contains the square FITS footprint, with a small margin so the stroke is
  // not clipped at the canvas edge.
  return Math.min(MAX_FOV_DEG, Math.max(MIN_FOV_DEG, diameterDeg * Math.max(1, aspect) * 1.08));
}

function refreshViewer(aladin) {
  if (typeof aladin?.view?.requestRedraw === "function") {
    aladin.view.requestRedraw();
    return;
  }
  aladin?.resize?.();
}

function removeFallbackSurveyLayers(aladin) {
  ["P/DSS2/color", "CDS/P/DSS2/color"].forEach((id) => aladin.removeImageLayer?.(id));
  const base = aladin.getBaseImageLayer?.();
  if (base) {
    aladin.removeImageLayer?.(base);
  }
}

export function createViewer(container, { hips, ra, dec, fov, onSurveyError }) {
  const A = getAladinApi();
  const aladin = A.aladin(container, {
    // Never omit survey: Aladin otherwise falls back to DSS2.
    survey: hips.url,
    fov,
    target: `${ra} ${dec}`,
    cooFrame: "ICRSd",
    backgroundColor: "rgb(0, 0, 0)",
    showReticle: true,
    showZoomControl: true,
    showFullscreenControl: false,
    showLayersControl: false,
    showGotoControl: false,
    showCooGrid: false,
    showCooGridControl: false,
    gridOptions: {
      enabled: false,
      color: GRID_COLOR,
      opacity: 0.85,
      thickness: 1,
      showLabels: true,
      labelSize: 14,
    },
    showProjectionControl: false,
    showFrame: false,
    showFov: false,
    showCooLocation: false,
    showSimbadPointerControl: false,
    showShareControl: false,
    showSettingsControl: false,
    showContextMenu: false,
    showStatusBar: false,
  });
  if (aladin.options) {
    aladin.options.showContextMenu = false;
  }
  aladin.contextMenu = null;

  const survey = aladin.createImageSurvey(hips.id, hips.name, hips.url, hips.cooFrame || "equatorial");
  aladin.setImageSurvey(survey, { imgFormat: "png", ...(hips.options || {}) });
  Promise.resolve(survey).catch(() => {
    removeFallbackSurveyLayers(aladin);
    onSurveyError?.();
  });
  return aladin;
}

export function getCenter(aladin) {
  return typeof aladin?.getRaDec === "function" ? aladin.getRaDec() : null;
}

export function setPosition(aladin, ra, dec) {
  aladin?.gotoRaDec?.(ra, dec);
}

export function setFov(aladin, fov) {
  aladin?.setFov?.(fov);
}

export function onViewer(aladin, event, callback) {
  aladin?.on?.(event, callback);
  return () => aladin?.off?.(event, callback);
}

export function resizeViewer(aladin) {
  if (typeof aladin?.resize === "function") {
    aladin.resize();
    return;
  }
  refreshViewer(aladin);
}

export function destroyViewer(container) {
  if (container) {
    container.innerHTML = "";
  }
}

export function setCooGrid(aladin, enabled) {
  aladin?.setCooGrid?.({
    enabled: Boolean(enabled),
    color: GRID_COLOR,
    opacity: 0.85,
    thickness: 1,
    showLabels: true,
    labelSize: 14,
  });
}

export function readRotationDeg(aladin) {
  try {
    const value = aladin?.view?.wasm?.getRotation?.() ?? aladin?.getRotation?.();
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  } catch (err) {
    return 0;
  }
}

export function writeRotationDeg(aladin, deg) {
  const wasm = aladin?.view?.wasm;
  if (typeof wasm?.setRotation === "function") {
    wasm.setRotation(deg);
  } else if (typeof aladin?.setRotation === "function") {
    aladin.setRotation(deg);
  }
  refreshViewer(aladin);
}

export function resetNorthUp(aladin) {
  if (!aladin) {
    return;
  }
  const wasm = aladin.view?.wasm;
  // Bypass View.setRotation early-return when getRotation() is already ~0
  // but the camera heading is not north-up after panning.
  if (typeof wasm?.setRotation === "function") {
    wasm.setRotation(0);
  } else if (typeof aladin.setRotation === "function") {
    aladin.setRotation(0);
  } else if (typeof aladin.setViewCenter2NorthPoleAngle === "function") {
    aladin.setViewCenter2NorthPoleAngle(0);
  }
  refreshViewer(aladin);
}

function stampSquareVertices(raDeg, decDeg, radiusArcmin) {
  const halfDeg = Number(radiusArcmin) / 60;
  const cosDec = Math.cos((Number(decDeg) * Math.PI) / 180);
  const halfRa = halfDeg / Math.max(Math.abs(cosDec), 1e-6);
  return [
    [Number(raDeg) - halfRa, Number(decDeg) - halfDeg],
    [Number(raDeg) + halfRa, Number(decDeg) - halfDeg],
    [Number(raDeg) + halfRa, Number(decDeg) + halfDeg],
    [Number(raDeg) - halfRa, Number(decDeg) + halfDeg],
    [Number(raDeg) - halfRa, Number(decDeg) - halfDeg],
  ];
}

export function createOverlay(aladin, color) {
  const A = getAladinApi();
  if (typeof A.graphicOverlay !== "function") {
    return null;
  }
  const overlay = A.graphicOverlay({ name: "cutout-stamp", color, lineWidth: 2 });
  aladin.addOverlay?.(overlay);
  return overlay;
}

function addShape(overlay, shape) {
  if (typeof overlay.addFootprints === "function") {
    overlay.addFootprints(Array.isArray(shape) ? shape : [shape]);
  } else {
    overlay.add?.(shape);
  }
}

export function redrawOverlay(aladin, overlay, stamp) {
  if (!aladin || !overlay) {
    return;
  }
  if (!stamp.mode || stamp.mode === "off") {
    overlay.removeAll?.();
    overlay.hide?.();
    overlayDrawKeys.set(overlay, "off");
    refreshViewer(aladin);
    return;
  }
  overlay.show?.();
  const ra = Number(stamp.ra);
  const dec = Number(stamp.dec);
  const radius = Number(stamp.radiusArcmin);
  if (!Number.isFinite(ra) || !Number.isFinite(dec) || !Number.isFinite(radius) || radius <= 0) {
    return;
  }
  const key = `${stamp.mode}:${ra.toFixed(5)}:${dec.toFixed(5)}:${radius.toFixed(4)}:${stamp.color}`;
  if (overlayDrawKeys.get(overlay) === key) {
    return;
  }
  const A = getAladinApi();
  overlayDrawKeys.set(overlay, key);
  overlay.removeAll?.();
  if (Object.prototype.hasOwnProperty.call(overlay, "color")) {
    overlay.color = stamp.color;
  }
  const style = { color: stamp.color, fillOpacity: 0, lineWidth: 2 };
  if (stamp.mode === "circle" && typeof A.circle === "function") {
    addShape(overlay, A.circle(ra, dec, radius / 60, style));
  } else if (typeof A.polygon === "function") {
    addShape(overlay, A.polygon(stampSquareVertices(ra, dec, radius), style));
  }
}
