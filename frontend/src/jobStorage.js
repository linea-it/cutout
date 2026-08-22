const STORAGE_KEY = "cutout.asyncJobs.v1";
const MAX_STORED_JOBS = 40;

export function loadStoredJobs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((job) => job && Number.isFinite(Number(job.jobId)));
  } catch {
    return [];
  }
}

export function saveStoredJobs(jobs) {
  try {
    const trimmed = jobs.slice(0, MAX_STORED_JOBS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Quota / private mode — tray still works for the current session.
  }
}

export function makeJobLabel({ surveyLabel, ra, dec, radiusArcmin, format, band, color, rgbBands }) {
  const bandPart = color ? `RGB ${rgbBands}` : `band ${band}`;
  return `${surveyLabel} · RA ${ra} Dec ${dec} · ${radiusArcmin}' · ${String(format).toUpperCase()} · ${bandPart}`;
}
