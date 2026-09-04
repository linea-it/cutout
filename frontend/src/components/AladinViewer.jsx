import React, { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

// Cutout API still caps radius at 30'; Aladin FoV itself is free for exploring the footprint.
const MAX_CUTOUT_RADIUS_ARCMIN = 30;
const MIN_FOV_DEG = (2 * 0.1) / 60; // ~0.1' radius floor for zoom-in
const MAX_FOV_DEG = 180;

function loadAladinAssets() {
  if (window.__aladinLiteLoading) {
    return window.__aladinLiteLoading;
  }
  if (window.A?.init) {
    return window.A.init;
  }

  window.__aladinLiteLoading = new Promise((resolve, reject) => {
    // Aladin Lite v3 bundles styles in JS; aladin.min.css on /latest/ is 404.

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
 * Aladin preview using the LIneA HiPS URL of the selected survey.
 * FoV can zoom out freely; cutout radius sync only applies within the API max.
 */
export default function AladinViewer({
  hips,
  ra,
  dec,
  radiusArcmin,
  seekId = 0,
  onCenterChange,
  onRadiusChange,
}) {
  const containerRef = useRef(null);
  const aladinRef = useRef(null);
  const surveyRef = useRef(null);
  const syncingRef = useRef(false);
  const readyRef = useRef(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const callbacksRef = useRef({ onCenterChange, onRadiusChange });

  useEffect(() => {
    callbacksRef.current = { onCenterChange, onRadiusChange };
  }, [onCenterChange, onRadiusChange]);

  useEffect(() => {
    let cancelled = false;
    let resizeObserver;
    setMapLoading(true);
    setMapUnavailable(false);

    const markReady = () => {
      if (!cancelled) {
        setMapLoading(false);
      }
    };

    const propertiesUrl = `${String(hips?.url || "").replace(/\/$/, "")}/properties`;
    const fetchOpts = {
      credentials: hips?.options?.requestCredentials === "include" ? "include" : "omit",
      mode: hips?.options?.requestMode === "same-origin" ? "same-origin" : "cors",
    };

    Promise.all([
      loadAladinAssets(),
      hips?.url
        ? fetch(propertiesUrl, fetchOpts).then(
            (response) => response,
            () => ({ ok: false, status: 0 }),
          )
        : Promise.resolve({ ok: false, status: 0 }),
    ])
      .then(([, propertiesResponse]) => {
        if (cancelled || !containerRef.current || aladinRef.current) {
          markReady();
          return;
        }
        if (!propertiesResponse?.ok) {
          setMapUnavailable(true);
          markReady();
          return;
        }
        const A = window.A;
        const initialRa = Number.isFinite(Number(ra)) ? Number(ra) : 0.5;
        const initialDec = Number.isFinite(Number(dec)) ? Number(dec) : 2.15;
        const initialFov = radiusToFovDeg(radiusArcmin || 1);
        const aladin = A.aladin(containerRef.current, {
          // Never omit `survey`: Aladin would load DSS2 as a fallback.
          survey: hips.url,
          fov: initialFov,
          target: `${initialRa} ${initialDec}`,
          cooFrame: "ICRSd",
          backgroundColor: "rgb(0, 0, 0)",
          showReticle: true,
          showZoomControl: true,
          showFullscreenControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showCooGridControl: false,
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
        aladinRef.current = aladin;

        if (aladin.options) {
          aladin.options.showContextMenu = false;
        }
        aladin.contextMenu = null;

        const hipsSurvey = aladin.createImageSurvey(
          hips.id,
          hips.name,
          hips.url,
          hips.cooFrame || "equatorial",
        );
        aladin.setImageSurvey(hipsSurvey, {
          imgFormat: "png",
          ...(hips.options || {}),
        });
        surveyRef.current = hipsSurvey;
        Promise.resolve(hipsSurvey).catch(() => {
          if (cancelled) {
            return;
          }
          try {
            ["P/DSS2/color", "CDS/P/DSS2/color"].forEach((id) => {
              aladin.removeImageLayer?.(id);
            });
            const base = aladin.getBaseImageLayer?.();
            if (base) {
              aladin.removeImageLayer?.(base);
            }
          } catch (err) {
            // ignore
          }
          setMapUnavailable(true);
        });

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
        };

        const pushRadiusFromAladin = () => {
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
          const radiusNow = fovToRadiusArcmin(exploreFov);
          if (radiusNow <= MAX_CUTOUT_RADIUS_ARCMIN) {
            callbacksRef.current.onRadiusChange?.(Math.max(0.1, radiusNow));
          }
        };

        aladin.on("positionChanged", pushFromAladin);
        aladin.on("zoomChanged", pushRadiusFromAladin);
        readyRef.current = true;
        markReady();
        window.requestAnimationFrame(() => {
          if (!cancelled && typeof aladin.resize === "function") {
            aladin.resize();
          }
        });
        if (typeof ResizeObserver !== "undefined" && containerRef.current) {
          resizeObserver = new ResizeObserver(() => {
            if (!cancelled && typeof aladin.resize === "function") {
              aladin.resize();
            }
          });
          resizeObserver.observe(containerRef.current);
        }
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error(err);
        if (!cancelled) {
          setMapUnavailable(true);
        }
        markReady();
      });

    return () => {
      cancelled = true;
      readyRef.current = false;
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
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
    // Re-init when the survey HiPS URL changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hips?.url]);

  useEffect(() => {
    if (!seekId) {
      return;
    }
    const aladin = aladinRef.current;
    if (!aladin || !readyRef.current) {
      return;
    }
    const raVal = Number(ra);
    const decVal = Number(dec);
    const radiusVal = Number(radiusArcmin);
    if (!Number.isFinite(raVal) || !Number.isFinite(decVal) || !Number.isFinite(radiusVal) || radiusVal <= 0) {
      return;
    }

    syncingRef.current = true;
    try {
      aladin.gotoRaDec(raVal, decVal);
      if (radiusVal <= MAX_CUTOUT_RADIUS_ARCMIN) {
        aladin.setFov(radiusToFovDeg(radiusVal));
      }
    } finally {
      window.setTimeout(() => {
        syncingRef.current = false;
      }, 80);
    }
    // Apply form RA/Dec/radius only when the user clicks search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekId]);

  return (
    <Box sx={{ width: "100%", height: "100%", minHeight: 0, flex: 1, display: "flex", flexDirection: "column" }}>
      <Box
        sx={{
          position: "relative",
          flex: 1,
          minHeight: 0,
          height: "100%",
          width: "100%",
          borderRadius: 1,
          overflow: "hidden",
          bgcolor: "#000",
          border: "1px solid",
          borderColor: "divider",
          "& .aladin-location, & .aladin-fov, & .aladin-status, & .aladin-context-menu": {
            display: "none !important",
          },
        }}
      >
        <div
          ref={containerRef}
          onContextMenu={(event) => event.preventDefault()}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        />
        {mapUnavailable ? (
          <Box
            sx={{
              position: "absolute",
              inset: 0,
              zIndex: 2,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              px: 2,
              bgcolor: "#000",
            }}
          >
            <Typography variant="body2" color="grey.400" align="center">
              Survey map is not available for this release.
            </Typography>
          </Box>
        ) : null}
        {mapLoading ? (
          <CircularProgress
            size={32}
            sx={{
              position: "absolute",
              top: "50%",
              left: "50%",
              zIndex: 2,
              marginTop: "-16px",
              marginLeft: "-16px",
              pointerEvents: "none",
            }}
          />
        ) : null}
      </Box>
    </Box>
  );
}
