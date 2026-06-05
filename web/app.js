/* Jarvis web UI — voice in the browser (Chrome Web Speech API); streams turns over
   /api/turn + /api/stream (SSE) so the page never freezes (Phase 1: Brain Unlock). */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const elHint = $("hint"), elStatus = $("statusText"), elText = $("text");
  const elMic = $("mic"), elOrb = $("orb"), elTranscript = $("transcript");
  const elLang = $("langToggle"), elControl = $("controlToggle"), elNew = $("newChat");

  const store = window.localStorage;
  let lang = store.getItem("jv_lang") || "en";          // "en" | "pt" (mic recognition language)
  let control = store.getItem("jv_control") === "1";     // let Jarvis control the Mac
  let conversing = false;                                  // hands-free loop active
  let busy = false;                                        // thinking or speaking
  let recog = null;
  let health = null;                                       // {accessibility, screen_recording} from /api/health
  let es = null;                                           // active SSE EventSource for the current streaming turn
  let lightbox = null;                                     // singleton fullscreen lightbox (created lazily)

  // Labels for replies that didn't come from the Max-plan brain, so Pietro can tell.
  const SRC_LABEL = {
    ollama:  { en: "offline", pt: "offline" },
    offline: { en: "no brain", pt: "sem cérebro" },
    error:   { en: "error", pt: "erro" },
  };

  const HINTS = {
    idle: { en: "tap the orb to talk — or just type below", pt: "toque na esfera para falar — ou digite abaixo" },
    listening: { en: "listening…", pt: "ouvindo…" },
    thinking: { en: "thinking…", pt: "pensando…" },
    speaking: { en: "", pt: "" },
  };

  // ---- UI state ----------------------------------------------------------------
  function setState(s) {
    body.className = `state-${s}` ;
    elStatus.textContent = s;
    if (s !== "speaking") elHint.textContent = HINTS[s][lang] || HINTS[s].en;
  }

  function addMsg(who, text, placeholder = false) {
    const div = document.createElement("div");
    div.className = `msg ${who === "you" ? "you" : "jv"}${placeholder ? " ph" : ""}`;
    const tag = document.createElement("span");
    tag.className = "who";
    tag.textContent = who === "you" ? "you" : "jarvis";
    const bodyEl = document.createElement("span");
    bodyEl.className = "body";
    bodyEl.textContent = text;
    div.append(tag, bodyEl);
    elTranscript.appendChild(div);
    elTranscript.scrollTop = elTranscript.scrollHeight;
    return div;
  }

  // Tag a Jarvis bubble when the reply came from somewhere other than the Max brain.
  function markSource(div, source) {
    const label = (SRC_LABEL[source] || {})[lang] || (SRC_LABEL[source] || {}).en;
    if (!label) return;  // "max" (or unknown) → no badge
    const b = document.createElement("span");
    b.className = `badge badge-${source}`;
    b.textContent = label;
    div.querySelector(".who").appendChild(b);
  }

  // ---- activity panel helpers (Phase 2: UI-02) --------------------------------
  function toolKey(name) {
    return (name || "").replace(/^mcp__computer__/, "");
  }

  function stepLabel(name, input, lang) {
    const key = toolKey(name);
    const inp = input || {};
    const MAP = {
      screenshot:       { icon: "📸", pt: "Tirou um print",           en: "Took a screenshot" },
      screen_info:      { icon: "📐", pt: "Mediu a tela",             en: "Measured the screen" },
      click:            { icon: "🖱️",  pt: "Clicou",                  en: "Clicked" },
      double_click:     { icon: "🖱️",  pt: "Clique duplo",            en: "Double-clicked" },
      right_click:      { icon: "🖱️",  pt: "Clique direito",          en: "Right-clicked" },
      move_mouse:       { icon: "🖱️",  pt: "Moveu o mouse",           en: "Moved the mouse" },
      scroll:           { icon: "🖱️",  pt: "Rolou a tela",            en: "Scrolled" },
      type_text:        { icon: "⌨️",   pt: "Digitou \"" + String(inp.text || "").slice(0, 40) + "\"",
                                        en: "Typed \""   + String(inp.text || "").slice(0, 40) + "\"" },
      key:              { icon: "⌨️",   pt: "Tecla "   + (inp.key || inp.keys || ""),
                                        en: "Pressed " + (inp.key || inp.keys || "") },
      open_app:         { icon: "🚀", pt: "Abriu "  + (inp.name || inp.app || ""),
                                      en: "Opened " + (inp.name || inp.app || "") },
      frontmost_app:    { icon: "👀", pt: "Viu o app ativo",          en: "Checked active app" },
      list_ui_elements: { icon: "👀", pt: "Leu a tela",               en: "Read the screen" },
      click_element:    { icon: "🖱️",  pt: "Clicou em " + (inp.label || inp.text || ""),
                                       en: "Clicked "   + (inp.label || inp.text || "") },
      run_applescript:  { icon: "📜", pt: "Rodou um AppleScript",     en: "Ran AppleScript" },
      remember:         { icon: "🧠", pt: "Memorizou",                en: "Remembered" },
      ToolSearch:       { icon: "🔎", pt: "Procurou ferramenta",      en: "Searched tools" },
    };
    const entry = MAP[key];
    if (!entry) return { icon: "🔧", text: key };
    return { icon: entry.icon, text: lang === "pt" ? entry.pt : entry.en };
  }

  function ensureActivityPanel(bubble) {
    const existing = bubble.querySelector(".activity");
    if (existing) return existing;
    const section = document.createElement("section");
    section.className = "activity";
    const head = document.createElement("div");
    head.className = "activity-head";
    const timerEl = document.createElement("span");
    timerEl.className = "activity-timer";
    timerEl.textContent = "0:00";
    head.appendChild(timerEl);
    section.appendChild(head);
    const bodyEl = bubble.querySelector(".body");
    bubble.insertBefore(section, bodyEl);
    return section;
  }

  function addStepCard(panel, ev) {
    const { icon, text } = stepLabel(ev.name, ev.input, lang);
    const step = document.createElement("div");
    step.className = "step";

    const iconEl = document.createElement("span");
    iconEl.className = "step-icon";
    iconEl.textContent = icon;

    const labelEl = document.createElement("span");
    labelEl.className = "step-label";
    labelEl.textContent = text;

    const detail = document.createElement("pre");
    detail.className = "step-detail";
    detail.textContent = JSON.stringify(ev.input || {}, null, 2);

    step.append(iconEl, labelEl, detail);
    panel.appendChild(step);
    elTranscript.scrollTop = elTranscript.scrollHeight;
    return step;
  }

  // ---- screenshot helpers (Phase 2: UI-03) ------------------------------------
  function ensureLightbox() {
    if (lightbox) return lightbox;
    lightbox = document.createElement("div");
    lightbox.className = "lightbox";
    const img = document.createElement("img");
    img.alt = lang === "pt" ? "captura de tela ampliada" : "enlarged screenshot";
    lightbox.appendChild(img);
    lightbox.onclick = () => lightbox.classList.remove("open");
    document.body.appendChild(lightbox);
    return lightbox;
  }

  function addShot(panel, b64) {
    if (!b64) return;
    const wrapper = document.createElement("div");
    wrapper.className = "shot";
    const img = document.createElement("img");
    img.src = "data:image/png;base64," + b64;
    img.alt = lang === "pt" ? "captura de tela" : "screenshot";
    img.loading = "lazy";
    img.onclick = () => {
      const lb = ensureLightbox();
      const lbImg = lb.querySelector("img");
      lbImg.src = "data:image/png;base64," + b64;
      lbImg.alt = img.alt;
      lb.classList.add("open");
    };
    wrapper.appendChild(img);
    panel.appendChild(wrapper);
    elTranscript.scrollTop = elTranscript.scrollHeight;
  }

  // ---- toggles -----------------------------------------------------------------
  function renderLang() { elLang.textContent = lang === "pt" ? "🇧🇷 PT" : "🇺🇸 EN"; }
  function renderControl() {
    elControl.textContent = `🖥️ Mac control: ${control ? "on" : "off"}`;
    elControl.classList.toggle("on", control);
  }
  elLang.onclick = () => { lang = lang === "pt" ? "en" : "pt"; store.setItem("jv_lang", lang);
    renderLang(); if (recog) recog.lang = lang === "pt" ? "pt-BR" : "en-US";
    if (!busy && !conversing) setState("idle"); };
  elControl.onclick = () => {
    control = !control; store.setItem("jv_control", control ? "1" : "0"); renderControl();
    // If he switches Mac control on but Accessibility isn't granted, it can't click/type.
    if (control && health && !health.accessibility && !busy && !conversing) {
      elHint.textContent = lang === "pt"
        ? "ative Acessibilidade nas Preferências p/ o controle do Mac"
        : "grant Accessibility in System Settings for Mac control";
    }
  };
  renderLang(); renderControl();

  // ---- speech synthesis (the voice) -------------------------------------------
  let voices = [];
  function loadVoices() { voices = window.speechSynthesis ? speechSynthesis.getVoices() : []; }
  if (window.speechSynthesis) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }
  function isPortuguese(t) {
    return /[ãõçáéíóúâêôàü]/i.test(t) ||
      /\b(você|voce|não|nao|está|esta|sim|olá|ola|obrigad|uma|que|por favor|bom dia|tchau)\b/i.test(t);
  }
  function pickVoice(code) { // code: "pt" | "en"
    const want = code === "pt" ? "pt" : "en";
    const byLang = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(want));
    return (
      byLang.find((v) => /google/i.test(v.name)) ||  // Google neural voices sound best
      byLang.find((v) => code === "pt" ? /brasil|brazil|BR/i.test(v.lang + v.name) : /US/i.test(v.lang)) ||
      byLang[0] || null
    );
  }
  function speak(text, after) {
    if (!window.speechSynthesis) { after && after(); return; }
    speechSynthesis.cancel();
    const code = isPortuguese(text) ? "pt" : "en";
    const u = new SpeechSynthesisUtterance(text);
    const v = pickVoice(code);
    if (v) u.voice = v;
    u.lang = code === "pt" ? "pt-BR" : "en-US";
    u.rate = 1.0; u.pitch = 1.0;
    setState("speaking");
    u.onend = u.onerror = () => { after && after(); };
    speechSynthesis.speak(u);
  }

  // ---- talking to the brain ----------------------------------------------------
  // Stream a turn: POST /api/turn -> {job_id}, then read /api/stream/<id> over SSE.
  // The page never blocks — text and tool steps arrive incrementally, and New Chat
  // stays clickable while Jarvis is thinking (Phase 1 success criteria 1 & 2).
  async function send(text) {
    text = (text || "").trim();
    if (!text) return;
    if (busy) {  // don't freeze — just let him know the current turn is still running
      elHint.textContent = lang === "pt" ? "Jarvis ainda está respondendo…" : "Jarvis is still replying…";
      return;
    }
    busy = true;
    addMsg("you", text);
    elText.value = "";
    setState("thinking");
    // Mac-control turns can take a while (open apps, click, read the screen) — say so.
    if (control) elHint.textContent = lang === "pt" ? "trabalhando no seu Mac…" : "working on your Mac…";
    const ph = addMsg("jarvis", "…", true);
    const bodyEl = ph.querySelector(".body");

    let acc = "";          // text streamed so far (shown live)
    let finalReply = "";   // canonical answer from the result event (used for the voice)
    let source = "max";
    let done = false;

    // Offline guarantee: if the streaming turn produced no answer (e.g. the Max brain is
    // offline → error event with no text), fall back to /api/ask, which degrades to the
    // local Ollama brain. Reuses the existing sync path so the source badge still works.
    const fallbackToAsk = async () => {
      try {
        const r = await fetch("/api/ask", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, control, lang }),
        });
        const d = await r.json();
        const reply = d.reply || "…";
        ph.classList.remove("ph");
        bodyEl.textContent = reply;
        markSource(ph, d.source);
        elTranscript.scrollTop = elTranscript.scrollHeight;
        speak(reply, () => { busy = false; afterTurn(); });
      } catch (_) {
        ph.classList.remove("ph");
        bodyEl.textContent =
          lang === "pt" ? "Não consegui falar com o cérebro do Jarvis." : "Couldn't reach Jarvis's brain.";
        markSource(ph, "error");
        busy = false; afterTurn();
      }
    };

    const finish = () => {
      if (done) return;
      done = true;
      if (es) { es.close(); es = null; }
      if (source === "error" && !acc.trim() && !finalReply) { fallbackToAsk(); return; }
      const reply = acc.trim() || finalReply || "…";
      ph.classList.remove("ph");
      bodyEl.textContent = reply;
      markSource(ph, source);
      elTranscript.scrollTop = elTranscript.scrollHeight;
      speak(finalReply || reply, () => { busy = false; afterTurn(); });
    };

    try {
      const r = await fetch("/api/turn", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, control, lang }),
      });
      if (!r.ok) throw new Error("turn " + r.status);
      const data = await r.json();
      if (!data.job_id) throw new Error("no job_id");

      es = new EventSource("/api/stream/" + encodeURIComponent(data.job_id));

      es.onmessage = (e) => {
        let ev;
        try { ev = JSON.parse(e.data); } catch (_) { return; }
        if (ev.type === "text") {
          acc += ev.text || "";
          ph.classList.remove("ph");
          bodyEl.textContent = acc;
          elTranscript.scrollTop = elTranscript.scrollHeight;
        } else if (ev.type === "tool_use") {
          const panel = ensureActivityPanel(ph); ph.classList.remove("ph");
          addStepCard(panel, { name: ev.name, input: ev.input || {} });
          elHint.textContent = "🔧 " + (ev.name || (lang === "pt" ? "ação" : "action")) + "…";
        } else if (ev.type === "screenshot") {
          const panel = ensureActivityPanel(ph); ph.classList.remove("ph");
          if (ev.data) addShot(panel, ev.data);
          elHint.textContent = lang === "pt" ? "📸 capturando a tela…" : "📸 capturing the screen…";
        } else if (ev.type === "result") {
          finalReply = ev.text || "";
        } else if (ev.type === "error") {
          source = "error";
          if (!acc) acc = ev.text || (lang === "pt" ? "Algo deu errado." : "Something went wrong.");
        }
        // {"type":"done"} also arrives, but the named "done" event below is what finalizes.
      };

      es.addEventListener("done", finish);
      // A dropped/closed connection (after the stream ends, or a real network blip)
      // surfaces here; finalize with whatever we have and stop EventSource from retrying.
      es.onerror = finish;
    } catch (e) {
      if (es) { es.close(); es = null; }
      // /api/turn unreachable or malformed — try the sync path (also covers offline → Ollama).
      fallbackToAsk();
    }
  }

  function afterTurn() {
    if (conversing) startRecog();   // hands-free: listen for the next thing
    else setState("idle");
  }

  // ---- speech recognition (the ears, in Chrome) -------------------------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function makeRecog() {
    const r = new SR();
    r.lang = lang === "pt" ? "pt-BR" : "en-US";
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      let interim = "", final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      if (interim) elHint.textContent = interim;
      if (final.trim()) { stopRecog(); send(final); }
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        conversing = false;
        elHint.textContent = lang === "pt"
          ? "permita o microfone no Chrome para falar" : "allow the microphone in Chrome to talk";
        setState("idle");
      }
    };
    r.onend = () => {
      // Chrome ends recognition after each phrase; resume if we're still in talk mode.
      if (conversing && !busy) { try { r.start(); } catch (_) {} }
    };
    return r;
  }
  function startRecog() {
    if (!SR) return;
    if (!recog) recog = makeRecog();
    recog.lang = lang === "pt" ? "pt-BR" : "en-US";
    try { recog.start(); setState("listening"); } catch (_) {}
  }
  function stopRecog() { if (recog) { try { recog.abort(); } catch (_) {} } }

  function toggleTalk() {
    // While Jarvis is speaking, a tap silences it (barge-in). speak()'s onend then
    // resumes listening in hands-free mode, or settles to idle for a one-shot.
    if (body.classList.contains("state-speaking")) {
      if (window.speechSynthesis) speechSynthesis.cancel();
      return;
    }
    if (!SR) {
      elHint.textContent = lang === "pt"
        ? "voz funciona no Chrome — por enquanto, digite" : "voice needs Chrome — type for now";
      elText.focus(); return;
    }
    if (conversing) { conversing = false; stopRecog(); setState("idle"); }
    else { conversing = true; if (window.speechSynthesis) speechSynthesis.cancel(); startRecog(); }
  }

  // Start a fresh conversation. Works even mid-turn (Phase 1 non-freeze): it abandons the
  // current stream, forgets the brain's session, and clears the screen. The in-flight server
  // turn finishes on its own — we just stop listening to it.
  async function newChat() {
    if (es) { es.close(); es = null; }
    if (window.speechSynthesis) speechSynthesis.cancel();
    conversing = false; stopRecog();
    busy = false;
    try { await fetch("/api/reset", { method: "POST" }); } catch (_) {}
    while (elTranscript.firstChild) elTranscript.removeChild(elTranscript.firstChild);
    setState("idle");
    elHint.textContent = HINTS.idle[lang];
  }

  // ---- health ------------------------------------------------------------------
  async function checkHealth() {
    try { health = await (await fetch("/api/health")).json(); }
    catch (_) { health = null; }
  }

  // ---- wiring ------------------------------------------------------------------
  elMic.onclick = toggleTalk;
  elOrb.onclick = toggleTalk;
  elNew.onclick = newChat;
  elOrb.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleTalk(); } };
  elText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && elText.value.trim()) { e.preventDefault(); conversing = false; send(elText.value); }
  });
  // Escape: hush the voice and drop out of hands-free, without touching the transcript.
  // Also closes the screenshot lightbox if open.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (lightbox && lightbox.classList.contains("open")) { lightbox.classList.remove("open"); return; }
    if (window.speechSynthesis) speechSynthesis.cancel();
    if (conversing) { conversing = false; stopRecog(); if (!busy) setState("idle"); }
  });

  setState("idle");
  checkHealth();
  // a warm first impression
  setTimeout(() => { if (!busy && !conversing) elHint.textContent = HINTS.idle[lang]; }, 50);
})();
