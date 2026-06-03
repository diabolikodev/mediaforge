const elements = {
  url: document.querySelector("#url"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  downloadBtn: document.querySelector("#downloadBtn"),
  saveSettingsBtn: document.querySelector("#saveSettingsBtn"),
  clearBtn: document.querySelector("#clearBtn"),
  openDownloadsBtn: document.querySelector("#openDownloadsBtn"),
  manageQueueBtn: document.querySelector("#manageQueueBtn"),
  queueMenu: document.querySelector("#queueMenuLayer"),
  pauseQueueBtn: document.querySelector("#pauseQueueBtn"),
  resumeQueueBtn: document.querySelector("#resumeQueueBtn"),
  cancelQueuedBtn: document.querySelector("#cancelQueuedBtn"),
  cancelActiveBtn: document.querySelector("#cancelActiveBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  clearCompletedBtn: document.querySelector("#clearCompletedBtn"),
  clearVisibleBtn: document.querySelector("#clearVisibleBtn"),
  clearAllBtn: document.querySelector("#clearAllBtn"),
  notice: document.querySelector("#notice"),
  jobsNotice: document.querySelector("#jobsNotice"),
  preview: document.querySelector("#preview"),
  thumb: document.querySelector("#thumb"),
  title: document.querySelector("#title"),
  meta: document.querySelector("#meta"),
  desc: document.querySelector("#desc"),
  mode: document.querySelector("#mode"),
  quality: document.querySelector("#quality"),
  videoQuality: document.querySelector("#videoQuality"),
  audioQualityWrap: document.querySelector("#audioQualityWrap"),
  videoQualityWrap: document.querySelector("#videoQualityWrap"),
  embedMetadata: document.querySelector("#embedMetadata"),
  embedCover: document.querySelector("#embedCover"),
  saveThumb: document.querySelector("#saveThumb"),
  saveDescription: document.querySelector("#saveDescription"),
  saveJson: document.querySelector("#saveJson"),
  expandPlaylists: document.querySelector("#expandPlaylists"),
  playlistLimit: document.querySelector("#playlistLimit"),
  jobsList: document.querySelector("#jobsList"),
  jobStats: document.querySelector("#jobStats"),
};

const activeStates = ["queued", "analyzing", "downloading", "converting", "tagging"];
const runningStates = ["analyzing", "downloading", "converting", "tagging"];
let activePoll = null;
let currentJobFilter = "all";

function showNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.dataset.type = type;
  elements.notice.classList.remove("hidden");
}

function hideNotice() {
  elements.notice.classList.add("hidden");
}

function showJobsNotice(message, type = "info") {
  elements.jobsNotice.textContent = message;
  elements.jobsNotice.dataset.type = type;
  elements.jobsNotice.classList.remove("hidden");
}

function closeQueueMenu() {
  elements.queueMenu.classList.add("hidden");
  elements.manageQueueBtn.classList.remove("active");
}

function positionQueueMenu() {
  const rect = elements.manageQueueBtn.getBoundingClientRect();
  const width = 250;
  const gap = 10;
  const left = Math.max(16, Math.min(window.innerWidth - width - 16, rect.right - width));
  const top = rect.bottom + gap;

  elements.queueMenu.style.left = `${left}px`;
  elements.queueMenu.style.top = `${top}px`;
}

function toggleQueueMenu() {
  const isHidden = elements.queueMenu.classList.contains("hidden");

  if (isHidden) {
    positionQueueMenu();
    elements.queueMenu.classList.remove("hidden");
    elements.manageQueueBtn.classList.add("active");
  } else {
    closeQueueMenu();
  }
}

function trimText(text, max = 180) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getUrls() {
  return elements.url.value
    .split(/\r?\n|,/)
    .map((url) => url.trim())
    .filter(Boolean);
}

function getFirstUrl() {
  return getUrls()[0] || "";
}

function updateModeVisibility() {
  const mode = elements.mode.value;

  if (mode === "video_mp4") {
    elements.audioQualityWrap.classList.add("hidden");
    elements.videoQualityWrap.classList.remove("hidden");
  } else if (mode === "audio_mp3") {
    elements.audioQualityWrap.classList.remove("hidden");
    elements.videoQualityWrap.classList.add("hidden");
  } else {
    elements.audioQualityWrap.classList.add("hidden");
    elements.videoQualityWrap.classList.add("hidden");
  }
}

function buildPayload() {
  const urls = getUrls();

  return {
    url: urls[0] || "",
    urls,
    mode: elements.mode.value,
    quality: elements.quality.value,
    video_quality: elements.videoQuality.value,
    embed_metadata: elements.embedMetadata.checked,
    embed_cover: elements.embedCover.checked,
    save_thumbnail: elements.saveThumb.checked,
    save_description: elements.saveDescription.checked,
    save_metadata_json: elements.saveJson.checked,
    expand_playlists: elements.expandPlaylists.checked,
    playlist_limit: elements.playlistLimit.value,
  };
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

async function sendEmptyRequest(url, method) {
  const response = await fetch(url, { method });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }

  return data;
}

async function loadSettings() {
  try {
    const settings = await requestJson("/api/settings");
    elements.mode.value = settings.default_mode || "audio_mp3";
    elements.quality.value = settings.default_audio_quality || "320k";
    elements.videoQuality.value = settings.default_video_quality || "best";
    elements.embedMetadata.checked = Boolean(settings.embed_metadata);
    elements.embedCover.checked = Boolean(settings.embed_cover);
    elements.saveThumb.checked = Boolean(settings.save_thumbnail);
    elements.saveDescription.checked = Boolean(settings.save_description);
    elements.saveJson.checked = Boolean(settings.save_metadata_json);
    elements.expandPlaylists.checked = Boolean(settings.expand_playlists);
    elements.playlistLimit.value = settings.playlist_limit || "50";
    updateModeVisibility();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function saveSettings() {
  try {
    await requestJson("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        default_mode: elements.mode.value,
        default_audio_quality: elements.quality.value,
        default_video_quality: elements.videoQuality.value,
        embed_metadata: elements.embedMetadata.checked,
        embed_cover: elements.embedCover.checked,
        save_thumbnail: elements.saveThumb.checked,
        save_description: elements.saveDescription.checked,
        save_metadata_json: elements.saveJson.checked,
        expand_playlists: elements.expandPlaylists.checked,
        playlist_limit: elements.playlistLimit.value,
      }),
    });

    showNotice("Default settings saved.", "success");
  } catch (error) {
    showNotice(error.message, "error");
  }
}

function applyPreset(name) {
  const presets = {
    audio_best: {
      mode: "audio_m4a",
      quality: "320k",
      videoQuality: "best",
      embedMetadata: true,
      embedCover: true,
      saveThumb: true,
      saveDescription: false,
      saveJson: true,
    },
    mp3_320: {
      mode: "audio_mp3",
      quality: "320k",
      videoQuality: "best",
      embedMetadata: true,
      embedCover: true,
      saveThumb: true,
      saveDescription: false,
      saveJson: true,
    },
    video_1080: {
      mode: "video_mp4",
      quality: "320k",
      videoQuality: "1080p",
      embedMetadata: true,
      embedCover: false,
      saveThumb: true,
      saveDescription: false,
      saveJson: true,
    },
    video_720: {
      mode: "video_mp4",
      quality: "320k",
      videoQuality: "720p",
      embedMetadata: true,
      embedCover: false,
      saveThumb: true,
      saveDescription: false,
      saveJson: true,
    },
    original: {
      mode: "best",
      quality: "320k",
      videoQuality: "best",
      embedMetadata: false,
      embedCover: false,
      saveThumb: true,
      saveDescription: false,
      saveJson: true,
    },
  };

  const preset = presets[name];

  if (!preset) {
    return;
  }

  elements.mode.value = preset.mode;
  elements.quality.value = preset.quality;
  elements.videoQuality.value = preset.videoQuality;
  elements.embedMetadata.checked = preset.embedMetadata;
  elements.embedCover.checked = preset.embedCover;
  elements.saveThumb.checked = preset.saveThumb;
  elements.saveDescription.checked = preset.saveDescription;
  elements.saveJson.checked = preset.saveJson;
  updateModeVisibility();
  showNotice("Preset applied.", "success");
}

function batchMessage(batch, fallbackSingle = "Job started.") {
  if (!batch) {
    return fallbackSingle;
  }

  if (batch.playlist_expansion && batch.expanded_playlists > 0) {
    if (batch.limit_label === "unlimited") {
      return `Playlist expanded into ${batch.count} job(s). No playlist limit applied.`;
    }

    const suffix = batch.truncated ? ` Limit reached: ${batch.limit}.` : "";
    return `Playlist expanded into ${batch.count} job(s).${suffix}`;
  }

  if (batch.count > 1) {
    return `${batch.count} URL(s) detected.`;
  }

  return fallbackSingle;
}

async function analyze() {
  const urls = getUrls();

  if (!urls.length) {
    showNotice("Paste a URL first.", "error");
    return;
  }

  hideNotice();
  elements.analyzeBtn.disabled = true;
  elements.analyzeBtn.textContent = "Analyzing...";

  try {
    const data = await requestJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });

    elements.preview.classList.remove("hidden");
    elements.thumb.src = data.thumbnail || "";
    elements.title.textContent = data.title || "Untitled";

    const meta = [
      data.uploader || data.channel || "unknown uploader",
      data.duration_string || "unknown duration",
      `${data.formats_count || 0} formats`,
    ];

    elements.meta.textContent = meta.join(" · ");
    elements.desc.textContent = trimText(data.description || "No description available.");

    const message = batchMessage(data.batch, "Preview analyzed successfully.");
    showNotice(`${message} Preview shows the first item.`, "success");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    elements.analyzeBtn.disabled = false;
    elements.analyzeBtn.textContent = "Analyze preview";
  }
}

async function download() {
  const urls = getUrls();

  if (!urls.length) {
    showNotice("Paste a URL first.", "error");
    return;
  }

  if (elements.expandPlaylists.checked && elements.playlistLimit.value === "unlimited") {
    const confirmed = window.confirm("No playlist limit can create a very large queue. Continue?");

    if (!confirmed) {
      return;
    }
  }

  elements.downloadBtn.disabled = true;
  elements.downloadBtn.textContent = "Starting...";

  try {
    const result = await requestJson("/api/download", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });

    const count = result.count || 1;
    const message = batchMessage(result.batch, count === 1 ? "Job started." : `${count} jobs started.`);
    showNotice(count === 1 ? message : `${message} ${count} job(s) started.`, "success");
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    elements.downloadBtn.disabled = false;
    elements.downloadBtn.textContent = "Download";
  }
}

function renderJobStats(jobs) {
  const counts = {
    all: jobs.length,
    queued: 0,
    running: 0,
    completed: 0,
    failed: 0,
    cancelled: 0,
  };

  for (const job of jobs) {
    if (job.status === "queued") {
      counts.queued += 1;
    } else if (job.status === "completed") {
      counts.completed += 1;
    } else if (job.status === "failed") {
      counts.failed += 1;
    } else if (job.status === "cancelled") {
      counts.cancelled += 1;
    } else if (runningStates.includes(job.status)) {
      counts.running += 1;
    }
  }

  const items = [
    ["all", "all", counts.all],
    ["queued", "queued", counts.queued],
    ["running", "running", counts.running],
    ["completed", "completed", counts.completed],
    ["failed", "failed", counts.failed],
    ["cancelled", "cancelled", counts.cancelled],
  ];

  elements.jobStats.innerHTML = items
    .map(([filter, label, count]) => {
      const active = currentJobFilter === filter ? "active" : "";
      return `<button class="${active}" data-job-filter="${filter}">${count} ${label}</button>`;
    })
    .join("");
}

function jobMatchesFilter(job) {
  if (currentJobFilter === "all") {
    return true;
  }

  if (currentJobFilter === "running") {
    return runningStates.includes(job.status);
  }

  return job.status === currentJobFilter;
}

function renderJobs(jobs) {
  renderJobStats(jobs);

  const openDetails = new Set(
    [...elements.jobsList.querySelectorAll(".job details[open]")]
      .map((details) => details.closest(".job")?.dataset.jobId)
      .filter(Boolean)
  );

  const visibleJobs = jobs.filter(jobMatchesFilter);

  if (!visibleJobs.length) {
    const label = currentJobFilter === "all" ? "No jobs yet." : `No ${currentJobFilter} jobs.`;
    elements.jobsList.innerHTML = `<div class="job"><small>${escapeHtml(label)}</small></div>`;
    return;
  }

  elements.jobsList.innerHTML = visibleJobs
    .slice()
    .reverse()
    .map((job) => {
      const files = job.output_files?.length
        ? `<small class="job-path">files: ${escapeHtml(job.output_files.join(", "))}</small>`
        : "";

      const outputDir = job.output_dir
        ? `<small class="job-path">folder: ${escapeHtml(job.output_dir)}</small>`
        : "";

      const detail = job.error_detail
        ? `<details class="error-details" ${openDetails.has(job.id) ? "open" : ""}><summary>show details</summary><pre>${escapeHtml(job.error_detail)}</pre></details>`
        : "";

      const error = job.error
        ? `<small class="job-path error-text">error: ${escapeHtml(job.error)}</small>${detail}`
        : "";

      let qualityLabel = "";
      if (job.mode === "audio_mp3" && job.quality) {
        qualityLabel = job.quality;
      } else if (job.mode === "video_mp4" && job.video_quality) {
        qualityLabel = job.video_quality;
      }

      const modeMeta = [job.mode, qualityLabel].filter(Boolean).join(" · ");
      const jobMeta = modeMeta ? `<small class="job-meta">${escapeHtml(modeMeta)}</small>` : "";
      const completed = job.status === "completed";
      const failed = job.status === "failed";
      const active = activeStates.includes(job.status);

      const actions = `
        <div class="job-control-row">
          ${completed && job.output_dir ? `<button data-open-output="${escapeHtml(job.id)}">Open folder</button>` : ""}
          ${job.output_dir ? `<button data-copy-path="${escapeHtml(job.output_dir)}">Copy path</button>` : ""}
          ${failed ? `<button data-retry="${escapeHtml(job.id)}">Retry</button>` : ""}
          ${active ? `<button data-cancel="${escapeHtml(job.id)}">Cancel</button>` : ""}
          ${!active ? `<button data-remove="${escapeHtml(job.id)}">Remove</button>` : ""}
        </div>
      `;

      return `
        <article class="job" data-job-id="${escapeHtml(job.id)}" data-status="${escapeHtml(job.status)}">
          <div class="job-head">
            <div>
              <strong>${escapeHtml(job.title || job.url || job.id)}</strong><br>
              <small>${escapeHtml(job.message || job.status)}</small>
              ${jobMeta}
            </div>
            <small>${escapeHtml(job.status)} · ${Number(job.progress || 0)}%</small>
          </div>
          <div class="progress"><span style="width:${Number(job.progress || 0)}%"></span></div>
          ${outputDir}
          ${files}
          ${error}
          ${actions}
        </article>
      `;
    })
    .join("");
}
async function refreshJobs() {
  try {
    const jobs = await requestJson("/api/jobs");
    renderJobs(jobs);

    const active = jobs.some((job) => activeStates.includes(job.status));

    if (!active && activePoll) {
      clearInterval(activePoll);
      activePoll = null;
    }
  } catch (error) {
    showNotice(error.message, "error");
  }
}

function startPolling() {
  refreshJobs();

  if (!activePoll) {
    activePoll = setInterval(refreshJobs, 1200);
  }
}

async function pauseQueue() {
  try {
    await requestJson("/api/queue/pause", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice("Queue paused. Running jobs will continue.", "success");
    showJobsNotice("Queue paused. Running jobs will continue.", "success");
    closeQueueMenu();
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function resumeQueue() {
  try {
    await requestJson("/api/queue/resume", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice("Queue resumed.", "success");
    showJobsNotice("Queue resumed.", "success");
    closeQueueMenu();
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function cancelQueuedJobs() {
  try {
    const result = await requestJson("/api/queue/cancel-queued", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice(`Cancelled ${result.cancelled || 0} queued job(s).`, "success");
    showJobsNotice(`Cancelled ${result.cancelled || 0} queued job(s).`, "success");
    closeQueueMenu();
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function cancelActiveJobs() {
  const confirmed = window.confirm("Stop queued jobs and request cancellation for running jobs?");

  if (!confirmed) {
    return;
  }

  try {
    const result = await requestJson("/api/queue/cancel-active", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice(`Stop requested for ${result.cancelled || 0} job(s).`, "success");
    showJobsNotice(`Stop requested for ${result.cancelled || 0} job(s).`, "success");
    closeQueueMenu();
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function clearCompletedJobs() {
  try {
    const result = await sendEmptyRequest("/api/jobs/completed", "DELETE");
    showNotice(`Cleared ${result.removed} done job(s).`, "success");
    showJobsNotice(`Cleared ${result.removed} finished job(s).`, "success");
    closeQueueMenu();
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function clearVisibleJobs() {
  if (!["completed", "failed", "cancelled"].includes(currentJobFilter)) {
    showJobsNotice("Open a completed, failed or cancelled filter before clearing the current filter.", "error");
    return;
  }

  try {
    const result = await sendEmptyRequest(`/api/jobs/visible?status=${encodeURIComponent(currentJobFilter)}`, "DELETE");
    showNotice(`Cleared ${result.removed} ${currentJobFilter} job(s).`, "success");
    showJobsNotice(`Cleared ${result.removed} ${currentJobFilter} job(s).`, "success");
    closeQueueMenu();
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
    showJobsNotice(error.message, "error");
  }
}

async function clearAllJobs() {
  const confirmed = window.confirm("Clear all jobs from the list? This will not delete downloaded files.");

  if (!confirmed) {
    return;
  }

  try {
    const result = await sendEmptyRequest("/api/jobs", "DELETE");
    showNotice(`Cleared ${result.removed} job(s).`, "success");
    showJobsNotice(`Cleared ${result.removed} job(s).`, "success");
    closeQueueMenu();
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function openDownloads() {
  try {
    await requestJson("/api/open-downloads", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice("Opened downloads folder.", "success");
    showJobsNotice("Opened downloads folder.", "success");
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function openJobFolder(jobId) {
  try {
    await requestJson(`/api/jobs/${encodeURIComponent(jobId)}/open-output`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice("Opened output folder.", "success");
    showJobsNotice("Opened output folder.", "success");
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function retryJob(jobId) {
  try {
    await requestJson(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice("Retry started.", "success");
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function cancelJob(jobId) {
  try {
    const result = await requestJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice(result.status === "cancelling" ? "Cancellation requested." : "Job cancelled.", "success");
    showJobsNotice(result.status === "cancelling" ? "Cancellation requested." : "Job cancelled.", "success");
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function removeJob(jobId) {
  try {
    const result = await sendEmptyRequest(`/api/jobs/${encodeURIComponent(jobId)}`, "DELETE");
    showNotice(`Removed ${result.removed} job.`, "success");
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function copyPath(path) {
  try {
    await navigator.clipboard.writeText(path);
    showNotice("Path copied.", "success");
  } catch (error) {
    showNotice("Unable to copy path.", "error");
  }
}

function clearForm() {
  elements.url.value = "";
  elements.preview.classList.add("hidden");
  hideNotice();
}

elements.manageQueueBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleQueueMenu();
});

document.addEventListener("click", (event) => {
  if (elements.queueMenu.classList.contains("hidden")) {
    return;
  }

  if (elements.queueMenu.contains(event.target) || elements.manageQueueBtn.contains(event.target)) {
    return;
  }

  closeQueueMenu();
});

window.addEventListener("resize", () => {
  if (!elements.queueMenu.classList.contains("hidden")) {
    positionQueueMenu();
  }
});

window.addEventListener("scroll", () => {
  if (!elements.queueMenu.classList.contains("hidden")) {
    positionQueueMenu();
  }
}, true);

elements.analyzeBtn.addEventListener("click", analyze);
elements.downloadBtn.addEventListener("click", download);
elements.saveSettingsBtn.addEventListener("click", saveSettings);
elements.clearBtn.addEventListener("click", clearForm);
elements.openDownloadsBtn.addEventListener("click", openDownloads);
elements.pauseQueueBtn.addEventListener("click", pauseQueue);
elements.resumeQueueBtn.addEventListener("click", resumeQueue);
elements.cancelQueuedBtn.addEventListener("click", cancelQueuedJobs);
elements.cancelActiveBtn.addEventListener("click", cancelActiveJobs);
elements.refreshBtn.addEventListener("click", () => {
  showJobsNotice("Job list refreshed.", "info");
  refreshJobs();
});
elements.clearCompletedBtn.addEventListener("click", clearCompletedJobs);
elements.clearVisibleBtn.addEventListener("click", clearVisibleJobs);
elements.clearAllBtn.addEventListener("click", clearAllJobs);
elements.mode.addEventListener("change", updateModeVisibility);

document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.preset));
});

elements.jobStats.addEventListener("click", (event) => {
  const target = event.target.closest("[data-job-filter]");

  if (!target) {
    return;
  }

  currentJobFilter = target.dataset.jobFilter;
  showJobsNotice(`Showing ${currentJobFilter} jobs.`, "info");
  refreshJobs();
});

elements.jobsList.addEventListener("click", (event) => {
  const target = event.target.closest("button");

  if (!target) {
    return;
  }

  if (target.dataset.openOutput) {
    openJobFolder(target.dataset.openOutput);
  } else if (target.dataset.copyPath) {
    copyPath(target.dataset.copyPath);
  } else if (target.dataset.retry) {
    retryJob(target.dataset.retry);
  } else if (target.dataset.cancel) {
    cancelJob(target.dataset.cancel);
  } else if (target.dataset.remove) {
    removeJob(target.dataset.remove);
  }
});

elements.url.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    download();
  }
});

loadSettings();
updateModeVisibility();
refreshJobs();
