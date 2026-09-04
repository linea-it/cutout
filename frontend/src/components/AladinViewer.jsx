import React, { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CropSquareIcon from "@mui/icons-material/CropSquare";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import VisibilityOffOutlinedIcon from "@mui/icons-material/VisibilityOffOutlined";
import { useTheme } from "@mui/material/styles";

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

function themePaddingPx(theme) {
  const raw = theme.spacing(2);
  const value = typeof raw === "number" ? raw : Number.parseFloat(raw);
  return Number.isFinite(value) ? value : 16;
}

function fovToRadiusArcmin(fovDeg) {
  return Number((((Number(fovDeg) * 60) / 2)).toFixed(3));
}

/** On-sky square (astrocut): equal angular size in RA and Dec. ΔRA is /cos(Dec). */
function stampSquareVertices(raDeg, decDeg, radiusArcmin) {
  const halfDeg = Number(radiusArcmin) / 60;
  const ra0 = Number(raDeg);
  const dec0 = Number(decDeg);
  const cosDec = Math.cos((dec0 * Math.PI) / 180);
  const halfRa = halfDeg / Math.max(Math.abs(cosDec), 1e-6);
  return [
    [ra0 - halfRa, dec0 - halfDeg],
    [ra0 + halfRa, dec0 - halfDeg],
    [ra0 + halfRa, dec0 + halfDeg],
    [ra0 - halfRa, dec0 + halfDeg],
    [ra0 - halfRa, dec0 - halfDeg],
  ];
}

function readFovDeg(aladin) {
  const fov = aladin && typeof aladin.getFov === "function" ? aladin.getFov() : null;
  if (Array.isArray(fov)) {
    const lon = Number(fov[0]);
    const lat = Number(fov[1]);
    return [lon, Number.isFinite(lat) && lat > 0 ? lat : lon];
  }
  const value = Number(fov);
  return [value, value];
}

function viewRadiusArcmin(aladin) {
  const [fovLon] = readFovDeg(aladin);
  return fovToRadiusArcmin(fovLon);
}

function overlayRadiusArcmin(aladin, formRadiusRaw) {
  const formRadius = Number(formRadiusRaw);
  const viewRadius = viewRadiusArcmin(aladin);
  if (Number.isFinite(viewRadius) && viewRadius >= MAX_CUTOUT_RADIUS_ARCMIN) {
    return MAX_CUTOUT_RADIUS_ARCMIN;
  }
  if (Number.isFinite(viewRadius) && viewRadius > 0) {
    return viewRadius;
  }
  if (!Number.isFinite(formRadius) || formRadius <= 0) {
    return MAX_CUTOUT_RADIUS_ARCMIN;
  }
  return Math.min(formRadius, MAX_CUTOUT_RADIUS_ARCMIN);
}

/** Pixel inset only while the stamp fills the view. At/past 30' use the true on-sky size. */
function paddedOverlayRadiusArcmin(aladin, container, formRadiusRaw, padPx) {
  const scientific = overlayRadiusArcmin(aladin, formRadiusRaw);
  const viewRadius = viewRadiusArcmin(aladin);
  if (viewRadius >= MAX_CUTOUT_RADIUS_ARCMIN || scientific >= MAX_CUTOUT_RADIUS_ARCMIN) {
    return MAX_CUTOUT_RADIUS_ARCMIN;
  }
  if (!aladin || !container) {
    return scientific;
  }
  const [fovLon, fovLat] = readFovDeg(aladin);
  const fovMin = Math.min(fovLon, fovLat);
  const shortPx = Math.min(container.clientWidth, container.clientHeight);
  if (!Number.isFinite(fovMin) || fovMin <= 0 || shortPx <= 0) {
    return scientific;
  }
  const maxPx = shortPx - 2 * padPx;
  if (maxPx <= 1) {
    return scientific;
  }
  const sideDeg = (2 * scientific) / 60;
  const stampPx = (sideDeg * shortPx) / fovMin;
  if (stampPx <= maxPx) {
    return scientific;
  }
  const drawnSideDeg = (maxPx * fovMin) / shortPx;
  return (drawnSideDeg * 60) / 2;
}

function addOverlayShape(overlay, shape) {
  if (typeof overlay.addFootprints === "function") {
    overlay.addFootprints(Array.isArray(shape) ? shape : [shape]);
  } else if (typeof overlay.add === "function") {
    overlay.add(shape);
  }
}

const overlayDrawKeys = new WeakMap();

function refreshAladin(aladin) {
  if (!aladin) {
    return;
  }
  if (aladin.view && typeof aladin.view.requestRedraw === "function") {
    aladin.view.requestRedraw();
  } else if (typeof aladin.resize === "function") {
    aladin.resize();
  }
}

function redrawCutoutStamp(aladin, overlay, stamp) {
  const A = window.A;
  if (!aladin || !overlay || !A) {
    return;
  }
  if (!stamp.mode || stamp.mode === "off") {
    if (typeof overlay.removeAll === "function") {
      overlay.removeAll();
    }
    overlayDrawKeys.set(overlay, "off");
    if (typeof overlay.hide === "function") {
      overlay.hide();
    }
    refreshAladin(aladin);
    return;
  }
  if (typeof overlay.show === "function") {
    overlay.show();
  }
  const raVal = Number(stamp.ra);
  const decVal = Number(stamp.dec);
  if (!Number.isFinite(raVal) || !Number.isFinite(decVal)) {
    return;
  }
  const radius = paddedOverlayRadiusArcmin(
    aladin,
    stamp.container,
    stamp.radiusArcmin,
    stamp.padPx || 16,
  );
  const drawKey = `${stamp.mode}:${raVal.toFixed(5)}:${decVal.toFixed(5)}:${radius.toFixed(4)}:${stamp.color}`;
  if (overlayDrawKeys.get(overlay) === drawKey) {
    return;
  }
  overlayDrawKeys.set(overlay, drawKey);
  if (typeof overlay.removeAll === "function") {
    overlay.removeAll();
  }
  if (Object.prototype.hasOwnProperty.call(overlay, "color")) {
    overlay.color = stamp.color;
  }
  const style = { color: stamp.color, fillOpacity: 0, lineWidth: 2 };
  if (stamp.mode === "circle" && typeof A.circle === "function") {
    addOverlayShape(overlay, A.circle(raVal, decVal, radius / 60, style));
  } else if (typeof A.polygon === "function") {
    addOverlayShape(overlay, A.polygon(stampSquareVertices(raVal, decVal, radius), style));
  }
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
  const theme = useTheme();
  const overlayColor = theme.palette.primary.main;
  const overlayPadPx = themePaddingPx(theme);
  const overlayPadPxRef = useRef(overlayPadPx);
  overlayPadPxRef.current = overlayPadPx;
  const containerRef = useRef(null);
  const aladinRef = useRef(null);
  const surveyRef = useRef(null);
  const overlayRef = useRef(null);
  const stampRef = useRef({ ra, dec, radiusArcmin, color: overlayColor });
  const syncingRef = useRef(false);
  const readyRef = useRef(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [overlayMode, setOverlayMode] = useState("off");
  const callbacksRef = useRef({ onCenterChange, onRadiusChange });

  useEffect(() => {
    callbacksRef.current = { onCenterChange, onRadiusChange };
  }, [onCenterChange, onRadiusChange]);

  stampRef.current = {
    ra,
    dec,
    radiusArcmin,
    color: overlayColor,
    mode: overlayMode,
    container: containerRef.current,
    padPx: overlayPadPx,
  };

  useEffect(() => {
    let cancelled = false;
    let resizeObserver;
    let overlayRaf = 0;
    let zoomSettleTimer = 0;
    let centerSettleTimer = 0;
    let zooming = false;
    const drawStampNow = () => {
      const aladin = aladinRef.current;
      if (!aladin || typeof aladin.getRaDec !== "function") {
        return;
      }
      const [raNow, decNow] = aladin.getRaDec();
      redrawCutoutStamp(aladin, overlayRef.current, {
        ...stampRef.current,
        ra: raNow,
        dec: decNow,
        container: containerRef.current,
        padPx: overlayPadPxRef.current,
      });
    };
    const queueStampRedraw = () => {
      if (zooming) {
        return;
      }
      if (overlayRaf) {
        window.cancelAnimationFrame(overlayRaf);
      }
      overlayRaf = window.requestAnimationFrame(() => {
        overlayRaf = 0;
        if (cancelled || zooming) {
          return;
        }
        drawStampNow();
      });
    };
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
        const initialFov = radiusToFovDeg(
          Math.min(Number(radiusArcmin) || 1, MAX_CUTOUT_RADIUS_ARCMIN),
        );
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

        if (typeof A.graphicOverlay === "function") {
          const overlay = A.graphicOverlay({
            name: "cutout-stamp",
            color: stampRef.current.color,
            lineWidth: 2,
          });
          aladin.addOverlay(overlay);
          overlayRef.current = overlay;
          redrawCutoutStamp(aladin, overlay, stampRef.current);
        }

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
          queueStampRedraw();
          window.clearTimeout(centerSettleTimer);
          centerSettleTimer = window.setTimeout(() => {
            centerSettleTimer = 0;
            if (cancelled || syncingRef.current) {
              return;
            }
            const [raNow, decNow] = aladin.getRaDec();
            callbacksRef.current.onCenterChange?.(raNow, decNow);
          }, 120);
        };

        const pushRadiusFromAladin = () => {
          if (syncingRef.current) {
            return;
          }
          const radiusNow = viewRadiusArcmin(aladin);
          if (radiusNow <= MAX_CUTOUT_RADIUS_ARCMIN) {
            callbacksRef.current.onRadiusChange?.(Math.max(0.1, radiusNow));
          }
          zooming = true;
          window.clearTimeout(zoomSettleTimer);
          zoomSettleTimer = window.setTimeout(() => {
            zoomSettleTimer = 0;
            zooming = false;
            if (!cancelled) {
              drawStampNow();
            }
          }, 40);
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
            if (cancelled) {
              return;
            }
            if (typeof aladin.resize === "function") {
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
      if (overlayRaf) {
        window.cancelAnimationFrame(overlayRaf);
      }
      window.clearTimeout(zoomSettleTimer);
      window.clearTimeout(centerSettleTimer);
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
      overlayRef.current = null;
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
        redrawCutoutStamp(aladinRef.current, overlayRef.current, stampRef.current);
      }, 80);
    }
    // Apply form RA/Dec/radius only when the user clicks search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekId]);

  useEffect(() => {
    if (!readyRef.current || mapUnavailable) {
      return;
    }
    redrawCutoutStamp(aladinRef.current, overlayRef.current, stampRef.current);
  }, [overlayColor, overlayMode, mapUnavailable]);

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
          "& .aladin-container, & .aladin-box, & canvas": {
            border: "none !important",
            outline: "none !important",
            boxShadow: "none !important",
          },
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
        {!mapUnavailable && !mapLoading ? (
          <ToggleButtonGroup
            exclusive
            orientation="vertical"
            size="small"
            value={overlayMode}
            onChange={(_event, next) => {
              if (next) {
                setOverlayMode(next);
              }
            }}
            sx={{
              position: "absolute",
              top: 8,
              right: 8,
              zIndex: 3,
              bgcolor: "background.paper",
              boxShadow: 1,
            }}
          >
            <Tooltip title="Hide cutout overlay">
              <ToggleButton value="off" aria-label="Hide cutout overlay">
                <VisibilityOffOutlinedIcon fontSize="small" />
              </ToggleButton>
            </Tooltip>
            <Tooltip title="FITS stamp (square)">
              <ToggleButton value="square" aria-label="Show square stamp overlay">
                <CropSquareIcon fontSize="small" />
              </ToggleButton>
            </Tooltip>
            <Tooltip title="Requested radius (circle)">
              <ToggleButton value="circle" aria-label="Show circular radius overlay">
                <RadioButtonUncheckedIcon fontSize="small" />
              </ToggleButton>
            </Tooltip>
          </ToggleButtonGroup>
        ) : null}
      </Box>
    </Box>
  );
}
