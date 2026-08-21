import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import DownloadIcon from "@mui/icons-material/Download";
import FolderZipIcon from "@mui/icons-material/FolderZip";

function phaseTone(phase) {
  const value = String(phase || "").toUpperCase();
  if (value === "COMPLETED") {
    return "success";
  }
  if (value === "ERROR" || value === "ABORTED") {
    return "error";
  }
  if (value === "EXECUTING" || value === "QUEUED" || value === "PENDING") {
    return "info";
  }
  return "default";
}

function isCompletedDownloadable(job) {
  return String(job.phase || "").toUpperCase() === "COMPLETED" && Boolean(job.downloadUrl);
}

export default function JobTray({
  jobs,
  onDismiss,
  onDownload,
  onDownloadAll,
  onClearAll,
  downloadingId,
  downloadingAll,
}) {
  if (!jobs.length) {
    return null;
  }

  const completedCount = jobs.filter(isCompletedDownloadable).length;

  return (
    <Card elevation={2} sx={{ mt: 3 }}>
      <CardContent>
        <Stack spacing={1.5}>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={1}
            alignItems={{ sm: "flex-start" }}
            justifyContent="space-between"
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="h6" sx={{ fontWeight: 500 }}>
                Queued Jobs
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Saved in <em>this</em> browser. You can close the tab and come back to download.
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} flexShrink={0}>
              <Button
                size="small"
                variant="outlined"
                startIcon={
                  downloadingAll ? <CircularProgress size={14} /> : <FolderZipIcon />
                }
                disabled={!completedCount || downloadingAll || Boolean(downloadingId)}
                onClick={onDownloadAll}
              >
                Download ZIP ({completedCount})
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="inherit"
                startIcon={<DeleteSweepIcon />}
                disabled={downloadingAll || Boolean(downloadingId)}
                onClick={onClearAll}
              >
                Clear jobs
              </Button>
            </Stack>
          </Stack>

          <Alert severity="info" sx={{ py: 0.5 }}>
            Jobs keep running on the server if you leave. This tray restores from localStorage.
          </Alert>

          <Stack spacing={1}>
            {jobs.map((job) => {
              const phase = String(job.phase || "QUEUED").toUpperCase();
              const isTerminal = phase === "COMPLETED" || phase === "ERROR" || phase === "ABORTED";
              const canDownload = isCompletedDownloadable(job);
              const isDownloading = downloadingId === job.jobId;

              return (
                <Box
                  key={job.jobId}
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    px: 1.5,
                    py: 1,
                  }}
                >
                  <Stack
                    direction={{ xs: "column", sm: "row" }}
                    spacing={1}
                    alignItems={{ sm: "center" }}
                    justifyContent="space-between"
                  >
                    <Stack spacing={0.25} sx={{ minWidth: 0, flex: 1 }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" fontWeight={600}>
                          Job #{job.jobId}
                        </Typography>
                        <Chip size="small" label={phase} color={phaseTone(phase)} />
                        {!isTerminal && <CircularProgress size={14} />}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" noWrap title={job.label}>
                        {job.label}
                      </Typography>
                      {job.errorMessage && (
                        <Typography variant="caption" color="error">
                          {job.errorMessage}
                        </Typography>
                      )}
                    </Stack>

                    <Stack direction="row" spacing={1} alignItems="center">
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={
                          isDownloading ? <CircularProgress size={14} /> : <DownloadIcon />
                        }
                        disabled={!canDownload || isDownloading || downloadingAll}
                        onClick={() => onDownload(job)}
                      >
                        Download
                      </Button>
                      <IconButton
                        size="small"
                        aria-label={`Dismiss job ${job.jobId}`}
                        disabled={downloadingAll}
                        onClick={() => onDismiss(job.jobId)}
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
