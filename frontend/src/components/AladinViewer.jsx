import React, { useEffect, useRef } from "react";
import Box from "@mui/material/Box";

// Cutout API still caps radius at 30'; Aladin FoV itself is free for exploring the footprint.
const MAX_CUTOUT_RADIUS_ARCMIN = 30;
const MIN_FOV_DEG = (2 * 0.1) / 60; // ~0.1' radius floor for zoom-in
const MAX_FOV_DEG = 180; // allow zooming out to see the full DES footprint

const LINEA_DES_DR2_HIPS = {
  id: "DES_DR2_IRG_LIneA",
  name: "DES DR2 IRG at LIneA",
  url: "https://datasets.linea.org.br/data/releases/des/dr2/images/hips/",
  cooFrame: "equatorial",
  options: {
    requestCredentials: "include",
    requestMode: "cors",
  },
};

function loadAladinAssets() {
  if (window.__aladinLiteLoading) {
    return window.__aladinLiteLoading;
  }
  if (window.A?.init) {
    return window.A.init;
  }

  window.__aladinLiteLoading = new Promise((resolve, reject) => {
    const cssId = "aladin-lite-css";
    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = "https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.min.css";
      document.head.appendChild(link);
    }

    const scriptId = "aladin-lite-js";
    const existing = document.getElementById(scriptId);
    if (existing && window.A?.init) {
      window.A.init.then(resolve).catch(reject);
      return;
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js";
    script.async = true;
    script.onload = () => {
      if (!window.A?.init) {
        reject(new Error("Aladin Lite failed to initialize"));
        return;
      }
      window.A.init.then(resolve).catch(reject);
    };
    script.onerror = () => reject(new Error("Failed to load Aladin Lite"));
    document.head.appendChild(script);
  });

  return window.__aladinLiteLoading;
}

function clampExploreFovDeg(fovDeg) {
  return Math.min(MAX_FOV_DEG, Math.max(MIN_FOV_DEG, fovDeg));
}

function radiusToFovDeg(radiusArcmin) {
  return clampExploreFovDeg((2 * Number(radiusArcmin)) / 60);
}

function fovToRadiusArcmin(fovDeg) {
  return Number((((Number(fovDeg) * 60) / 2)).toFixed(3));
}

/**
 * Aladin preview using LIneA-hosted DES DR2 HiPS (same source as sky-viewer).
 * FoV can zoom out freely; cutout radius sync only applies within the API max.
 */
export default function AladinViewer({
  ra,
  dec,
  radiusArcmin,
  onCenterChange,
  onRadiusChange,
}) {
  const containerRef = useRef(null);
  const aladinRef = useRef(null);
  const surveyRef = useRef(null);
  const syncingRef = useRef(false);
  const readyRef = useRef(false);
  const callbacksRef = useRef({ onCenterChange, onRadiusChange });

  useEffect(() => {
    callbacksRef.current = { onCenterChange, onRadiusChange };
  }, [onCenterChange, onRadiusChange]);

  useEffect(() => {
    let cancelled = false;

    loadAladinAssets()
      .then(() => {
        if (cancelled || !containerRef.current || aladinRef.current) {
          return;
        }
        const A = window.A;
        const initialRa = Number.isFinite(Number(ra)) ? Number(ra) : 0.5;
        const initialDec = Number.isFinite(Number(dec)) ? Number(dec) : 2.15;
        const initialFov = radiusToFovDeg(radiusArcmin || 1);

        const aladin = A.aladin(containerRef.current, {
          fov: initialFov,
          target: `${initialRa} ${initialDec}`,
          cooFrame: "ICRSd",
          showReticle: true,
          showZoomControl: false,
          showFullscreenControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showCooGridControl: false,
          showProjectionControl: false,
          showFrame: false,
          showFov: false,
          // Top-left RA/Dec + copy control (default true in Aladin Lite v3).
          showCooLocation: false,
          showSimbadPointerControl: false,
          showShareControl: false,
          showSettingsControl: false,
          showContextMenu: false,
          showStatusBar: false,
        });
        aladinRef.current = aladin;

        // Aladin Lite 3.8.2 still opens the context menu on right-click even when
        // showContextMenu is false; drop the widget so attach/_show cannot run.
        if (aladin.options) {
          aladin.options.showContextMenu = false;
        }
        aladin.contextMenu = null;

        const hipsSurvey = aladin.createImageSurvey(
          LINEA_DES_DR2_HIPS.id,
          LINEA_DES_DR2_HIPS.name,
          LINEA_DES_DR2_HIPS.url,
          LINEA_DES_DR2_HIPS.cooFrame,
        );
        aladin.setImageSurvey(hipsSurvey, LINEA_DES_DR2_HIPS.options);
        surveyRef.current = hipsSurvey;

        const blockContextMenu = (event) => {
          event.preventDefault();
          event.stopPropagation();
        };
        containerRef.current.addEventListener("contextmenu", blockContextMenu, true);
        containerRef.current.__aladinBlockContextMenu = blockContextMenu;

        const pushFromAladin = () => {
          if (syncingRef.current) {
            return;
          }
          const [fovLon] = aladin.getFov();
          const exploreFov = clampExploreFovDeg(fovLon);
          if (Math.abs(exploreFov - fovLon) > 1e-6) {
            syncingRef.current = true;
            aladin.setFov(exploreFov);
            syncingRef.current = false;
          }
          const [raNow, decNow] = aladin.getRaDec();
          callbacksRef.current.onCenterChange?.(raNow, decNow);

          const radiusNow = fovToRadiusArcmin(exploreFov);
          // Only push radius into the form while within the cutout API limit.
          if (radiusNow <= MAX_CUTOUT_RADIUS_ARCMIN) {
            callbacksRef.current.onRadiusChange?.(Math.max(0.1, radiusNow));
          }
        };

        aladin.on("positionChanged", pushFromAladin);
        aladin.on("zoomChanged", pushFromAladin);
        readyRef.current = true;
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error(err);
      });

    return () => {
      cancelled = true;
      readyRef.current = false;
      if (containerRef.current) {
        const blockContextMenu = containerRef.current.__aladinBlockContextMenu;
        if (blockContextMenu) {
          containerRef.current.removeEventListener("contextmenu", blockContextMenu, true);
          delete containerRef.current.__aladinBlockContextMenu;
        }
        containerRef.current.innerHTML = "";
      }
      aladinRef.current = null;
      surveyRef.current = null;
    };
    // init once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const aladin = aladinRef.current;
    if (!aladin || !readyRef.current) {
      return;
    }
    const raVal = Number(ra);
    const decVal = Number(dec);
    const radiusVal = Number(radiusArcmin);
    if (!Number.isFinite(raVal) || !Number.isFinite(decVal) || !Number.isFinite(radiusVal)) {
      return;
    }

    syncingRef.current = true;
    try {
      aladin.gotoRaDec(raVal, decVal);
      // Form radius only drives FoV when within the cutout max (avoids yanking zoom out).
      if (radiusVal <= MAX_CUTOUT_RADIUS_ARCMIN) {
        const [currentFov] = aladin.getFov();
        const impliedRadius = fovToRadiusArcmin(currentFov);
        // If user zoomed out past the cutout size, keep that explore FoV.
        if (impliedRadius <= MAX_CUTOUT_RADIUS_ARCMIN) {
          aladin.setFov(radiusToFovDeg(radiusVal));
        }
      }
    } finally {
      syncingRef.current = false;
    }
  }, [ra, dec, radiusArcmin]);

  return (
    <Box sx={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 1 }}>
      <Box
        ref={containerRef}
        onContextMenu={(event) => event.preventDefault()}
        sx={{
          flex: 1,
          minHeight: 420,
          width: "100%",
          borderRadius: 1,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
          // Hide chrome Aladin may still inject despite options (esp. older CDN builds).
          "& .aladin-location, & .aladin-fov, & .aladin-context-menu": {
            display: "none !important",
          },
        }}
      />
    </Box>
  );
}
