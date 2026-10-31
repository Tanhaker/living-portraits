const API = window.LP_API || "";
const $ = (id) => document.getElementById(id);
const STEPS = ["queued", "mending", "colouring", "finding depth", "checking it is still them"];

let viewer = null;
let current = null;

// ---- The altar ------------------------------------------------------------

function initViewer() {
  try {
    viewer = new LivingPortrait($("portrait"));
  } catch {
    // No WebGL: show the restored photo as a still image instead.
    $("portrait").hidden = true;
    $("fallback").hidden = false;
    $("replay").hidden = true;
    $("record").hidden = true;
  }
}

async function showOnAltar(item, { scroll = false } = {}) {
  current = item;
  $("r-name").textContent = item.name || "";
  $("r-memory").textContent = item.memory || "";
  $("download").href = item.download || item.final;
  if (viewer) await viewer.show(item);
  else $("fallback").src = item.final;
  if (scroll) $("altar").scrollIntoView({ behavior: "smooth", block: "center" });
}

$("replay").addEventListener("click", () => viewer && viewer.play());

$("record").addEventListener("click", async () => {
  if (!viewer || !current) return;
  const btn = $("record");
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="ph ph-record"></i>Recording';
  try {
    const blob = await viewer.record(9);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(current.name || "portrait").replace(/[^\w]+/g, "-").toLowerCase()}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    a.click();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = label;
  }
});

// ---- Gallery ----------------------------------------------------------------

async function loadExamples() {
  try {
    const items = await fetch("examples/examples.json?v=4").then((r) => r.json());
    return items.map((e) => ({ ...e, before: `examples/${e.before}`, final: `examples/${e.final}`, depth: `examples/${e.depth}` }));
  } catch { return []; }
}

function fromJob(job) {
  const f = (k) => `${API}/files/${job.id}/${job.files[k]}`;
  return { name: job.name, memory: job.memory, before: f("before"), final: f("final"), depth: f("depth"),
           download: f("download"), face: job.face };
}

function renderGallery(items) {
  if (!items.length) return;
  $("gallery").innerHTML = "";
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    const img = document.createElement("img");
    img.src = item.final;
    img.alt = item.name || "Restored portrait";
    img.loading = "lazy";
    const name = document.createElement("span");
    name.textContent = item.name || "";
    b.append(img, name);
    b.addEventListener("click", () => showOnAltar(item, { scroll: true }));
    $("gallery").append(b);
  }
  $("gallery-section").hidden = false;
}

// ---- Placing a photo ----------------------------------------------------------

const form = $("form"), photo = $("photo"), drop = $("drop");

function preview(file) {
  if (!file) return;
  $("preview").src = URL.createObjectURL(file);
  $("preview").hidden = false;
  $("drop-text").hidden = true;
}

photo.addEventListener("change", () => preview(photo.files[0]));
["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (ev) => {
  const file = ev.dataTransfer.files[0];
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  photo.files = dt.files;
  preview(file);
});

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!photo.files[0]) return showError("Choose a photo first.");
  showError("");
  const data = new FormData(form);
  data.set("share", form.share.checked);
  $("submit").disabled = true;
  try {
    const res = await fetch(`${API}/api/portraits`, { method: "POST", body: data });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "The server could not take this photo.");
    const { id } = await res.json();
    history.replaceState(null, "", `#${id}`);
    follow(id);
  } catch (e) {
    showError(e.message);
  } finally {
    $("submit").disabled = false;
  }
});

function setStep(step) {
  const idx = STEPS.indexOf(step ?? "queued");
  document.querySelectorAll(".steps li").forEach((li, i) => {
    li.classList.toggle("done", i < idx);
    li.classList.toggle("active", i === idx);
  });
}

async function follow(id) {
  form.hidden = true;
  $("working").hidden = false;
  $("working-note").textContent = "Usually under a minute.";
  for (;;) {
    let job;
    try {
      job = await fetch(`${API}/api/portraits/${id}`).then((r) => (r.ok ? r.json() : Promise.reject()));
    } catch {
      $("working-note").textContent = "Could not reach the server. Trying again.";
      await new Promise((r) => setTimeout(r, 4000));
      continue;
    }
    if (job.status === "done") {
      form.reset();
      $("preview").hidden = true;
      $("drop-text").hidden = false;
      form.hidden = false;
      $("working").hidden = true;
      return showOnAltar(fromJob(job), { scroll: true });
    }
    if (job.status === "failed") {
      form.hidden = false;
      $("working").hidden = true;
      return showError(`That photo could not be restored: ${job.error}`);
    }
    setStep(job.status === "queued" ? "queued" : job.step);
    await new Promise((r) => setTimeout(r, 1200));
  }
}

// ---- Falling marigold petals behind everything ---------------------------------

function petals() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = $("petals"), ctx = c.getContext("2d");
  const colours = ["#e8a243", "#f0b25d", "#d9822b"];
  let w, h, list;
  const size = () => {
    w = c.width = innerWidth;
    h = c.height = innerHeight;
    list = Array.from({ length: Math.round(w / 90) }, () => spawn(true));
  };
  const spawn = (anywhere) => ({
    x: Math.random() * w, y: anywhere ? Math.random() * h : -20,
    r: 3 + Math.random() * 4, vy: 0.25 + Math.random() * 0.45, sway: Math.random() * 6.28,
    rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * 0.02, col: colours[(Math.random() * 3) | 0],
    a: 0.35 + Math.random() * 0.35,
  });
  size();
  addEventListener("resize", size);
  (function tick() {
    ctx.clearRect(0, 0, w, h);
    for (const p of list) {
      p.y += p.vy;
      p.sway += 0.01;
      p.x += Math.sin(p.sway) * 0.3;
      p.rot += p.vr;
      if (p.y > h + 20) Object.assign(p, spawn(false));
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = p.a;
      ctx.fillStyle = p.col;
      ctx.beginPath();
      ctx.ellipse(0, 0, p.r, p.r * 0.55, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
    requestAnimationFrame(tick);
  })();
}

// ---- Start ---------------------------------------------------------------------

(async function start() {
  initViewer();
  petals();
  const examples = await loadExamples();

  let shared = [];
  try {
    const health = await fetch(`${API}/api/health`).then((r) => r.json());
    if (!health.ready) $("server-note").textContent = "The restoring server is starting up. Give it a minute.";
    shared = (await fetch(`${API}/api/gallery`).then((r) => r.json())).map(fromJob);
  } catch {
    $("server-note").textContent = "The restoring server is resting right now, so new photos can't be placed. The portraits below still work.";
    $("submit").disabled = true;
  }

  const all = shared.concat(examples);
  renderGallery(all);
  const first = examples[0] || all[0];
  if (location.hash.length > 1) follow(location.hash.slice(1));
  else if (first) showOnAltar(first);
})();
