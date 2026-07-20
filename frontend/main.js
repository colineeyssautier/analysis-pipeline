"use strict";
if (window.location.protocol === "file:") {
    document.body.innerHTML = `
    <div style="max-width:640px;margin:80px auto;font-family:'Segoe UI',system-ui,sans-serif;line-height:1.6;padding:0 24px;color:#111;">
      <h2>This page needs the backend server running</h2>
      <p>You opened this file directly from disk, but the chat needs the Python server to search the knowledge base and answer questions — it can't work as a plain file.</p>
      <p>From a terminal, in the project folder, run:</p>
      <pre style="background:#f4f4f4;padding:12px 16px;border-radius:8px;overflow-x:auto;">uvicorn server:app --reload</pre>
      <p>Then open the address it prints (usually <code>http://127.0.0.1:8000</code>) in your browser — not this file.</p>
    </div>`;
    throw new Error("Opened via file:// — backend not reachable, aborting.");
}
const messagesEl = document.getElementById("messages");
const questionEl = document.getElementById("question");
const askForm = document.getElementById("ask-form");
const minSatisfactionEl = document.getElementById("min-satisfaction");
const minSatisfactionVal = document.getElementById("min-satisfaction-val");
const nSimilarEl = document.getElementById("n-similar");
const nSimilarVal = document.getElementById("n-similar-val");
const useDecompositionEl = document.getElementById("use-decomposition");
const addDocBtn = document.getElementById("add-doc-btn");
const uploadModal = document.getElementById("upload-modal");
const modalCancel = document.getElementById("modal-cancel");
const modalUpload = document.getElementById("modal-upload");
const fileInput = document.getElementById("file-input");
const sourceTypeEl = document.getElementById("source-type");
const uploadPanel = document.getElementById("upload-panel");
const uploadList = document.getElementById("upload-list");
const docsListEl = document.getElementById("docs-list");
const tabs = Array.from(document.querySelectorAll(".tab"));
const views = Array.from(document.querySelectorAll(".view"));
function switchView(viewId) {
    for (const tab of tabs)
        tab.classList.toggle("active", tab.dataset.view === viewId);
    for (const view of views)
        view.classList.toggle("active", view.id === viewId);
    if (viewId === "view-docs")
        void loadDocuments();
}
for (const tab of tabs) {
    tab.addEventListener("click", () => switchView(tab.dataset.view));
}
minSatisfactionEl.addEventListener("input", () => {
    minSatisfactionVal.textContent = minSatisfactionEl.value;
});
nSimilarEl.addEventListener("input", () => {
    nSimilarVal.textContent = nSimilarEl.value;
});
function addUserMessage(question) {
    const div = document.createElement("div");
    div.className = "msg-user";
    div.textContent = question;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
}
function addAiMessage(data) {
    const div = document.createElement("div");
    div.className = "msg-ai";
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `Based on ${data.projects.length} similar past project(s) and ${data.documents.length} reference document chunk(s)`;
    div.appendChild(meta);
    const body = document.createElement("div");
    body.textContent = data.answer;
    div.appendChild(body);
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "How this answer was built";
    details.appendChild(summary);
    details.appendChild(sectionTitle("Angles explored:"));
    const anglesList = document.createElement("ul");
    if (data.subqueries.length > 1) {
        for (const sq of data.subqueries)
            anglesList.appendChild(listItem(sq));
    }
    else {
        anglesList.appendChild(listItem("(no decomposition — question used as-is)"));
    }
    details.appendChild(anglesList);
    details.appendChild(sectionTitle("Matched projects:"));
    const projectsList = document.createElement("ul");
    for (const p of data.projects) {
        const matchedBy = (p._matched_by ?? []).join(", ") || "n/a";
        const facet = p.best_facet ? `, best facet: ${p.best_facet}` : "";
        projectsList.appendChild(listItem(`${p.name ?? "N/A"} — matched via ${matchedBy}${facet}`));
    }
    details.appendChild(projectsList);
    details.appendChild(sectionTitle("Matched reference chunks:"));
    const docsUl = document.createElement("ul");
    if (data.documents.length) {
        for (const d of data.documents) {
            const matchedBy = (d._matched_by ?? []).join(", ") || "n/a";
            docsUl.appendChild(listItem(`${d.title ?? "N/A"} (chunk ${d.chunk_index ?? "?"}) — matched via ${matchedBy}`));
        }
    }
    else {
        docsUl.appendChild(listItem("(none)"));
    }
    details.appendChild(docsUl);
    div.appendChild(details);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
}
function sectionTitle(text) {
    const p = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = text;
    p.appendChild(strong);
    return p;
}
function listItem(text) {
    const li = document.createElement("li");
    li.textContent = text;
    return li;
}
async function submitQuestion(question) {
    addUserMessage(question);
    const loading = document.createElement("div");
    loading.className = "msg-ai";
    loading.textContent = "Searching past projects and reference documents, then generating analysis...";
    messagesEl.appendChild(loading);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    try {
        const res = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question,
                n_similar: Number(nSimilarEl.value),
                min_satisfaction: Number(minSatisfactionEl.value),
                use_decomposition: useDecompositionEl.checked,
            }),
        });
        if (!res.ok)
            throw new Error(`Server error (${res.status})`);
        const data = (await res.json());
        loading.remove();
        addAiMessage(data);
    }
    catch (err) {
        loading.remove();
        const errorDiv = document.createElement("div");
        errorDiv.className = "msg-ai";
        errorDiv.textContent = `Error: ${err.message}`;
        messagesEl.appendChild(errorDiv);
    }
}
askForm.addEventListener("submit", (e) => e.preventDefault());
questionEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const question = questionEl.value.trim();
        if (!question)
            return;
        questionEl.value = "";
        void submitQuestion(question);
    }
});
// --- Document upload ---
addDocBtn.addEventListener("click", () => {
    uploadModal.classList.remove("hidden");
});
modalCancel.addEventListener("click", () => {
    uploadModal.classList.add("hidden");
    fileInput.value = "";
});
modalUpload.addEventListener("click", () => {
    const files = fileInput.files;
    if (!files || files.length === 0)
        return;
    uploadModal.classList.add("hidden");
    uploadPanel.classList.remove("hidden");
    const formData = new FormData();
    formData.append("source_type", sourceTypeEl.value);
    const entries = [];
    for (const file of Array.from(files)) {
        formData.append("files", file);
        const title = file.name.replace(/\.pdf$/i, "");
        const item = document.createElement("div");
        item.className = "upload-item";
        item.innerHTML = `<div class="title">${title}</div><div class="status processing">Processing...</div>`;
        uploadList.appendChild(item);
        entries.push({ title, el: item });
    }
    fileInput.value = "";
    fetch("/api/upload", { method: "POST", body: formData })
        .then((res) => res.json())
        .then((data) => {
        for (const result of data.results) {
            const entry = entries.find((e) => e.title === result.title);
            if (!entry)
                continue;
            const statusEl = entry.el.querySelector(".status");
            statusEl.className = `status ${result.status}`;
            if (result.status === "success") {
                statusEl.textContent = `Added (${result.chunks} chunks)`;
            }
            else if (result.status === "skipped") {
                statusEl.textContent = `Skipped (${result.reason ?? ""})`;
            }
            else {
                statusEl.textContent = `Failed (${result.reason ?? ""})`;
            }
        }
    })
        .catch((err) => {
        for (const entry of entries) {
            const statusEl = entry.el.querySelector(".status");
            statusEl.className = "status failed";
            statusEl.textContent = `Error: ${err.message}`;
        }
    });
});
// --- "See reference documents" tab ---
async function loadDocuments() {
    docsListEl.textContent = "Loading...";
    try {
        const res = await fetch("/api/documents");
        const data = (await res.json());
        docsListEl.innerHTML = "";
        if (data.documents.length === 0) {
            docsListEl.textContent = "No reference documents added yet.";
            return;
        }
        for (const doc of data.documents) {
            const div = document.createElement("div");
            div.className = "doc-item";
            div.innerHTML = `<div class="title">${doc.title}</div><div class="meta">${doc.source_type} — ${doc.chunks} chunks</div>`;
            docsListEl.appendChild(div);
        }
    }
    catch (err) {
        docsListEl.textContent = `Could not load document list: ${err.message}`;
    }
}
