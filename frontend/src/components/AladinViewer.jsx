import React, { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CropSquareIcon from "@mui/icons-material/CropSquare";
import ExploreOutlinedIcon from "@mui/icons-material/ExploreOutlined";
import GridOnOutlinedIcon from "@mui/icons-material/GridOnOutlined";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import VisibilityOffOutlinedIcon from "@mui/icons-material/VisibilityOffOutlined";
import { useTheme } from "@mui/material/styles";
import {
  createOverlay,
  createViewer,
  destroyViewer,
  fovForRadius,
  getCenter,
  loadAladinLite,
  onViewer,
  probeHipsProperties,
  readRotationDeg,
  redrawOverlay,
  resetNorthUp,
  resizeViewer,
  setCooGrid,
  setFov,
  setPosition,
  writeRotationDeg,
} from "../integrations/aladin";

// Cutout API still caps radius at 30'; Aladin FoV itself is free for exploring the footprint.
const MAX_CUTOUT_RADIUS_ARCMIN = 30;

function bindRightDragRotate(aladin, host) {
  if (!aladin || !host) {
    return () => {};
  }
  const drag = { active: false, lastAngle: 0, rotation: 0, frame: 0 };

  const angleFromCenter = (event) => {
    const box = host.getBoundingClientRect();
    return (Math.atan2(event.clientY - (box.top + box.height / 2), event.clientX - (box.left + box.width / 2)) * 180) / Math.PI;
  };

  const onContextMenu = (event) => {
    event.preventDefault();
  };

  const onMouseDown = (event) => {
    if (event.button !== 2) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    drag.active = true;
    drag.lastAngle = angleFromCenter(event);
    drag.rotation = readRotationDeg(aladin);
  };

  const onMouseMove = (event) => {
    if (!drag.active) {
      return;
    }
    event.preventDefault();
    const angle = angleFromCenter(event);
    let delta = angle - drag.lastAngle;
    if (delta > 180) {
      delta -= 360;
    } else if (delta < -180) {
      delta += 360;
    }
    drag.lastAngle = angle;
    drag.rotation += delta;
    if (!drag.frame) {
      drag.frame = window.requestAnimationFrame(() => {
        drag.frame = 0;
        writeRotationDeg(aladin, drag.rotation);
      });
    }
  };

  const onMouseUp = () => {
    drag.active = false;
    if (drag.frame) {
      window.cancelAnimationFrame(drag.frame);
      drag.frame = 0;
      writeRotationDeg(aladin, drag.rotation);
    }
  };

  host.addEventListener("contextmenu", onContextMenu, true);
  host.addEventListener("mousedown", onMouseDown, true);
  window.addEventListener("mousemove", onMouseMove, true);
  window.addEventListener("mouseup", onMouseUp, true);
  window.addEventListener("blur", onMouseUp);

  return () => {
    drag.active = false;
    if (drag.frame) {
      window.cancelAnimationFrame(drag.frame);
    }
    host.removeEventListener("contextmenu", onContextMenu, true);
    host.removeEventListener("mousedown", onMouseDown, true);
    window.removeEventListener("mousemove", onMouseMove, true);
    window.removeEventListener("mouseup", onMouseUp, true);
    window.removeEventListener("blur", onMouseUp);
  };
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
  const containerRef = useRef(null);
  const aladinRef = useRef(null);
  const overlayRef = useRef(null);
  const stampRef = useRef({ ra, dec, radiusArcmin, color: overlayColor });
  const syncingRef = useRef(false);
  const readyRef = useRef(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [overlayMode, setOverlayMode] = useState("off");
  const [showCooGrid, setShowCooGrid] = useState(false);
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
  };

  useEffect(() => {
    let cancelled = false;
    let resizeObserver;
    let unbindRightDragRotate = () => {};
    let overlayRaf = 0;
    let zoomSettleTimer = 0;
    let centerSettleTimer = 0;
    let resizeRaf = 0;
    let zooming = false;
    let unsubscribePosition = () => {};
    let unsubscribeZoom = () => {};
    const drawStampNow = () => {
      const center = getCenter(aladinRef.current);
      if (!center) {
        return;
      }
      redrawOverlay(aladinRef.current, overlayRef.current, {
        ...stampRef.current,
        ra: center[0],
        dec: center[1],
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

    Promise.all([loadAladinLite(), probeHipsProperties(hips)])
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
        const initialRa = Number.isFinite(Number(ra)) ? Number(ra) : 0.5;
        const initialDec = Number.isFinite(Number(dec)) ? Number(dec) : 2.15;
        const initialRadius = Math.min(Number(radiusArcmin) || 1, MAX_CUTOUT_RADIUS_ARCMIN);
        const aladin = createViewer(containerRef.current, {
          hips,
          ra: initialRa,
          dec: initialDec,
          fov: fovForRadius(initialRadius, containerRef.current),
          onSurveyError: () => {
            if (!cancelled) {
              setMapUnavailable(true);
            }
          },
        });
        aladinRef.current = aladin;
        overlayRef.current = createOverlay(aladin, stampRef.current.color);
        redrawOverlay(aladin, overlayRef.current, stampRef.current);
        setFov(aladin, fovForRadius(initialRadius, containerRef.current, aladin));
        setCooGrid(aladin, false);
        resetNorthUp(aladin);

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
            const center = getCenter(aladin);
            if (center) {
              callbacksRef.current.onCenterChange?.(center[0], center[1]);
            }
          }, 120);
        };

        const pushRadiusFromAladin = () => {
          if (syncingRef.current) {
            return;
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

        unsubscribePosition = onViewer(aladin, "positionChanged", pushFromAladin);
        unsubscribeZoom = onViewer(aladin, "zoomChanged", pushRadiusFromAladin);
        unbindRightDragRotate = bindRightDragRotate(aladin, containerRef.current);
        readyRef.current = true;
        markReady();
        window.requestAnimationFrame(() => {
          if (!cancelled) {
            resizeViewer(aladin);
          }
        });
        if (typeof ResizeObserver !== "undefined" && containerRef.current) {
          resizeObserver = new ResizeObserver(() => {
            if (!cancelled && !resizeRaf) {
              resizeRaf = window.requestAnimationFrame(() => {
                resizeRaf = 0;
                if (!cancelled) {
                  resizeViewer(aladin);
                }
              });
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
      unbindRightDragRotate();
      unsubscribePosition();
      unsubscribeZoom();
      if (overlayRaf) {
        window.cancelAnimationFrame(overlayRaf);
      }
      if (resizeRaf) {
        window.cancelAnimationFrame(resizeRaf);
      }
      window.clearTimeout(zoomSettleTimer);
      window.clearTimeout(centerSettleTimer);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      destroyViewer(containerRef.current);
      aladinRef.current = null;
      overlayRef.current = null;
    };
    // Re-init when the survey HiPS URL changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hips?.url]);

  useEffect(() => {
    if (!readyRef.current) {
      return;
    }
    setCooGrid(aladinRef.current, showCooGrid);
  }, [showCooGrid]);

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
      setPosition(aladin, raVal, decVal);
      if (radiusVal <= MAX_CUTOUT_RADIUS_ARCMIN) {
        setFov(aladin, fovForRadius(radiusVal, containerRef.current, aladin));
      }
    } finally {
      window.setTimeout(() => {
        syncingRef.current = false;
        redrawOverlay(aladinRef.current, overlayRef.current, stampRef.current);
      }, 400);
    }
    // Apply form RA/Dec/radius only when the user clicks search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekId]);

  useEffect(() => {
    if (!readyRef.current || mapUnavailable) {
      return;
    }
    const aladin = aladinRef.current;
    const radiusVal = Number(radiusArcmin);
    if (
      aladin &&
      overlayMode !== "off" &&
      Number.isFinite(radiusVal) &&
      radiusVal > 0 &&
      radiusVal <= MAX_CUTOUT_RADIUS_ARCMIN
    ) {
      syncingRef.current = true;
      setFov(aladin, fovForRadius(radiusVal, containerRef.current, aladin));
      window.setTimeout(() => {
        syncingRef.current = false;
        redrawOverlay(aladinRef.current, overlayRef.current, stampRef.current);
      }, 400);
      return;
    }
    redrawOverlay(aladin, overlayRef.current, stampRef.current);
  }, [overlayColor, overlayMode, mapUnavailable, radiusArcmin]);

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
          // Aladin Lite v3 class names, used only to hide built-in chrome.
          "& .aladin-container, & .aladin-box, & canvas": {
            border: "none !important",
            outline: "none !important",
            boxShadow: "none !important",
          },
          "& .aladin-location, & .aladin-fov, & .aladin-status, & .aladin-context-menu, & .aladin-grid-control": {
            display: "none !important",
          },
        }}
      >
        <div ref={containerRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
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
          <Box
            sx={{
              position: "absolute",
              top: 8,
              right: 8,
              zIndex: 1200,
              pointerEvents: "auto",
              bgcolor: "background.paper",
              boxShadow: 1,
              borderRadius: 1,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
          >
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
                "& .MuiToggleButtonGroup-grouped": {
                  margin: 0,
                  border: 0,
                  borderRadius: 0,
                },
              }}
            >
              <Tooltip disableInteractive title="Hide cutout overlay">
                <ToggleButton value="off" aria-label="Hide cutout overlay">
                  <VisibilityOffOutlinedIcon fontSize="small" />
                </ToggleButton>
              </Tooltip>
              <Tooltip disableInteractive title="FITS stamp (square)">
                <ToggleButton value="square" aria-label="Show square stamp overlay">
                  <CropSquareIcon fontSize="small" />
                </ToggleButton>
              </Tooltip>
              <Tooltip disableInteractive title="Requested radius reference (circle)">
                <ToggleButton value="circle" aria-label="Show circular radius reference">
                  <RadioButtonUncheckedIcon fontSize="small" />
                </ToggleButton>
              </Tooltip>
            </ToggleButtonGroup>
            <Box role="separator" sx={{ height: "1px", bgcolor: "divider", mx: 0.75 }} />
            <Tooltip disableInteractive title={showCooGrid ? "Hide RA/Dec grid" : "Show RA/Dec grid"}>
              <ToggleButton
                size="small"
                value="grid"
                selected={showCooGrid}
                aria-label={showCooGrid ? "Hide RA/Dec grid" : "Show RA/Dec grid"}
                onClick={() => setShowCooGrid((prev) => !prev)}
                sx={{ border: 0, borderRadius: 0 }}
              >
                <GridOnOutlinedIcon fontSize="small" />
              </ToggleButton>
            </Tooltip>
            <Tooltip disableInteractive title="Reset north up. Right-drag the map to rotate.">
              <ToggleButton
                size="small"
                value="north"
                aria-label="Reset north up"
                onMouseDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  resetNorthUp(aladinRef.current);
                }}
                sx={{ border: 0, borderRadius: 0 }}
              >
                <ExploreOutlinedIcon fontSize="small" />
              </ToggleButton>
            </Tooltip>
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
