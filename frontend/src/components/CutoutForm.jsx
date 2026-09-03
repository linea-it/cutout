import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormLabel from "@mui/material/FormLabel";
import Grid from "@mui/material/Grid2";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import ClearIcon from "@mui/icons-material/Clear";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import LoginIcon from "@mui/icons-material/Login";
import PlaylistAddCheckIcon from "@mui/icons-material/PlaylistAddCheck";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import AladinViewer from "./AladinViewer";
import JobTray from "./JobTray";
import { loadStoredJobs, makeJobLabel, saveStoredJobs } from "../jobStorage";
import JSZip from "jszip";

const LINEA_HIPS_OPTIONS = {
  requestCredentials: "include",
  requestMode: "cors",
};

const DEFAULT_SKYVIEWER_BASE_HOST = "https://skyviewer.linea.org.br";

function buildSurveys(skyviewerBaseHost) {
  const baseHost = (skyviewerBaseHost || DEFAULT_SKYVIEWER_BASE_HOST).replace(/\/$/, "");
  return [
    {
      id: "des_dr2",
      label: "DES DR2",
      bands: ["g", "r", "i", "z", "Y"],
      rgbPresets: ["gri", "riz", "izY"],
      defaultRa: "0.5",
      defaultDec: "2.15",
      hips: {
        id: "DES_DR2_IRG_LIneA",
        name: "DES DR2 IRG at LIneA",
        url: "https://datasets.linea.org.br/data/releases/des/dr2/images/hips/",
        cooFrame: "equatorial",
        options: LINEA_HIPS_OPTIONS,
      },
    },
    {
      id: "lsst_dp1",
      label: "LSST DP1",
      requireGroup: "lsst_dp1",
      bands: ["u", "g", "r", "i", "z", "y"],
      rgbPresets: ["gri", "riz", "izy"],
      // Sky Viewer: "02 39 35.55 -34 30 38.3"
      defaultRa: "39.898125",
      defaultDec: "-34.510639",
      hips: {
        id: "LSST_DP1_IRG_LIneA",
        name: "LSST DP1 IRG at LIneA",
        // Igual ao sky-viewer: `${baseHost}/data/releases/lsst/dp1/images/hips`
        url: `${baseHost}/data/releases/lsst/dp1/images/hips`,
        cooFrame: "equatorial",
        options: LINEA_HIPS_OPTIONS,
      },
    },
  ];
}

const ALL_BANDS = [...new Set(buildSurveys().flatMap((s) => s.bands))];
const MAX_RADIUS_ARCMIN = 30;
const SYNC_RADIUS_LIMIT_ARCMIN = 10;
const CARD_MIN_HEIGHT = 560;
const ASYNC_POLL_MS = 3000;

function arcminToDeg(arcmin) {
  return arcmin / 60;
}

function parseFilename(contentDisposition, fallback) {
  if (!contentDisposition) {
    return fallback;
  }
  const utfMatch = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
  if (utfMatch) {
    try {
      return decodeURIComponent(utfMatch[1]);
    } catch {
      return utfMatch[1];
    }
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(contentDisposition);
  return plainMatch ? plainMatch[1] : fallback;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildBody(params) {
  const body = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      body.set(key, String(value));
    }
  });
  return body;
}

function isOpenPhase(phase) {
  const value = String(phase || "").toUpperCase();
  return value !== "COMPLETED" && value !== "ERROR" && value !== "ABORTED";
}

function regionParams(region, { includePhase = true } = {}) {
  const params = {
    id: region.surveyId,
    POS: `CIRCLE ${region.ra} ${region.dec} ${arcminToDeg(region.radiusArcmin)}`,
    format: region.format,
  };
  if (includePhase) {
    params.phase = "RUN";
  }
  if (region.format === "png" && region.color) {
    params.color = "true";
    params.rgb_bands = region.rgbBands;
  } else {
    params.band = region.band;
  }
  return params;
}

function newRegionId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function splitCsvLine(line) {
  return String(line)
    .split(",")
    .map((part) => part.trim().replace(/^["']|["']$/g, ""));
}

function normalizeHeader(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

function validateRaDec(ra, dec, label) {
  if (Number.isNaN(ra) || ra < 0 || ra >= 360) {
    return `${label}: RA must be between 0 and 360.`;
  }
  if (Number.isNaN(dec) || dec < -90 || dec > 90) {
    return `${label}: Dec must be between -90 and 90.`;
  }
  return "";
}

function validateRadius(radiusArcmin, label) {
  if (Number.isNaN(radiusArcmin) || radiusArcmin <= 0) {
    return `${label}: radius must be a positive number (arcmin).`;
  }
  if (radiusArcmin > MAX_RADIUS_ARCMIN) {
    return `${label}: radius exceeds ${MAX_RADIUS_ARCMIN} arcmin.`;
  }
  return "";
}

/**
 * Parse bulk input:
 * - freeform RA/Dec pairs (form defaults for band/format/radius)
 * - CSV with header ra,dec and optional band,format,radius,color,rgb_bands
 */
function parseBulkCoordinates(text, defaults) {
  const source = String(text || "").trim();
  if (!source) {
    return { rows: [], errors: ["Paste or upload at least one RA Dec pair."] };
  }

  const lines = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));

  if (!lines.length) {
    return { rows: [], errors: ["Paste or upload at least one RA Dec pair."] };
  }

  const headerCells = splitCsvLine(lines[0]).map(normalizeHeader);
  const hasCsvHeader = headerCells.includes("ra") && headerCells.includes("dec");
  const rows = [];
  const errors = [];

  if (hasCsvHeader) {
    const idx = Object.fromEntries(headerCells.map((name, i) => [name, i]));
    lines.slice(1).forEach((line, offset) => {
      const label = `Row ${offset + 2}`;
      const cells = splitCsvLine(line);
      if (!cells.length || cells.every((c) => !c)) {
        return;
      }
      const ra = Number(cells[idx.ra]);
      const dec = Number(cells[idx.dec]);
      const coordError = validateRaDec(ra, dec, label);
      if (coordError) {
        errors.push(coordError);
        return;
      }

      const formatRaw = (cells[idx.format] || defaults.format || "fits").toLowerCase();
      const format = formatRaw === "png" ? "png" : "fits";
      const bandRaw = cells[idx.band] || defaults.band || "r";
      const band = ALL_BANDS.includes(bandRaw) ? bandRaw : defaults.band;
      const radiusRaw =
        idx.radius !== undefined && cells[idx.radius] !== ""
          ? Number(cells[idx.radius])
          : defaults.radiusArcmin;
      const radiusError = validateRadius(radiusRaw, label);
      if (radiusError) {
        errors.push(radiusError);
        return;
      }
      const colorRaw = (cells[idx.color] || "").toLowerCase();
      const color =
        format === "png" &&
        (colorRaw === "true" || colorRaw === "1" || colorRaw === "yes"
          ? true
          : colorRaw === "false" || colorRaw === "0" || colorRaw === "no"
            ? false
            : Boolean(defaults.color));
      const rgbBands = cells[idx.rgb_bands] || defaults.rgbBands || "gri";

      rows.push({
        id: newRegionId(),
        ra,
        dec,
        radiusArcmin: radiusRaw,
        format,
        band,
        color: format === "png" && color,
        rgbBands,
      });
    });
  } else {
    const pairRe = /([+-]?\d+(?:\.\d+)?)\s*[, ]\s*([+-]?\d+(?:\.\d+)?)/g;
    let match = pairRe.exec(source);
    let index = 0;
    while (match) {
      index += 1;
      const ra = Number(match[1]);
      const dec = Number(match[2]);
      const coordError = validateRaDec(ra, dec, `Pair ${index}`);
      if (coordError) {
        errors.push(coordError);
      } else {
        rows.push({
          id: newRegionId(),
          ra,
          dec,
          radiusArcmin: defaults.radiusArcmin,
          format: defaults.format,
          band: defaults.band,
          color: defaults.format === "png" && defaults.color,
          rgbBands: defaults.rgbBands,
        });
      }
      match = pairRe.exec(source);
    }
    if (!rows.length && !errors.length) {
      errors.push(
        "No coordinates found. Paste RA Dec pairs or CSV with header ra,dec[,band,format,radius].",
      );
    }
  }

  return { rows, errors };
}

export default function CutoutForm({
  authenticated,
  loginUrl,
  csrfToken,
  userGroups = [],
  skyviewerBaseHost = DEFAULT_SKYVIEWER_BASE_HOST,
}) {
  const groups = useMemo(() => new Set(userGroups), [userGroups]);
  const allSurveys = useMemo(() => buildSurveys(skyviewerBaseHost), [skyviewerBaseHost]);
  const surveys = useMemo(
    () =>
      allSurveys.filter((s) => {
        if (!s.requireGroup) {
          return true;
        }
        // API cutout: requireGroup; HiPS tiles no Sky Viewer podem exigir hipsRequireGroup.
        return groups.has(s.requireGroup) || (s.hipsRequireGroup && groups.has(s.hipsRequireGroup));
      }),
    [allSurveys, groups],
  );
  const initialSurvey = surveys.find((s) => s.id === "lsst_dp1") || surveys[0] || allSurveys[0];
  const [surveyId, setSurveyId] = useState(initialSurvey.id);
  const [ra, setRa] = useState(initialSurvey.defaultRa);
  const [dec, setDec] = useState(initialSurvey.defaultDec);
  const [radiusArcmin, setRadiusArcmin] = useState("1");
  const [format, setFormat] = useState("fits");
  const [band, setBand] = useState("r");
  const [color, setColor] = useState(false);
  const [rgbBands, setRgbBands] = useState("gri");
  const [regions, setRegions] = useState([]);
  const [coordPaste, setCoordPaste] = useState("");
  const [bulkPreview, setBulkPreview] = useState([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState(() => (typeof window !== "undefined" ? loadStoredJobs() : []));
  const [downloadingId, setDownloadingId] = useState(null);
  const [downloadingAll, setDownloadingAll] = useState(false);
  const jobsRef = useRef(jobs);

  useEffect(() => {
    jobsRef.current = jobs;
    saveStoredJobs(jobs);
  }, [jobs]);

  useEffect(() => {
    if (surveys.some((s) => s.id === surveyId)) {
      return;
    }
    const next = surveys[0];
    if (!next) {
      return;
    }
    setSurveyId(next.id);
    setRa(next.defaultRa);
    setDec(next.defaultDec);
  }, [surveys, surveyId]);

  const radiusValue = Number(radiusArcmin);
  const raValue = Number(ra);
  const decValue = Number(dec);
  const survey = surveys.find((s) => s.id === surveyId) || surveys[0];
  const surveyLabel = survey.label;
  const bands = survey.bands;
  const rgbPresets = survey.rgbPresets;
  const hasSkyMap = Boolean(survey?.hips?.url);

  const validationError = useMemo(() => {
    if (Number.isNaN(raValue) || raValue < 0 || raValue >= 360) {
      return "RA must be a number between 0 and 360 degrees.";
    }
    if (Number.isNaN(decValue) || decValue < -90 || decValue > 90) {
      return "Dec must be a number between -90 and 90 degrees.";
    }
    if (Number.isNaN(radiusValue) || radiusValue <= 0) {
      return "Radius must be a positive number (arcmin).";
    }
    if (radiusValue > MAX_RADIUS_ARCMIN) {
      return `Radius ${radiusValue}' exceeds the maximum allowed of ${MAX_RADIUS_ARCMIN} arcmin.`;
    }
    return "";
  }, [raValue, decValue, radiusValue]);

  const handleCenterChange = useCallback((nextRa, nextDec) => {
    setRa(Number(nextRa).toFixed(6));
    setDec(Number(nextDec).toFixed(6));
  }, []);

  const handleRadiusChange = useCallback((nextRadius) => {
    setRadiusArcmin(String(nextRadius));
  }, []);

  const currentRegion = () => ({
    id: newRegionId(),
    surveyId,
    surveyLabel,
    ra: raValue,
    dec: decValue,
    radiusArcmin: radiusValue,
    format,
    band,
    color: format === "png" && color,
    rgbBands,
    label: makeJobLabel({
      surveyLabel,
      ra: raValue,
      dec: decValue,
      radiusArcmin: radiusValue,
      format,
      band,
      color: format === "png" && color,
      rgbBands,
    }),
  });

  const regionFromFields = ({
    ra: raDeg,
    dec: decDeg,
    radiusArcmin: radiusDeg,
    format: fmt,
    band: bandValue,
    color: colorValue,
    rgbBands: rgbValue,
  }) => {
    const useColor = fmt === "png" && Boolean(colorValue);
    return {
      id: newRegionId(),
      surveyId,
      surveyLabel,
      ra: raDeg,
      dec: decDeg,
      radiusArcmin: radiusDeg,
      format: fmt,
      band: bandValue,
      color: useColor,
      rgbBands: rgbValue,
      label: makeJobLabel({
        surveyLabel,
        ra: raDeg,
        dec: decDeg,
        radiusArcmin: radiusDeg,
        format: fmt,
        band: bandValue,
        color: useColor,
        rgbBands: rgbValue,
      }),
    };
  };

  const addRegion = () => {
    setError("");
    if (validationError) {
      setError(validationError);
      return;
    }
    const region = currentRegion();
    setRegions((prev) => [...prev, region]);
    setStatus(`Added region (${regions.length + 1} in queue list).`);
  };

  const parseIntoPreview = (text, { clearPaste = false } = {}) => {
    setError("");
    setStatus("");
    if (Number.isNaN(radiusValue) || radiusValue <= 0 || radiusValue > MAX_RADIUS_ARCMIN) {
      setError(
        Number.isNaN(radiusValue) || radiusValue <= 0
          ? "Radius must be a positive number (arcmin)."
          : `Radius ${radiusValue}' exceeds the maximum allowed of ${MAX_RADIUS_ARCMIN} arcmin.`,
      );
      return;
    }

    const { rows, errors } = parseBulkCoordinates(text, {
      radiusArcmin: radiusValue,
      format,
      band,
      color,
      rgbBands,
    });
    if (!rows.length) {
      setBulkPreview([]);
      setError(errors.join(" ") || "No valid coordinates found.");
      return;
    }

    setBulkPreview(rows);
    setBulkOpen(true);
    if (clearPaste) {
      setCoordPaste("");
    }
    const skipped = errors.length ? ` Skipped ${errors.length} invalid row(s).` : "";
    setStatus(`Preview ready: ${rows.length} row(s). Review and add to queue.${skipped}`);
    if (errors.length) {
      setError(errors.slice(0, 3).join(" "));
    }
  };

  const handleCoordFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    try {
      const text = await file.text();
      setCoordPaste(text);
      parseIntoPreview(text);
    } catch (err) {
      setError(err.message || "Failed to read coordinate file.");
    }
  };

  const updatePreviewRow = (id, patch) => {
    setBulkPreview((prev) =>
      prev.map((row) => {
        if (row.id !== id) {
          return row;
        }
        const next = { ...row, ...patch };
        if (Object.prototype.hasOwnProperty.call(patch, "format")) {
          if (next.format === "fits") {
            next.color = false;
          } else if (next.format === "png") {
            // PNG in preview defaults to RGB composite (same mental model as the form).
            next.color = true;
            next.rgbBands = next.rgbBands || rgbBands || "gri";
          }
        }
        if (next.format === "fits") {
          next.color = false;
        }
        return next;
      }),
    );
  };

  const removePreviewRow = (id) => {
    setBulkPreview((prev) => prev.filter((row) => row.id !== id));
  };

  const clearBulk = () => {
    setCoordPaste("");
    setBulkPreview([]);
    setError("");
    setStatus("Cleared bulk coordinates.");
  };

  const commitPreviewToQueue = () => {
    setError("");
    if (!bulkPreview.length) {
      setError("Parse coordinates into the preview first.");
      return;
    }
    for (const row of bulkPreview) {
      const coordError = validateRaDec(row.ra, row.dec, "Preview");
      const radiusError = validateRadius(Number(row.radiusArcmin), "Preview");
      if (coordError || radiusError) {
        setError(coordError || radiusError);
        return;
      }
    }
    const added = bulkPreview.map((row) =>
      regionFromFields({
        ra: Number(row.ra),
        dec: Number(row.dec),
        radiusArcmin: Number(row.radiusArcmin),
        format: row.format,
        band: row.band,
        color: row.color,
        rgbBands: row.rgbBands,
      }),
    );
    setRegions((prev) => [...prev, ...added]);
    setBulkPreview([]);
    setStatus(`Added ${added.length} region(s) to the queue.`);
  };

  const removeRegion = (id) => {
    setRegions((prev) => prev.filter((region) => region.id !== id));
  };

  const refreshJob = async (jobId) => {
    const detailResponse = await fetch(`/api/async/${jobId}`, {
      method: "GET",
      credentials: "same-origin",
    });
    if (detailResponse.status === 404) {
      return {
        phase: "ERROR",
        downloadUrl: null,
        errorMessage: "Job not found (expired or deleted).",
      };
    }
    if (!detailResponse.ok) {
      const text = await detailResponse.text();
      throw new Error(text || `Failed to poll job (${detailResponse.status})`);
    }
    const detail = await detailResponse.json();
    const phase = String(detail.phase || "").toUpperCase();
    const result = detail.results?.[0];
    const downloadUrl = result?.download_url || null;
    const ready = Boolean(downloadUrl);
    return {
      phase: ready ? "COMPLETED" : phase,
      downloadUrl,
      errorMessage: detail.tasks?.[0]?.error_message || null,
      format: result?.mime_type?.includes("png")
        ? "png"
        : jobsRef.current.find((j) => j.jobId === jobId)?.format || "fits",
    };
  };

  const openJobKey = jobs
    .filter((job) => isOpenPhase(job.phase))
    .map((job) => job.jobId)
    .join(",");

  useEffect(() => {
    if (!openJobKey) {
      return undefined;
    }

    let cancelled = false;

    const poll = async () => {
      const openJobs = jobsRef.current.filter((job) => isOpenPhase(job.phase));
      if (!openJobs.length) {
        return;
      }
      const updates = await Promise.all(
        openJobs.map(async (job) => {
          try {
            const refreshed = await refreshJob(job.jobId);
            return { jobId: job.jobId, ...refreshed };
          } catch (err) {
            return {
              jobId: job.jobId,
              phase: job.phase,
              errorMessage: err.message || "Polling failed",
            };
          }
        }),
      );
      if (cancelled) {
        return;
      }
      setJobs((prev) =>
        prev.map((job) => {
          const update = updates.find((item) => item.jobId === job.jobId);
          return update ? { ...job, ...update } : job;
        }),
      );
    };

    poll();
    const timer = setInterval(poll, ASYNC_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [openJobKey]);

  const enqueueRegion = async (region) => {
    const createResponse = await fetch("/api/async", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": csrfToken,
      },
      body: buildBody(regionParams(region)),
    });

    if (!createResponse.ok && createResponse.status !== 303) {
      const text = await createResponse.text();
      throw new Error(text || `Async request failed (${createResponse.status})`);
    }

    const created = await createResponse.json();
    const jobId = created.job_id;
    if (!jobId) {
      throw new Error("Async job id missing from response.");
    }

    return {
      jobId,
      label: region.label,
      phase: String(created.phase || "QUEUED").toUpperCase(),
      format: region.format,
      downloadUrl: null,
      errorMessage: null,
      createdAt: new Date().toISOString(),
    };
  };

  const downloadSyncRegion = async (region) => {
    const query = buildBody(regionParams(region, { includePhase: false }));
    const response = await fetch(`/api/sync?${query.toString()}`, {
      method: "GET",
      credentials: "same-origin",
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Sync download failed (${response.status})`);
    }
    const blob = await response.blob();
    const filename = parseFilename(
      response.headers.get("Content-Disposition"),
      `cutout.${region.format === "png" ? "png" : "fits"}`,
    );
    triggerDownload(blob, filename);
  };

  const submitCurrent = async () => {
    setError("");
    setStatus("");
    if (validationError) {
      setError(validationError);
      return;
    }
    if (!csrfToken && radiusValue > SYNC_RADIUS_LIMIT_ARCMIN) {
      setError("Missing CSRF token. Reload the page and try again.");
      return;
    }

    const region = currentRegion();
    setLoading(true);
    try {
      if (radiusValue > SYNC_RADIUS_LIMIT_ARCMIN) {
        const created = await enqueueRegion(region);
        setJobs((prev) => [created, ...prev]);
        setStatus("Job queued. Track download in the tray — safe to leave this page.");
      } else {
        await downloadSyncRegion(region);
        setStatus("Cutout downloaded.");
      }
    } catch (err) {
      setError(err.message || "Failed to request cutout.");
    } finally {
      setLoading(false);
    }
  };

  const queueRegions = async () => {
    setError("");
    setStatus("");
    if (!csrfToken) {
      setError("Missing CSRF token. Reload the page and try again.");
      return;
    }
    if (!regions.length) {
      setError("Add at least one region before queueing jobs.");
      return;
    }

    setLoading(true);
    try {
      const createdJobs = [];
      for (const region of regions) {
        // Sequential enqueue keeps API/worker pressure predictable (RAM-safe serial cutouts).
        // eslint-disable-next-line no-await-in-loop
        createdJobs.push(await enqueueRegion(region));
      }
      setJobs((prev) => [...createdJobs, ...prev]);
      setRegions([]);
      setStatus(
        `${createdJobs.length} job(s) queued. Track downloads in the tray — safe to leave this page.`,
      );
    } catch (err) {
      setError(err.message || "Failed to queue async jobs.");
    } finally {
      setLoading(false);
    }
  };

  const handleDismissJob = (jobId) => {
    setJobs((prev) => prev.filter((job) => job.jobId !== jobId));
  };

  const handleClearJobs = () => {
    setJobs([]);
    setStatus("Cleared async jobs from this browser.");
    setError("");
  };

  const fetchJobFile = async (job) => {
    if (!job.downloadUrl) {
      throw new Error(`Job #${job.jobId} has no download URL.`);
    }
    const fileResponse = await fetch(job.downloadUrl, {
      method: "GET",
      credentials: "same-origin",
    });
    if (!fileResponse.ok) {
      const text = await fileResponse.text();
      throw new Error(text || `Download failed (${fileResponse.status})`);
    }
    const blob = await fileResponse.blob();
    const filename = parseFilename(
      fileResponse.headers.get("Content-Disposition"),
      `cutout_job_${job.jobId}.${job.format === "png" ? "png" : "fits"}`,
    );
    return { blob, filename };
  };

  const handleDownloadJob = async (job) => {
    setDownloadingId(job.jobId);
    setError("");
    try {
      const { blob, filename } = await fetchJobFile(job);
      triggerDownload(blob, filename);
    } catch (err) {
      setError(err.message || "Download failed.");
    } finally {
      setDownloadingId(null);
    }
  };

  const uniqueZipEntryName = (usedNames, filename, jobId) => {
    if (!usedNames.has(filename)) {
      usedNames.add(filename);
      return filename;
    }
    const dot = filename.lastIndexOf(".");
    const stem = dot > 0 ? filename.slice(0, dot) : filename;
    const ext = dot > 0 ? filename.slice(dot) : "";
    const candidate = `${stem}_job${jobId}${ext}`;
    usedNames.add(candidate);
    return candidate;
  };

  const handleDownloadAllCompleted = async () => {
    const completed = jobsRef.current.filter(
      (job) => String(job.phase || "").toUpperCase() === "COMPLETED" && job.downloadUrl,
    );
    if (!completed.length) {
      return;
    }
    setDownloadingAll(true);
    setError("");
    setStatus("");
    let packed = 0;
    try {
      const zip = new JSZip();
      const usedNames = new Set();
      for (const job of completed) {
        setDownloadingId(job.jobId);
        // eslint-disable-next-line no-await-in-loop
        const { blob, filename } = await fetchJobFile(job);
        zip.file(uniqueZipEntryName(usedNames, filename, job.jobId), blob);
        packed += 1;
      }
      const zipBlob = await zip.generateAsync({ type: "blob" });
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      triggerDownload(zipBlob, `cutout_jobs_${stamp}.zip`);
      setStatus(`Downloaded ZIP with ${packed} completed job(s).`);
    } catch (err) {
      setError(
        packed
          ? `${err.message || "ZIP download failed."} (${packed} file(s) fetched before the error.)`
          : err.message || "ZIP download failed.",
      );
    } finally {
      setDownloadingId(null);
      setDownloadingAll(false);
    }
  };

  const cardSx = {
    width: "100%",
    minHeight: CARD_MIN_HEIGHT,
    height: "100%",
    display: "flex",
    flexDirection: "column",
  };

  return (
    <Box sx={{ py: 3 }}>
      <Typography variant="h5" sx={{ mb: 0.5, fontWeight: 500 }}>
        Image Cutout Service
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Explore LIneA sky survey catalogs on the map, then extract the region you need — instant cutouts up
        to {SYNC_RADIUS_LIMIT_ARCMIN}&apos;, or queued jobs for larger radii and multiple targets.
      </Typography>

      <Grid container spacing={3} alignItems="stretch">
        <Grid size={{ xs: 12, md: hasSkyMap ? 5 : 12 }} sx={{ display: "flex" }}>
          <Card elevation={2} sx={cardSx}>
            <CardContent sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
              <Stack spacing={2} sx={{ flex: 1 }}>
                <FormControl fullWidth size="small">
                  <InputLabel id="survey-label">Survey</InputLabel>
                  <Select
                    labelId="survey-label"
                    label="Survey"
                    value={surveyId}
                    onChange={(e) => {
                      const next = surveys.find((s) => s.id === e.target.value) || surveys[0];
                      setSurveyId(next.id);
                      setRa(next.defaultRa);
                      setDec(next.defaultDec);
                      if (!next.bands.includes(band)) {
                        setBand(next.bands.includes("g") ? "g" : next.bands[0]);
                      }
                      if (!next.rgbPresets.includes(rgbBands)) {
                        setRgbBands(next.rgbPresets[0]);
                      }
                    }}
                  >
                    {surveys.map((item) => (
                      <MenuItem key={item.id} value={item.id}>
                        {item.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                  <TextField
                    label="RA (deg)"
                    value={ra}
                    onChange={(e) => setRa(e.target.value)}
                    fullWidth
                    size="small"
                    inputProps={{ inputMode: "decimal" }}
                  />
                  <TextField
                    label="Dec (deg)"
                    value={dec}
                    onChange={(e) => setDec(e.target.value)}
                    fullWidth
                    size="small"
                    inputProps={{ inputMode: "decimal" }}
                  />
                </Stack>

                <TextField
                  label="Radius (arcmin)"
                  value={radiusArcmin}
                  onChange={(e) => setRadiusArcmin(e.target.value)}
                  fullWidth
                  size="small"
                  helperText={`Max ${MAX_RADIUS_ARCMIN}' for cutout · Aladin can zoom out freely`}
                  inputProps={{ inputMode: "decimal" }}
                />

                <FormControl>
                  <FormLabel id="format-label">Format</FormLabel>
                  <RadioGroup
                    row
                    aria-labelledby="format-label"
                    value={format}
                    onChange={(e) => {
                      const next = e.target.value;
                      setFormat(next);
                      if (next === "fits") {
                        setColor(false);
                      }
                    }}
                  >
                    <FormControlLabel value="fits" control={<Radio size="small" />} label="FITS" />
                    <FormControlLabel value="png" control={<Radio size="small" />} label="PNG" />
                  </RadioGroup>
                </FormControl>

                {format === "png" && (
                  <FormControlLabel
                    control={
                      <Switch
                        checked={color}
                        onChange={(e) => setColor(e.target.checked)}
                        size="small"
                      />
                    }
                    label="RGB color composite"
                  />
                )}

                {format === "png" && color ? (
                  <FormControl fullWidth size="small">
                    <InputLabel id="rgb-bands-label">RGB bands</InputLabel>
                    <Select
                      labelId="rgb-bands-label"
                      label="RGB bands"
                      value={rgbBands}
                      onChange={(e) => setRgbBands(e.target.value)}
                    >
                      {rgbPresets.map((preset) => (
                        <MenuItem key={preset} value={preset}>
                          {preset}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : (
                  <FormControl fullWidth size="small">
                    <InputLabel id="band-label">Band</InputLabel>
                    <Select
                      labelId="band-label"
                      label="Band"
                      value={band}
                      onChange={(e) => setBand(e.target.value)}
                    >
                      {bands.map((b) => (
                        <MenuItem key={b} value={b}>
                          {b}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}

                {(error || validationError) && (
                  <Alert severity="error">{error || validationError}</Alert>
                )}
                {status && !error && <Alert severity="success">{status}</Alert>}

                <Divider />

                <Typography variant="subtitle2">
                  Regions to queue ({regions.length})
                </Typography>
                {regions.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    Empty list — use Download for the current fields (≤{SYNC_RADIUS_LIMIT_ARCMIN}
                    &apos;) or add regions to queue several jobs.
                  </Typography>
                ) : (
                  <List dense sx={{ maxHeight: 160, overflow: "auto", bgcolor: "action.hover", borderRadius: 1 }}>
                    {regions.map((region) => (
                      <ListItem
                        key={region.id}
                        secondaryAction={
                          <IconButton
                            edge="end"
                            aria-label="remove region"
                            onClick={() => removeRegion(region.id)}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        }
                      >
                        <ListItemText
                          primaryTypographyProps={{ variant: "body2", noWrap: true }}
                          primary={region.label}
                        />
                      </ListItem>
                    ))}
                  </List>
                )}

                <Box sx={{ flexGrow: 1 }} />

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                  <Button
                    variant="outlined"
                    startIcon={<AddIcon />}
                    disabled={Boolean(validationError) || loading}
                    onClick={addRegion}
                    fullWidth
                  >
                    Add region
                  </Button>
                  {regions.length > 0 ? (
                    <Button
                      variant="contained"
                      startIcon={
                        loading ? (
                          <CircularProgress size={16} color="inherit" />
                        ) : (
                          <PlaylistAddCheckIcon />
                        )
                      }
                      disabled={loading || !csrfToken}
                      onClick={queueRegions}
                      fullWidth
                    >
                      Queue jobs
                    </Button>
                  ) : (
                    <Button
                      variant="contained"
                      startIcon={
                        loading ? (
                          <CircularProgress size={16} color="inherit" />
                        ) : radiusValue > SYNC_RADIUS_LIMIT_ARCMIN ? (
                          <PlaylistAddCheckIcon />
                        ) : (
                          <DownloadIcon />
                        )
                      }
                      disabled={
                        loading ||
                        Boolean(validationError) ||
                        (radiusValue > SYNC_RADIUS_LIMIT_ARCMIN && !csrfToken)
                      }
                      onClick={submitCurrent}
                      fullWidth
                    >
                      {radiusValue > SYNC_RADIUS_LIMIT_ARCMIN ? "Queue job" : "Download"}
                    </Button>
                  )}
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {hasSkyMap ? (
          <Grid size={{ xs: 12, md: 7 }} sx={{ display: "flex" }}>
            <Card elevation={2} sx={{ ...cardSx, p: 2 }}>
              <AladinViewer
                key={survey.hips.url}
                hips={survey.hips}
                ra={raValue}
                dec={decValue}
                radiusArcmin={Number.isFinite(radiusValue) ? Math.min(radiusValue, MAX_RADIUS_ARCMIN) : 1}
                onCenterChange={handleCenterChange}
                onRadiusChange={handleRadiusChange}
              />
            </Card>
          </Grid>
        ) : null}
      </Grid>

      <Accordion
        disableGutters
        elevation={0}
        expanded={bulkOpen}
        onChange={(_, expanded) => setBulkOpen(expanded)}
        sx={{ mt: 3, border: "1px solid", borderColor: "divider", borderRadius: 1, width: "100%" }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2">
            Bulk Coordinates
            {bulkPreview.length ? ` · preview ${bulkPreview.length}` : ""}
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ width: "100%", overflow: "hidden" }}>
          <Stack spacing={1.5} sx={{ width: "100%" }}>
            <Typography variant="body2" color="text.secondary">
              Paste RA/Dec pairs (uses form defaults) or CSV with header <code>ra,dec</code> and
              optional <code>band,format,radius,color,rgb_bands</code>.
            </Typography>
            {!bulkPreview.length && (
              <TextField
                label="Paste list or CSV"
                value={coordPaste}
                onChange={(e) => setCoordPaste(e.target.value)}
                fullWidth
                multiline
                minRows={2}
                size="small"
                placeholder={"0.5 +2.15, 1.0 -3.2\nor\nra,dec,band,format\n0.5,2.15,g,fits"}
              />
            )}
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} flexWrap="wrap" useFlexGap>
              <Button
                variant="outlined"
                startIcon={<UploadFileIcon />}
                component="label"
                disabled={loading}
                size="small"
              >
                Upload file
                <input
                  hidden
                  type="file"
                  accept=".txt,.csv,.dat,.list,text/plain,text/csv"
                  onChange={handleCoordFile}
                />
              </Button>
              {!bulkPreview.length && (
                <Button
                  variant="outlined"
                  startIcon={<AddIcon />}
                  disabled={loading || !coordPaste.trim()}
                  onClick={() => parseIntoPreview(coordPaste)}
                  size="small"
                >
                  Preview
                </Button>
              )}
              <Button
                variant="contained"
                disabled={loading || !bulkPreview.length}
                onClick={commitPreviewToQueue}
                size="small"
              >
                Add to queue
              </Button>
              <Button
                variant="text"
                color="inherit"
                startIcon={<ClearIcon />}
                disabled={loading || (!coordPaste.trim() && !bulkPreview.length)}
                onClick={clearBulk}
                size="small"
              >
                Clear
              </Button>
            </Stack>

            {bulkPreview.length > 0 && (
              <TableContainer
                sx={{
                  width: "100%",
                  maxHeight: { xs: 280, md: 360 },
                  overflowX: "auto",
                  overflowY: "auto",
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Table
                  size="small"
                  stickyHeader
                  sx={{
                    width: "100%",
                    minWidth: 640,
                    tableLayout: "auto",
                  }}
                >
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ minWidth: 110 }}>RA</TableCell>
                      <TableCell sx={{ minWidth: 110 }}>Dec</TableCell>
                      <TableCell sx={{ minWidth: 96 }}>Band / RGB</TableCell>
                      <TableCell sx={{ minWidth: 96 }}>Format</TableCell>
                      <TableCell sx={{ minWidth: 100 }}>Radius&apos;</TableCell>
                      <TableCell sx={{ width: 48 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {bulkPreview.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {Number(row.ra).toFixed(6)}
                        </TableCell>
                        <TableCell sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {Number(row.dec).toFixed(6)}
                        </TableCell>
                        <TableCell>
                          {row.format === "png" && row.color ? (
                            <Select
                              size="small"
                              value={row.rgbBands || "gri"}
                              onChange={(e) =>
                                updatePreviewRow(row.id, { rgbBands: e.target.value, color: true })
                              }
                              fullWidth
                            >
                              {rgbPresets.map((preset) => (
                                <MenuItem key={preset} value={preset}>
                                  {preset}
                                </MenuItem>
                              ))}
                            </Select>
                          ) : (
                            <Select
                              size="small"
                              value={row.band}
                              onChange={(e) => updatePreviewRow(row.id, { band: e.target.value })}
                              fullWidth
                            >
                              {bands.map((b) => (
                                <MenuItem key={b} value={b}>
                                  {b}
                                </MenuItem>
                              ))}
                            </Select>
                          )}
                        </TableCell>
                        <TableCell>
                          <Select
                            size="small"
                            value={row.format}
                            onChange={(e) => updatePreviewRow(row.id, { format: e.target.value })}
                            fullWidth
                          >
                            <MenuItem value="fits">fits</MenuItem>
                            <MenuItem value="png">png</MenuItem>
                          </Select>
                        </TableCell>
                        <TableCell>
                          <TextField
                            size="small"
                            fullWidth
                            value={row.radiusArcmin}
                            onChange={(e) =>
                              updatePreviewRow(row.id, { radiusArcmin: e.target.value })
                            }
                            inputProps={{ inputMode: "decimal" }}
                          />
                        </TableCell>
                        <TableCell>
                          <IconButton
                            size="small"
                            aria-label="remove preview row"
                            onClick={() => removePreviewRow(row.id)}
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Stack>
        </AccordionDetails>
      </Accordion>

      <JobTray
        jobs={jobs}
        onDismiss={handleDismissJob}
        onDownload={handleDownloadJob}
        onDownloadAll={handleDownloadAllCompleted}
        onClearAll={handleClearJobs}
        downloadingId={downloadingId}
        downloadingAll={downloadingAll}
      />
    </Box>
  );
}
