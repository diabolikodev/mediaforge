const elements = {
  url: document.querySelector("#url"),
  analyzeBtn: document.querySelector("#analyzeBtn"),
  downloadBtn: document.querySelector("#downloadBtn"),
  clearBtn: document.querySelector("#clearBtn"),
  openDownloadsBtn: document.querySelector("#openDownloadsBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  clearCompletedBtn: document.querySelector("#clearCompletedBtn"),
  clearAllBtn: document.querySelector("#clearAllBtn"),
  notice: document.querySelector("#notice"),
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
  jobsList: document.querySelector("#jobsList"),
};

let activePoll = null;

function showNotice(message, type = "info") {
  elements.notice.textContent = message;
  elements.notice.dataset.type = type;
  elements.notice.classList.remove("hidden");
}

function hideNotice() {
  elements.notice.classList.add("hidden");
}

function trimText(text, max = 180) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}...` : text;
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

async function analyze() {
  const url = elements.url.value.trim();

  if (!url) {
    showNotice("Paste a URL first.", "error");
    return;
  }

  hideNotice();
  elements.analyzeBtn.disabled = true;
  elements.analyzeBtn.textContent = "Analyzing...";

  try {
    const data = await requestJson("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ url }),
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
    showNotice("URL analyzed successfully.", "success");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    elements.analyzeBtn.disabled = false;
    elements.analyzeBtn.textContent = "Analyze";
  }
}

async function download() {
  const url = elements.url.value.trim();

  if (!url) {
    showNotice("Paste a URL first.", "error");
    return;
  }

  elements.downloadBtn.disabled = true;
  elements.downloadBtn.textContent = "Starting...";

  try {
    const job = await requestJson("/api/download", {
      method: "POST",
      body: JSON.stringify({
        url,
        mode: elements.mode.value,
        quality: elements.quality.value,
        video_quality: elements.videoQuality.value,
        embed_metadata: elements.embedMetadata.checked,
        embed_cover: elements.embedCover.checked,
        save_thumbnail: elements.saveThumb.checked,
        save_description: elements.saveDescription.checked,
        save_metadata_json: elements.saveJson.checked,
      }),
    });

    showNotice(`Job ${job.id} started.`, "success");
    startPolling();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    elements.downloadBtn.disabled = false;
    elements.downloadBtn.textContent = "Download";
  }
}

function renderJobs(jobs) {
  if (!jobs.length) {
    elements.jobsList.innerHTML = `<div class="job"><small>No jobs yet.</small></div>`;
    return;
  }

  elements.jobsList.innerHTML = jobs
    .slice()
    .reverse()
    .map((job) => {
      const files = job.output_files?.length
        ? `<small class="job-path">files: ${job.output_files.join(", ")}</small>`
        : "";

      const outputDir = job.output_dir
        ? `<small class="job-path">folder: ${job.output_dir}</small>`
        : "";

      const error = job.error ? `<small class="job-path">error: ${job.error}</small>` : "";

      let qualityLabel = "";
      if (job.mode === "audio_mp3" && job.quality) {
        qualityLabel = job.quality;
      } else if (job.mode === "video_mp4" && job.video_quality) {
        qualityLabel = job.video_quality;
      }

      const modeMeta = [job.mode, qualityLabel].filter(Boolean).join(" · ");
      const jobMeta = modeMeta ? `<small class="job-meta">${modeMeta}</small>` : "";

      return `
        <article class="job">
          <div class="job-head">
            <div>
              <strong>${job.title || job.id}</strong><br>
              <small>${job.message || job.status}</small>
              ${jobMeta}
            </div>
            <small>${job.status} · ${job.progress}%</small>
          </div>
          <div class="progress"><span style="width:${job.progress}%"></span></div>
          ${outputDir}
          ${files}
          ${error}
        </article>
      `;
    })
    .join("");
}

async function refreshJobs() {
  try {
    const jobs = await requestJson("/api/jobs");
    renderJobs(jobs);

    const active = jobs.some((job) =>
      ["queued", "analyzing", "downloading", "converting", "tagging"].includes(job.status)
    );

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

async function clearCompletedJobs() {
  try {
    const result = await sendEmptyRequest("/api/jobs/completed", "DELETE");
    showNotice(`Cleared ${result.removed} completed/failed job(s).`, "success");
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
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
    await refreshJobs();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function openDownloads() {
  try {
    const result = await requestJson("/api/open-downloads", {
      method: "POST",
      body: JSON.stringify({}),
    });
    showNotice(`Opened downloads folder.`, "success");
  } catch (error) {
    showNotice(error.message, "error");
  }
}

function clearForm() {
  elements.url.value = "";
  elements.preview.classList.add("hidden");
  hideNotice();
}

elements.analyzeBtn.addEventListener("click", analyze);
elements.downloadBtn.addEventListener("click", download);
elements.clearBtn.addEventListener("click", clearForm);
elements.openDownloadsBtn.addEventListener("click", openDownloads);
elements.refreshBtn.addEventListener("click", refreshJobs);
elements.clearCompletedBtn.addEventListener("click", clearCompletedJobs);
elements.clearAllBtn.addEventListener("click", clearAllJobs);
elements.mode.addEventListener("change", updateModeVisibility);

elements.url.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    analyze();
  }
});

updateModeVisibility();
refreshJobs();
