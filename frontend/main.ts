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

type Project = {
  name?: string;
  best_facet?: string;
  _matched_by?: string[];
  [key: string]: unknown;
};

type DocChunk = {
  title?: string;
  chunk_index?: number;
  _matched_by?: string[];
  [key: string]: unknown;
};

type AskResponse = {
  answer: string;
  subqueries: string[];
  projects: Project[];
  documents: DocChunk[];
};

type UploadResult = {
  title: string;
  status: "success" | "skipped" | "failed";
  reason: string | null;
  chunks: number;
};

const messagesEl = document.getElementById("messages") as HTMLDivElement;
const questionEl = document.getElementById("question") as HTMLTextAreaElement;
const askForm = document.getElementById("ask-form") as HTMLFormElement;
const minSatisfactionEl = document.getElementById("min-satisfaction") as HTMLInputElement;
const minSatisfactionVal = document.getElementById("min-satisfaction-val") as HTMLSpanElement;
const nSimilarEl = document.getElementById("n-similar") as HTMLInputElement;
const nSimilarVal = document.getElementById("n-similar-val") as HTMLSpanElement;
const useDecompositionEl = document.getElementById("use-decomposition") as HTMLInputElement;

const addDocBtn = document.getElementById("add-doc-btn") as HTMLButtonElement;
const uploadModal = document.getElementById("upload-modal") as HTMLDivElement;
const modalCancel = document.getElementById("modal-cancel") as HTMLButtonElement;
const modalUpload = document.getElementById("modal-upload") as HTMLButtonElement;
const fileInput = document.getElementById("file-input") as HTMLInputElement;
const dropZone = document.getElementById("drop-zone") as HTMLDivElement;
const fileListEl = document.getElementById("file-list") as HTMLDivElement;
const sourceTypeEl = document.getElementById("source-type") as HTMLSelectElement;
const uploadPanel = document.getElementById("upload-panel") as HTMLDivElement;
const uploadList = document.getElementById("upload-list") as HTMLDivElement;

const docsListEl = document.getElementById("docs-list") as HTMLDivElement;

const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>(".tab"));
const views = Array.from(document.querySelectorAll<HTMLElement>(".view"));

function switchView(viewId: string): void {
  for (const tab of tabs) tab.classList.toggle("active", tab.dataset.view === viewId);
  for (const view of views) view.classList.toggle("active", view.id === viewId);
  if (viewId === "view-docs") void loadDocuments();
}

for (const tab of tabs) {
  tab.addEventListener("click", () => switchView(tab.dataset.view as string));
}

minSatisfactionEl.addEventListener("input", () => {
  minSatisfactionVal.textContent = minSatisfactionEl.value;
});
nSimilarEl.addEventListener("input", () => {
  nSimilarVal.textContent = nSimilarEl.value;
});

function addUserMessage(question: string): void {
  const div = document.createElement("div");
  div.className = "msg-user";
  div.textContent = question;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addAiMessage(data: AskResponse): HTMLDivElement {
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
    for (const sq of data.subqueries) anglesList.appendChild(listItem(sq));
  } else {
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
  } else {
    docsUl.appendChild(listItem("(none)"));
  }
  details.appendChild(docsUl);

  div.appendChild(details);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

function sectionTitle(text: string): HTMLParagraphElement {
  const p = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = text;
  p.appendChild(strong);
  return p;
}

function listItem(text: string): HTMLLIElement {
  const li = document.createElement("li");
  li.textContent = text;
  return li;
}

async function submitQuestion(question: string): Promise<void> {
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
    if (!res.ok) throw new Error(`Server error (${res.status})`);
    const data = (await res.json()) as AskResponse;
    loading.remove();
    addAiMessage(data);
  } catch (err) {
    loading.remove();
    const errorDiv = document.createElement("div");
    errorDiv.className = "msg-ai";
    errorDiv.textContent = `Error: ${(err as Error).message}`;
    messagesEl.appendChild(errorDiv);
  }
}

askForm.addEventListener("submit", (e) => e.preventDefault());

questionEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const question = questionEl.value.trim();
    if (!question) return;
    questionEl.value = "";
    void submitQuestion(question);
  }
});

// --- Document upload ---

addDocBtn.addEventListener("click", () => {
  uploadModal.classList.remove("hidden");
});

function renderFileList(): void {
  const files = fileInput.files;
  fileListEl.innerHTML = "";
  if (!files || files.length === 0) return;
  for (const file of Array.from(files)) {
    const div = document.createElement("div");
    div.textContent = file.name;
    fileListEl.appendChild(div);
  }
}

function addFiles(newFiles: FileList | File[]): void {
  const dt = new DataTransfer();
  if (fileInput.files) {
    for (const existing of Array.from(fileInput.files)) dt.items.add(existing);
  }
  for (const file of Array.from(newFiles)) {
    if (file.type === "application/pdf" || /\.pdf$/i.test(file.name)) dt.items.add(file);
  }
  fileInput.files = dt.files;
  renderFileList();
}

dropZone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => renderFileList());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  e.stopPropagation();
  dropZone.classList.remove("dragover");
  if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
});

// Without these, dropping a file anywhere outside the exact drop-zone bounds
// (e.g. the modal isn't open yet) falls through to the browser's default
// behavior of navigating to/opening the file instead of doing nothing.
window.addEventListener("dragover", (e) => e.preventDefault());

window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (!e.dataTransfer?.files?.length) return;
  uploadModal.classList.remove("hidden");
  addFiles(e.dataTransfer.files);
});

modalCancel.addEventListener("click", () => {
  uploadModal.classList.add("hidden");
  fileInput.value = "";
  fileListEl.innerHTML = "";
});

modalUpload.addEventListener("click", () => {
  const files = fileInput.files;
  if (!files || files.length === 0) return;

  uploadModal.classList.add("hidden");
  uploadPanel.classList.remove("hidden");
  fileListEl.innerHTML = "";

  const formData = new FormData();
  formData.append("source_type", sourceTypeEl.value);
  const entries: { title: string; el: HTMLDivElement }[] = [];
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
    .then((data: { results: UploadResult[] }) => {
      for (const result of data.results) {
        const entry = entries.find((e) => e.title === result.title);
        if (!entry) continue;
        const statusEl = entry.el.querySelector(".status") as HTMLDivElement;
        statusEl.className = `status ${result.status}`;
        if (result.status === "success") {
          statusEl.textContent = `Added (${result.chunks} chunks)`;
        } else if (result.status === "skipped") {
          statusEl.textContent = `Skipped (${result.reason ?? ""})`;
        } else {
          statusEl.textContent = `Failed (${result.reason ?? ""})`;
        }
      }
    })
    .catch((err: Error) => {
      for (const entry of entries) {
        const statusEl = entry.el.querySelector(".status") as HTMLDivElement;
        statusEl.className = "status failed";
        statusEl.textContent = `Error: ${err.message}`;
      }
    });
});

// --- "See reference documents" tab ---

async function loadDocuments(): Promise<void> {
  docsListEl.textContent = "Loading...";
  try {
    const res = await fetch("/api/documents");
    const data = (await res.json()) as { documents: { title: string; source_type: string; chunks: number }[] };
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
  } catch (err) {
    docsListEl.textContent = `Could not load document list: ${(err as Error).message}`;
  }
}
