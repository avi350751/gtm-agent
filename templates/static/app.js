const $ = (sel) => document.querySelector(sel);
const topicInput = $("#topic");
const goBtn = $("#go");
const loading = $("#loading");
const loadingMsg = $("#loading-msg");
const errorBox = $("#error");
const results = $("#results");

const LOADING_STEPS = [
  "Retrieving context from your docs…",
  "Setting audience, tone & messaging…",
  "Drafting all four formats…",
  "Reviewing for grounding & consistency…",
];
let loadingTimer = null;

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function startLoading() {
  errorBox.hidden = true;
  results.hidden = true;
  results.innerHTML = "";
  loading.hidden = false;
  goBtn.disabled = true;
  let i = 0;
  loadingMsg.textContent = LOADING_STEPS[0];
  loadingTimer = setInterval(() => {
    i = (i + 1) % LOADING_STEPS.length;
    loadingMsg.textContent = LOADING_STEPS[i];
  }, 2200);
}

function stopLoading() {
  clearInterval(loadingTimer);
  loading.hidden = true;
  goBtn.disabled = false;
}

async function generate(topic) {
  startLoading();
  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    render(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    stopLoading();
  }
}

/* ---- small builders ------------------------------------------------- */
function copyButton(getText) {
  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.textContent = "Copy";
  btn.onclick = async () => {
    await navigator.clipboard.writeText(getText());
    btn.textContent = "Copied";
    btn.classList.add("done");
    setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("done"); }, 1500);
  };
  return btn;
}

function card({ key, accent, title, copyText, buildBody }) {
  const el = document.createElement("section");
  el.className = "card";
  el.dataset.key = key || "";
  if (accent) el.style.setProperty("--accent", accent);

  const head = document.createElement("div");
  head.className = "card-head";
  const h = document.createElement("p");
  h.className = "card-title";
  h.textContent = title;
  head.appendChild(h);
  if (copyText) head.appendChild(copyButton(copyText));
  el.appendChild(head);

  buildBody(el);
  return el;
}

function starRating(topic, key) {
  const wrap = document.createElement("div");
  wrap.className = "rate";
  const label = document.createElement("span");
  label.textContent = "Your rating";
  const stars = document.createElement("span");
  stars.className = "stars";
  const storeKey = `rating:${topic}:${key}`;
  const saved = Number(localStorage.getItem(storeKey) || 0);

  const paint = (n) => stars.querySelectorAll(".star")
    .forEach((s, idx) => s.classList.toggle("on", idx < n));

  for (let i = 1; i <= 5; i++) {
    const s = document.createElement("span");
    s.className = "star";
    s.textContent = "★";
    s.onclick = () => { localStorage.setItem(storeKey, i); paint(i); };
    stars.appendChild(s);
  }
  paint(saved);
  wrap.append(label, stars);
  return wrap;
}

/* ---- main render ---------------------------------------------------- */
function render(data) {
  const { topic, strategy: s = {}, content: c = {}, review: r = {}, revisions = 0 } = data;
  results.innerHTML = "";

  // Review banner (rating) goes first
  results.appendChild(reviewCard(r, revisions));

  // Strategy
  results.appendChild(card({
    accent: "var(--indigo)", title: "GTM Strategy",
    buildBody: (el) => {
      const dl = document.createElement("dl");
      dl.className = "kv";
      const row = (k, vNode) => {
        const dt = document.createElement("dt"); dt.textContent = k;
        const dd = document.createElement("dd"); dd.appendChild(vNode);
        dl.append(dt, dd);
      };
      const txt = (t) => document.createTextNode(t || "—");
      row("Audience", txt(s.target_audience));
      row("Tone", txt(s.tone));
      row("Summary", txt(s.product_summary));
      const props = document.createElement("div");
      props.className = "taglist";
      (s.value_props || []).forEach((v) => {
        const t = document.createElement("span"); t.className = "tag"; t.textContent = v;
        props.appendChild(t);
      });
      row("Value props", props);
      row("Key messages", txt((s.key_messages || []).join("  •  ")));
      row("CTA", txt(s.call_to_action));
      el.appendChild(dl);
    },
  }));

  // LinkedIn
  results.appendChild(contentCard({
    key: "linkedin_post", topic, review: r, accent: "var(--linkedin)",
    title: "LinkedIn Post", text: c.linkedin_post,
    buildBody: (el) => addText(el, c.linkedin_post),
  }));

  // Email
  const emailFull = `Subject: ${c.email_subject || ""}\n\n${c.email_body || ""}`;
  results.appendChild(contentCard({
    key: "email", topic, review: r, accent: "var(--email)",
    title: "Promotional Email", text: emailFull,
    buildBody: (el) => {
      const subj = document.createElement("div");
      subj.className = "subject";
      subj.innerHTML = `<b>Subject:</b> ${esc(c.email_subject)}`;
      el.appendChild(subj);
      addText(el, c.email_body);
    },
  }));

  // Blog
  const blogFull = `${c.blog_title || ""}\n\n${c.blog_draft || ""}`;
  results.appendChild(contentCard({
    key: "blog", topic, review: r, accent: "var(--blog)",
    title: "Blog Draft", text: blogFull,
    buildBody: (el) => {
      const t = document.createElement("div");
      t.className = "blog-title"; t.textContent = c.blog_title || "";
      el.appendChild(t);
      addText(el, c.blog_draft);
    },
  }));

  // Ads
  results.appendChild(contentCard({
    key: "ads", topic, review: r, accent: "var(--ads)",
    title: "Ad Variations",
    text: (c.ad_variations || []).map((a) => `${a.headline}\n${a.body}`).join("\n\n"),
    buildBody: (el) => {
      const grid = document.createElement("div");
      grid.className = "ads-grid";
      (c.ad_variations || []).forEach((a) => {
        const ad = document.createElement("div");
        ad.className = "ad";
        ad.innerHTML =
          `<span class="ad-angle">${esc(a.angle)}</span>` +
          `<div class="ad-headline">${esc(a.headline)}</div>` +
          `<div class="ad-body">${esc(a.body)}</div>`;
        grid.appendChild(ad);
      });
      el.appendChild(grid);
    },
  }));

  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function addText(el, text) {
  const p = document.createElement("div");
  p.className = "body-text";
  p.textContent = text || "";
  el.appendChild(p);
}

// content card = card + per-piece critique + user stars in the footer
function contentCard(opts) {
  const el = card({
    key: opts.key, accent: opts.accent, title: opts.title,
    copyText: () => opts.text || "", buildBody: opts.buildBody,
  });
  const foot = document.createElement("div");
  foot.className = "card-foot";

  const note = pieceCritique(opts.review, opts.key);
  if (note) {
    const n = document.createElement("div");
    n.className = "piece-note";
    n.innerHTML = `<b>Reviewer:</b> ${esc(note)}`;
    foot.appendChild(n);
  } else {
    foot.appendChild(document.createElement("div")); // spacer
  }
  foot.appendChild(starRating(opts.topic, opts.key));
  el.appendChild(foot);
  return el;
}

// Find a reviewer critique whose piece name matches this card's key.
function pieceCritique(review, key) {
  const crits = (review && review.critiques) || [];
  const k = key.toLowerCase();
  for (const c of crits) {
    const p = String(c.piece || "").toLowerCase();
    if (p.includes(k) || k.includes(p.split("_")[0])) {
      const lines = [...(c.issues || []), ...(c.suggestions || [])];
      if (lines.length) return lines.join(" ");
    }
  }
  return null;
}

function reviewCard(r, revisions) {
  const score = Number(r.quality_score ?? 0);
  const color = score >= 8 ? "var(--good)" : score >= 6 ? "var(--mid)" : "var(--bad)";

  const el = document.createElement("section");
  el.className = "card review";
  el.style.setProperty("--score-color", color);

  const top = document.createElement("div");
  top.className = "review-top";

  const badge = document.createElement("div");
  badge.className = "score";
  badge.innerHTML = `<b>${score || "–"}</b><span>/ 10</span>`;
  top.appendChild(badge);

  const checks = document.createElement("div");
  checks.className = "checks";
  const mk = (label, ok) => {
    const c = document.createElement("span");
    c.className = "check " + (ok ? "pass" : "fail");
    c.textContent = (ok ? "✓ " : "✕ ") + label;
    return c;
  };
  checks.append(
    mk("Grounded", r.grounded),
    mk("Consistent", r.consistent),
    mk("Tone aligned", r.tone_aligned),
  );
  top.appendChild(checks);

  const verdict = document.createElement("div");
  verdict.className = "verdict";
  verdict.innerHTML =
    (r.needs_revision ? "Needs work (cap reached)" : "Passed review") +
    `<br>${revisions} revision${revisions === 1 ? "" : "s"} performed`;
  top.appendChild(verdict);

  el.appendChild(top);

  if (r.overall_feedback) {
    const fb = document.createElement("div");
    fb.className = "review-feedback";
    fb.textContent = r.overall_feedback;
    el.appendChild(fb);
  }

  const crits = r.critiques || [];
  if (crits.length) {
    const box = document.createElement("div");
    box.className = "crit";
    crits.forEach((c) => {
      const item = document.createElement("div");
      item.className = "crit-item";
      const lines = [...(c.issues || []), ...(c.suggestions || [])];
      item.innerHTML =
        `<b>${esc(c.piece)}</b>` +
        (lines.length ? `<ul>${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "");
      box.appendChild(item);
    });
    el.appendChild(box);
  }
  return el;
}

/* ---- events --------------------------------------------------------- */
goBtn.onclick = () => {
  const topic = topicInput.value.trim();
  if (topic) generate(topic);
};
topicInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") goBtn.click();
});
document.querySelectorAll(".chip").forEach((chip) => {
  chip.onclick = () => {
    topicInput.value = chip.dataset.topic;
    goBtn.click();
  };
});
