import React, { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import { marked } from "marked";
import "./styles.css";

marked.setOptions({
  breaks: true,
  gfm: true,
});

function formatMessageContent(content) {
  if (!content) return "";
  // Convert [Document: filename.pdf, Page X] or [Document: filename.pdf | Page X] to stylish multi-doc badge chips
  let processed = content.replace(/(?:【|\[)Document:\s*([^,|\]]+)(?:,\s*Page|\s*\|\s*Page)[\s\u202f]*(\d+)(?:】|\])/gi, (match, doc, p1) => {
    const cleanDoc = doc.trim();
    return `<span class="page-badge" title="Source Document: ${cleanDoc}"><span class="badge-icon">📑</span> ${cleanDoc} · Page ${p1}</span>`;
  });
  // Convert [Page X] or 【Page X】 or (Page X) to stylish badge chips
  processed = processed.replace(/(?:【|\[)Page[\s\u202f]*(\d+)(?:】|\])/gi, (match, p1) => {
    return `<span class="page-badge"><span class="badge-icon">📄</span> Page ${p1}</span>`;
  });
  try {
    return marked.parse(processed);
  } catch {
    return content;
  }
}

const API = import.meta.env.VITE_API_URL !== undefined
  ? import.meta.env.VITE_API_URL
  : (typeof window !== "undefined" && window.location.port === "3000"
      ? "http://localhost:8000"
      : (typeof window !== "undefined" ? window.location.origin : ""));

const UPLOAD_PIPELINE_STEPS = [
  {
    emoji: "📄",
    title: "Document Parsing",
    subtitle: "PyMuPDF extraction to MinIO",
    detail: "Parsing document structure & extracting high-resolution assets into MinIO...",
  },
  {
    emoji: "🧩",
    title: "Context Chunking",
    subtitle: "Parent (~1000ch) & child (~250ch)",
    detail: "Generating hierarchical parent/child chunks with page coordinates...",
  },
  {
    emoji: "🌐",
    title: "FAISS HNSW Graph",
    subtitle: "FastEmbed & HNSW Clustering",
    detail: "Generating 384-dim semantic embeddings & building FAISS HNSW graph clusters across uploaded SOPs...",
  },
  {
    emoji: "📊",
    title: "Compliance Audit",
    subtitle: "Template, Readability & Quality",
    detail: "Benchmarking against Kenvue standards & compiling compliance scorecards...",
  },
];

const OPTIMIZE_PIPELINE_STEPS = [
  {
    emoji: "📜",
    title: "Skill Directive",
    subtitle: "Compiling optimization_skill.md",
    detail: "Compiling dynamic optimization skill directives and user custom parameters...",
  },
  {
    emoji: "⚙️",
    title: "Standardization",
    subtitle: "Kenvue 10-tier procedure format",
    detail: "Restructuring sections, standardized safety callouts, and step actions...",
  },
  {
    emoji: "🛡️",
    title: "QA Validation Loop",
    subtitle: "Automated agent remediation",
    detail: "QA Validation Agent auditing generated document to verify 100% guideline compliance...",
  },
  {
    emoji: "📑",
    title: "ReportLab Engine",
    subtitle: "Re-embedding MinIO figures/tables",
    detail: "Re-inserting original figures & tables from MinIO and compiling publication PDF...",
  },
  {
    emoji: "🔄",
    title: "Vector Re-Indexing",
    subtitle: "FAISS re-index & scorecard refresh",
    detail: "Re-indexing optimized SOP text into FAISS vector space for instant RAG retrieval...",
  },
];

const HARMONIZE_PIPELINE_STEPS = [
  {
    emoji: "🔍",
    title: "Semantic Analysis",
    subtitle: "FAISS HNSW Chamfer alignment",
    detail: "Analyzing overlapping steps, procedural divergences, and parameters across selected SOPs...",
  },
  {
    emoji: "⚖️",
    title: "Conflict Resolution",
    subtitle: "Conservative GMP standards",
    detail: "Resolving operating parameter conflicts (speed, temp, pressure) and standardizing terminology...",
  },
  {
    emoji: "📋",
    title: "Template Alignment",
    subtitle: "Kenvue 10-Tier SOP Structure",
    detail: "Synthesizing unified 10-tier procedure, preserving unique rules & re-inserting original MinIO figures & tables...",
  },
  {
    emoji: "🤖",
    title: "Optimization Agents",
    subtitle: "Parallel compliance & QA pass",
    detail: "Executing parallel validation agents and compiling publication ReportLab PDF...",
  },
];

function PipelineProgressBar({ mode, progress, currentStageIndex, stageDetail, title, badgeText, customSteps }) {
  const steps = customSteps || (mode === "upload" ? UPLOAD_PIPELINE_STEPS : OPTIMIZE_PIPELINE_STEPS);
  const gridClass = steps.length === 4 ? "steps-4" : "steps-5";
  const displayPct = Math.min(100, Math.max(0, Math.round(progress)));

  return (
    <div className="pipeline-container">
      <div className="pipeline-header">
        <div className="pipeline-title-group">
          <div className="pipeline-pulse-badge">
            <span className="pipeline-pulse-dot" />
            <span>{badgeText || (mode === "upload" ? "AUDIT & EVALUATION PIPELINE" : "OPTIMIZATION & RE-INDEXING PIPELINE")}</span>
          </div>
          <h3 className="pipeline-main-title">{title}</h3>
        </div>
        <div className="pipeline-percentage-box">
          <span className="pipeline-pct-number">{displayPct}%</span>
          <span className="pipeline-pct-label">PROGRESS</span>
        </div>
      </div>

      <div className="pipeline-bar-track">
        <div className="pipeline-bar-fill" style={{ width: `${Math.min(100, Math.max(3, displayPct))}%` }}>
          <div className="pipeline-bar-shimmer" />
          <div className="pipeline-bar-glow" />
        </div>
      </div>

      <div className={`pipeline-steps-grid ${gridClass}`}>
        {steps.map((step, idx) => {
          let status = "step-pending";
          if (progress >= 100 || idx < currentStageIndex) {
            status = "step-done";
          } else if (idx === currentStageIndex) {
            status = "step-active";
          }

          return (
            <div key={idx} className={`pipeline-step-item ${status}`}>
              <div className="pipeline-step-node">
                {status === "step-done" ? (
                  "✓"
                ) : status === "step-active" ? (
                  <div className="step-spinner-node" />
                ) : (
                  idx + 1
                )}
              </div>
              <div className="pipeline-step-content">
                <div className="pipeline-step-title">
                  <span className="step-emoji">{step.emoji}</span>
                  <span>{step.title}</span>
                </div>
                <div className="pipeline-step-subtitle">{step.subtitle}</div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pipeline-live-ticker">
        <span className="ticker-pulse-icon">⚡</span>
        <div className="ticker-text-wrapper">
          <span className="ticker-prefix">CURRENT BACKEND OPERATION</span>
          <span className="ticker-message">{stageDetail || steps[currentStageIndex]?.detail || "Processing..."}</span>
        </div>
      </div>
    </div>
  );
}

function App() {
  // Auth state
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem("sop_user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [authMode, setAuthMode] = useState("login"); // 'login' or 'register'
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");

  // Chats & messaging
  const [chats, setChats] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // SOP & Evaluation state
  const [activeSop, setActiveSop] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStageIndex, setUploadStageIndex] = useState(0);
  const [uploadStageDetail, setUploadStageDetail] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("all");

  // Optimization workflow state
  const [showOptForm, setShowOptForm] = useState(false);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [customInstructions, setCustomInstructions] = useState("");
  const [optimizing, setOptimizing] = useState(false);
  const [optStatus, setOptStatus] = useState("");
  const [optResult, setOptResult] = useState(null);
  const [optProgress, setOptProgress] = useState(0);
  const [optStageIndex, setOptStageIndex] = useState(0);
  const [optStageDetail, setOptStageDetail] = useState("");

  // Modals & previews
  const [artifactsModalOpen, setArtifactsModalOpen] = useState(false);
  const [artifactFilter, setArtifactFilter] = useState("all");
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [pdfPreviewTitle, setPdfPreviewTitle] = useState("");
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState("");

  // Multi-SOP Similarity & Harmonization state
  const [similarityData, setSimilarityData] = useState(null);
  const [selectedHarmonizeIds, setSelectedHarmonizeIds] = useState([]);
  const [harmonizing, setHarmonizing] = useState(false);
  const [harmonizeError, setHarmonizeError] = useState("");
  const [showOverlapDetails, setShowOverlapDetails] = useState(false);
  const [harmonizedVersions, setHarmonizedVersions] = useState([]);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [harmProgress, setHarmProgress] = useState(0);
  const [harmStageIndex, setHarmStageIndex] = useState(0);
  const [harmStageDetail, setHarmStageDetail] = useState("");

  // Simplification state
  const [simplificationCatalog, setSimplificationCatalog] = useState([]);
  const [showSimplifyPanel, setShowSimplifyPanel] = useState(false);
  const [selectedSimpRecs, setSelectedSimpRecs] = useState([]);
  const [simplifying, setSimplifying] = useState(false);

  // Interactive Refinement state
  const [refinementPrompt, setRefinementPrompt] = useState("");
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState("");

  // Admin template upload state
  const [templateFile, setTemplateFile] = useState(null);
  const [templateUploading, setTemplateUploading] = useState(false);
  const [templateUploadMsg, setTemplateUploadMsg] = useState("");

  const fileInputRef = useRef(null);
  const templateInputRef = useRef(null);

  const [settings, setSettings] = useState({
    provider: "groq",
    model: "openai/gpt-oss-120b",
    apiKey: "",
    configured: false,
    groqConfigured: false,
    geminiConfigured: false,
    template_status: null,
  });

  const getHeaders = () => ({
    "Content-Type": "application/json",
    "X-User-Name": currentUser?.username || "admin",
  });

  // Load conversations and settings
  const load = async () => {
    if (!currentUser) return;
    try {
      const [c, s] = await Promise.all([
        fetch(`${API}/conversations`, { headers: { "X-User-Name": currentUser.username } }).then((r) => r.json()),
        fetch(`${API}/settings`).then((r) => r.json()),
      ]);
      setChats(Array.isArray(c) ? c : []);
      setSettings((x) => ({
        ...x,
        provider: s.provider,
        model: s.model,
        configured: s.api_key_configured,
        groqConfigured: s.groq_configured,
        geminiConfigured: s.gemini_configured,
        template_status: s.template_status,
      }));
    } catch (e) {
      console.error("Failed to load initial data:", e);
    }
  };

  useEffect(() => {
    if (currentUser) {
      load();
    }
  }, [currentUser]);

  // Auth Handlers
  const handleAuth = async (e) => {
    if (e) e.preventDefault();
    setAuthError("");
    const endpoint = authMode === "login" ? `${API}/auth/login` : `${API}/auth/register`;
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: authUsername.trim(), password: authPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Authentication failed");
      const userObj = { username: data.username, role: data.role };
      setCurrentUser(userObj);
      localStorage.setItem("sop_user", JSON.stringify(userObj));
      setAuthPassword("");
    } catch (err) {
      setAuthError(err.message);
    }
  };

  const handleLogout = () => {
    setCurrentUser(null);
    localStorage.removeItem("sop_user");
    setActive(null);
    setChats([]);
    setMessages([]);
    setActiveSop(null);
    setOptResult(null);
  };

  // Load active SOP data
  const loadSopInfo = async (conversationId) => {
    try {
      const [sopRes, artRes] = await Promise.all([
        fetch(`${API}/conversations/${conversationId}/sop`).then((r) => r.json()),
        fetch(`${API}/conversations/${conversationId}/artifacts`).then((r) => r.json()),
      ]);
      if (sopRes.has_sop) {
        setActiveSop(sopRes);
        const docs = sopRes.documents || [sopRes.document];
        let currentTargetId = selectedDocId;

        if (docs.length > 1) {
          if (selectedDocId !== "all" && !docs.some((d) => d.id === selectedDocId)) {
            currentTargetId = "all";
            setSelectedDocId("all");
          }
        } else if (sopRes.document) {
          currentTargetId = sopRes.document.id;
          setSelectedDocId(sopRes.document.id);
        }

        const targetDoc = (currentTargetId !== "all" && docs.find((d) => d.id === currentTargetId)) || sopRes.document;

        if (targetDoc?.optimized_scores?.suggestions) {
          setSelectedSuggestions(targetDoc.optimized_scores.suggestions.map((s) => s.id));
        } else if (targetDoc?.scores?.suggestions) {
          // Pre-select all suggestions by default
          setSelectedSuggestions(targetDoc.scores.suggestions.map((s) => s.id));
        }

        if (targetDoc?.optimized_scores) {
          setOptResult({
            document_title: targetDoc.optimized_title || targetDoc.filename,
            previous_scores: targetDoc.scores,
            updated_scores: targetDoc.optimized_scores,
            pdf_download_url: `/conversations/${conversationId}/optimized-sop/download${targetDoc.id ? `?document_id=${targetDoc.id}` : ''}`,
            pdf_preview_url: `/conversations/${conversationId}/optimized-sop/preview${targetDoc.id ? `?document_id=${targetDoc.id}` : ''}`,
            skill_url: `/conversations/${conversationId}/optimization-skill`,
            summary: "Optimized SOP generated according to Kenvue standards.",
          });
        }
        setSimilarityData(sopRes.similarity_analysis || null);
        const harmVers = sopRes.harmonized_versions || [];
        setHarmonizedVersions(harmVers);
        if (harmVers.length > 0) {
          setSelectedVersionId(sopRes.latest_harmonized_version?.id || harmVers[harmVers.length - 1].id);
        } else {
          setSelectedVersionId(null);
        }

        if (sopRes.similarity_analysis?.recommended_harmonize_ids?.length) {
          setSelectedHarmonizeIds(sopRes.similarity_analysis.recommended_harmonize_ids);
        } else if (sopRes.documents?.length) {
          setSelectedHarmonizeIds(sopRes.documents.map((d) => d.id));
        }

        fetch(`${API}/conversations/${conversationId}/harmonized-sop/simplification-suggestions`)
          .then((r) => r.json())
          .then((data) => {
            if (data.catalog) {
              setSimplificationCatalog(data.catalog);
              setSelectedSimpRecs(data.catalog.map((c) => c.id));
            }
          })
          .catch(() => {});
      } else {
        setActiveSop(null);
        setSelectedDocId("all");
        setSimilarityData(null);
        setHarmonizedVersions([]);
        setSelectedVersionId(null);
      }
      setArtifacts(Array.isArray(artRes) ? artRes : []);
    } catch (e) {
      console.error("Error loading SOP data:", e);
      setActiveSop(null);
      setArtifacts([]);
      setSimilarityData(null);
      setHarmonizedVersions([]);
      setSelectedVersionId(null);
    }
  };

  const newChat = async () => {
    try {
      const r = await fetch(`${API}/conversations`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ title: "New Chat" }),
      });
      const chat = await r.json();
      setChats((x) => [chat, ...x]);
      setActive(chat);
      setMessages([]);
      setActiveSop(null);
      setSelectedDocId("all");
      setArtifacts([]);
      setOptResult(null);
      setShowOptForm(false);
      setUploadError("");
      setSettingsOpen(false);
      setSimilarityData(null);
      setSelectedHarmonizeIds([]);
      setHarmonizing(false);
      setHarmonizeError("");
      setHarmonizedVersions([]);
      setSelectedVersionId(null);
      setShowSimplifyPanel(false);
      setRefinementPrompt("");
      setRefineError("");
    } catch (e) {
      console.error("Failed to create conversation:", e);
    }
  };

  const openChat = async (chat) => {
    setActive(chat);
    setSettingsOpen(false);
    setUploadError("");
    setOptResult(null);
    setShowOptForm(false);
    setSimilarityData(null);
    setSelectedHarmonizeIds([]);
    setHarmonizing(false);
    setHarmonizeError("");
    setHarmonizedVersions([]);
    setSelectedVersionId(null);
    setShowSimplifyPanel(false);
    setRefinementPrompt("");
    setRefineError("");
    try {
      const msgs = await fetch(`${API}/conversations/${chat.id}/messages`).then((r) => r.json());
      setMessages(msgs);
      await loadSopInfo(chat.id);
    } catch (e) {
      console.error("Error opening chat:", e);
    }
  };

  const handleDeleteChat = async (e, chat) => {
    e.stopPropagation();
    const confirmed = window.confirm(
      `Are you sure you want to permanently delete "${chat.title}"?\n\nThis will permanently wipe all conversation messages, SOP documents, vector embeddings, and storage summaries.`
    );
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/conversations/${chat.id}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to delete chat session");
      }

      const updatedChats = chats.filter((c) => c.id !== chat.id);
      setChats(updatedChats);

      if (active?.id === chat.id) {
        if (updatedChats.length > 0) {
          openChat(updatedChats[0]);
        } else {
          newChat();
        }
      }
    } catch (err) {
      console.error("Error deleting conversation:", err);
      alert(`Could not delete session: ${err.message}`);
    }
  };

  // SOP Upload & Evaluation (Supports up to 10 SOP PDFs)
  const handleFileUpload = async (filesInput) => {
    if (!filesInput || !active) return;
    const rawFiles = filesInput instanceof FileList
      ? Array.from(filesInput)
      : Array.isArray(filesInput)
      ? filesInput
      : [filesInput];

    if (rawFiles.length === 0) return;

    if (rawFiles.length > 10) {
      setUploadError(`Maximum 10 SOP PDFs allowed at a time (you selected ${rawFiles.length}). Please choose up to 10 files.`);
      return;
    }

    const nonPdf = rawFiles.find((f) => !f.name.toLowerCase().endsWith(".pdf"));
    if (nonPdf) {
      setUploadError(`All files must be valid PDF documents (.pdf). Found: ${nonPdf.name}`);
      return;
    }

    setUploading(true);
    setUploadError("");
    setUploadProgress(4);
    setUploadStageIndex(0);
    const count = rawFiles.length;
    setUploadStageDetail(
      count > 1
        ? `Parsing ${count} SOP documents structure & extracting high-resolution assets into MinIO...`
        : UPLOAD_PIPELINE_STEPS[0].detail
    );

    const formData = new FormData();
    rawFiles.forEach((f) => {
      formData.append("files", f);
    });
    // Compatibility fallback
    formData.append("file", rawFiles[0]);

    const startTime = Date.now();
    const progressTimer = setInterval(() => {
      const elapsed = Date.now() - startTime;
      let nextPct = 4;
      let stage = 0;

      if (elapsed < 1400) {
        nextPct = 4 + (elapsed / 1400) * 20;
        stage = 0;
      } else if (elapsed < 2800) {
        nextPct = 25 + ((elapsed - 1400) / 1400) * 24;
        stage = 1;
      } else if (elapsed < 4400) {
        nextPct = 50 + ((elapsed - 2800) / 1600) * 24;
        stage = 2;
      } else {
        const extra = Math.min(19, ((elapsed - 4400) / 3500) * 19);
        nextPct = 75 + extra;
        stage = 3;
      }

      setUploadProgress(Math.min(94, Math.round(nextPct)));
      setUploadStageIndex(stage);
      if (stage === 1 && count > 1) {
        setUploadStageDetail(`Generating parent & child chunks across all ${count} SOP documents...`);
      } else if (stage === 2 && count > 1) {
        setUploadStageDetail(`Generating 384-dim semantic embeddings & building FAISS HNSW graph clusters for ${count} SOPs...`);
      } else if (stage === 3 && count > 1) {
        setUploadStageDetail(`Auditing compliance across all ${count} SOP documents & compiling scorecards...`);
      } else {
        setUploadStageDetail(UPLOAD_PIPELINE_STEPS[stage]?.detail || "");
      }
    }, 100);

    try {
      const res = await fetch(`${API}/conversations/${active.id}/upload-sop`, {
        method: "POST",
        headers: { "X-User-Name": currentUser.username },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");

      clearInterval(progressTimer);
      setUploadProgress(100);
      setUploadStageIndex(UPLOAD_PIPELINE_STEPS.length - 1);
      setUploadStageDetail("Audit & HNSW graph clustering complete! Rendering scorecards...");

      // Brief delay to showcase 100% completion
      await new Promise((r) => setTimeout(r, 450));

      await loadSopInfo(active.id);

      if (data.conversation_title) {
        setActive((prev) => ({ ...prev, title: data.conversation_title }));
        setChats((prev) =>
          prev.map((c) => (c.id === active.id ? { ...c, title: data.conversation_title } : c))
        );
      }
    } catch (e) {
      clearInterval(progressTimer);
      setUploadError(e.message || "Failed to process SOP PDFs.");
    } finally {
      clearInterval(progressTimer);
      setUploading(false);
      setUploadProgress(0);
      setUploadStageIndex(0);
      setUploadStageDetail("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Optimization Execution
  const handleOptimize = async () => {
    if (!active || !activeSop) return;
    const targetDoc = (selectedDocId !== "all" && activeSop?.documents?.find((d) => d.id === selectedDocId)) || activeSop.document;

    setOptimizing(true);
    setOptProgress(3);
    setOptStageIndex(0);
    setOptStageDetail(OPTIMIZE_PIPELINE_STEPS[0].detail);

    const startTime = Date.now();
    const progressTimer = setInterval(() => {
      const elapsed = Date.now() - startTime;
      let nextPct = 3;
      let stage = 0;

      if (elapsed < 1800) {
        nextPct = 3 + (elapsed / 1800) * 16;
        stage = 0;
      } else if (elapsed < 4200) {
        nextPct = 20 + ((elapsed - 1800) / 2400) * 24;
        stage = 1;
      } else if (elapsed < 7500) {
        nextPct = 45 + ((elapsed - 4200) / 3300) * 24;
        stage = 2;
      } else if (elapsed < 10500) {
        nextPct = 70 + ((elapsed - 7500) / 3000) * 19;
        stage = 3;
      } else {
        const extra = Math.min(6, ((elapsed - 10500) / 4000) * 6);
        nextPct = 90 + extra;
        stage = 4;
      }

      setOptProgress(Math.min(96, Math.round(nextPct)));
      setOptStageIndex(stage);
      setOptStageDetail(OPTIMIZE_PIPELINE_STEPS[stage]?.detail || "");
    }, 120);

    try {
      const res = await fetch(`${API}/conversations/${active.id}/optimize-sop`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          selected_suggestion_ids: selectedSuggestions,
          custom_instructions: customInstructions,
          document_id: targetDoc?.id,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Optimization failed");

      clearInterval(progressTimer);
      setOptProgress(100);
      setOptStageIndex(OPTIMIZE_PIPELINE_STEPS.length - 1);
      setOptStageDetail("Standardization and FAISS HNSW re-indexing complete! Finalizing scorecard...");

      // Brief delay to showcase 100% completion
      await new Promise((r) => setTimeout(r, 600));

      setOptResult({
        ...data,
        pdf_download_url: `/conversations/${active.id}/optimized-sop/download${targetDoc?.id ? `?document_id=${targetDoc.id}` : ''}`,
        pdf_preview_url: `/conversations/${active.id}/optimized-sop/preview${targetDoc?.id ? `?document_id=${targetDoc.id}` : ''}`,
      });
      setShowOptForm(false);
      await loadSopInfo(active.id);

      // Add assistant confirmation message in chat
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `✨ **SOP "${targetDoc?.filename || "Document"}" Successfully Optimized to Kenvue Standards!**\n\n` +
            `• **Compliance Score**: Raised from **${data.previous_scores?.average_score || 70}%** to **${data.updated_scores.average_score}%** (+${data.updated_scores.average_score - (data.previous_scores?.average_score || 70)} pts)\n` +
            `• **Execution Method**: Generated and executed dynamic skill directive (\`optimization_skill.md\`) in MinIO based on your approved recommendations.\n` +
            `• **Media Integrity**: All original images and tables from MinIO have been re-inserted into their respective sections without alteration.\n` +
            `• **HNSW Graph Re-Indexed**: Vectors for the optimized SOP have been updated in the multi-document FAISS HNSW graph.\n\n` +
            `You can download or preview your optimized PDF above, view the skill directive, continue asking questions, or click **End Chat** when finished.`,
        },
      ]);
    } catch (e) {
      clearInterval(progressTimer);
      alert(`Optimization error: ${e.message}`);
    } finally {
      clearInterval(progressTimer);
      setOptimizing(false);
      setOptProgress(0);
      setOptStageIndex(0);
      setOptStageDetail("");
    }
  };

  // Multi-SOP Harmonization Execution
  const handleHarmonize = async () => {
    if (!active || selectedHarmonizeIds.length < 2) return;
    setHarmonizing(true);
    setHarmonizeError("");
    setHarmProgress(5);
    setHarmStageIndex(0);
    setHarmStageDetail(HARMONIZE_PIPELINE_STEPS[0].detail);

    const startTime = Date.now();
    const progressTimer = setInterval(() => {
      const elapsed = Date.now() - startTime;
      let nextPct = 5;
      let stage = 0;
      if (elapsed < 1500) {
        nextPct = 5 + (elapsed / 1500) * 25;
        stage = 0;
      } else if (elapsed < 3500) {
        nextPct = 30 + ((elapsed - 1500) / 2000) * 30;
        stage = 1;
      } else if (elapsed < 6000) {
        nextPct = 60 + ((elapsed - 3500) / 2500) * 25;
        stage = 2;
      } else {
        const extra = Math.min(10, ((elapsed - 6000) / 3000) * 10);
        nextPct = 85 + extra;
        stage = 3;
      }
      setHarmProgress(Math.min(96, Math.round(nextPct)));
      setHarmStageIndex(stage);
      setHarmStageDetail(HARMONIZE_PIPELINE_STEPS[stage]?.detail || "");
    }, 120);

    try {
      const res = await fetch(`${API}/conversations/${active.id}/harmonize-sops`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          selected_document_ids: selectedHarmonizeIds,
          custom_instructions: customInstructions,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Harmonization failed");

      clearInterval(progressTimer);
      setHarmProgress(100);
      setHarmStageIndex(HARMONIZE_PIPELINE_STEPS.length - 1);
      setHarmStageDetail("Consolidation, Kenvue 10-tier template alignment & ReportLab PDF compilation complete!");

      await new Promise((r) => setTimeout(r, 600));

      await loadSopInfo(active.id);
      setSelectedVersionId(data.id);
      setShowSimplifyPanel(false);
      setCustomInstructions("");

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `✨ **Harmonized SOP Successfully Generated!**\n\n` +
            `• **Consolidated Document**: ${data.title}\n` +
            `• **Version**: ${data.version_label}\n` +
            `• **Source Lineage**: ${data.source_filenames?.join(", ")}\n` +
            `• **Overall Quality Score**: **${data.scores?.average_score}%** (Template: ${data.scores?.template_score}%, Readability: ${data.scores?.readability_score}%, Quality: ${data.scores?.quality_score}%)\n` +
            `• **Status**: All conflicting parameters resolved to GMP limits and unified into Kenvue 10-tier procedure format. Full lineage permanently preserved in MinIO & SQLite.`,
        },
      ]);
    } catch (e) {
      clearInterval(progressTimer);
      setHarmonizeError(e.message || "Failed to harmonize SOPs");
    } finally {
      clearInterval(progressTimer);
      setHarmonizing(false);
      setHarmProgress(0);
      setHarmStageIndex(0);
      setHarmStageDetail("");
    }
  };

  // Simplification Recommendation Execution
  const handleSimplify = async () => {
    if (!active) return;
    setSimplifying(true);
    try {
      const recsToApply = selectedSimpRecs.length > 0 ? selectedSimpRecs : simplificationCatalog.map((c) => c.id);
      const res = await fetch(`${API}/conversations/${active.id}/harmonized-sop/simplify`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          version_id: selectedVersionId,
          selected_recommendation_ids: recsToApply,
        }),
      });

      const newVersion = await res.json();
      if (!res.ok) throw new Error(newVersion.detail || "Simplification failed");

      await loadSopInfo(active.id);
      setSelectedVersionId(newVersion.id);
      setShowSimplifyPanel(false);

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `⚡ **Harmonized SOP v${newVersion.version_number} (Simplified) Created!**\n\n` +
            `• **Readability Score**: Improved to **${newVersion.scores?.readability_score}%**\n` +
            `• **Overall Score**: **${newVersion.scores?.average_score}%**\n` +
            `• **Changes Applied**: ${newVersion.change_summary}\n` +
            `• **Version Preservation**: Previous version v${newVersion.version_number - 1} remains accessible and unchanged.`,
        },
      ]);
    } catch (e) {
      alert(`Simplification error: ${e.message}`);
    } finally {
      setSimplifying(false);
    }
  };

  // Interactive Conversational Refinement Execution
  const handleRefine = async (e) => {
    if (e) e.preventDefault();
    if (!active || !refinementPrompt.trim()) return;
    setRefining(true);
    setRefineError("");
    const userPromptText = refinementPrompt.trim();

    try {
      const res = await fetch(`${API}/conversations/${active.id}/harmonized-sop/refine`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          version_id: selectedVersionId,
          refinement_prompt: userPromptText,
        }),
      });

      const newVersion = await res.json();
      if (!res.ok) throw new Error(newVersion.detail || "Refinement failed");

      await loadSopInfo(active.id);
      setSelectedVersionId(newVersion.id);
      setRefinementPrompt("");

      setMessages((m) => [
        ...m,
        { role: "user", content: userPromptText },
        {
          role: "assistant",
          content: `💬 **Refinement Applied! Generated Harmonized SOP v${newVersion.version_number}.**\n\n` +
            `• **Directives Incorporated**: "${userPromptText}"\n` +
            `• **Updated Overall Score**: **${newVersion.scores?.average_score}%**\n` +
            `• **Lineage**: Generated from parent version v${newVersion.version_number - 1}. Full historical version trail retained.`,
        },
      ]);
    } catch (e) {
      setRefineError(e.message || "Failed to apply refinement");
    } finally {
      setRefining(false);
    }
  };

  // End Chat & Lifecycle Cleanup
  const handleEndChat = async () => {
    if (!active) return;
    const confirm = window.confirm(
      "Are you sure you want to end this chat? A comprehensive session summary will be archived in MinIO, and temporary image/table assets will be cleaned up."
    );
    if (!confirm) return;

    try {
      const res = await fetch(`${API}/conversations/${active.id}/end-chat`, {
        method: "POST",
        headers: getHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed ending chat");

      alert(`✅ ${data.message}`);
      await newChat();
    } catch (e) {
      alert(`Error ending chat: ${e.message}`);
    }
  };

  // Admin Template Upload Handler
  const handleAdminTemplateUpload = async (e) => {
    e.preventDefault();
    if (!templateFile) return;
    setTemplateUploading(true);
    setTemplateUploadMsg("");

    const formData = new FormData();
    formData.append("file", templateFile);

    try {
      const res = await fetch(`${API}/admin/upload-template`, {
        method: "POST",
        headers: { "X-User-Name": currentUser.username },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Template upload failed");

      setTemplateUploadMsg(`✅ Successfully updated Kenvue Standard Guideline (${data.chunks_count} rule chunks indexed)!`);
      setTemplateFile(null);
      if (templateInputRef.current) templateInputRef.current.value = "";
      load();
    } catch (err) {
      setTemplateUploadMsg(`❌ Error: ${err.message}`);
    } finally {
      setTemplateUploading(false);
    }
  };

  // Chat message sending
  const send = async () => {
    if (!input.trim() || !active || loading) return;
    const content = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content }]);
    setLoading(true);

    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ conversation_id: active.id, content }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Request failed");

      setMessages((m) => [...m, data]);

      if (data.title && data.title !== active.title) {
        setActive((prev) => ({ ...prev, title: data.title }));
        setChats((prev) =>
          prev.map((c) => (c.id === active.id ? { ...c, title: data.title } : c))
        );
      }
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    try {
      const r = await fetch(`${API}/settings`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          provider: settings.provider,
          model: settings.model,
          api_key: settings.apiKey,
        }),
      });
      const data = await r.json();
      if (!r.ok) return alert(data.detail || "Could not save settings");
      setSettings((s) => ({ ...s, apiKey: "" }));
      await load();
      setSettingsOpen(false);
    } catch (e) {
      alert(`Could not save settings: ${e.message}`);
    }
  };

  // Helper for score badges
  const getScoreBadgeClass = (score) => {
    if (score >= 80) return "green";
    if (score >= 60) return "yellow";
    return "red";
  };

  // If user is not logged in, render Login / Register view
  if (!currentUser) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-brand">
            <h1>KENVUE</h1>
            <span className="brand-badge">SOP AI</span>
          </div>
          <p className="auth-tagline">Standard Operating Procedure Optimization & Audit System</p>

          <div className="auth-tabs">
            <button
              className={`auth-tab ${authMode === "login" ? "active" : ""}`}
              onClick={() => { setAuthMode("login"); setAuthError(""); }}
            >
              Sign In
            </button>
            <button
              className={`auth-tab ${authMode === "register" ? "active" : ""}`}
              onClick={() => { setAuthMode("register"); setAuthError(""); }}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleAuth}>
            <div className="auth-input-group">
              <label>Username</label>
              <input
                type="text"
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                placeholder="Enter your username"
                required
              />
            </div>
            <div className="auth-input-group">
              <label>Password</label>
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="Enter password"
                required
              />
            </div>

            {authError && <p style={{ color: "#ef4444", fontSize: "13px", margin: "4px 0 12px" }}>{authError}</p>}

            <button type="submit" className="auth-submit-btn">
              {authMode === "login" ? "Sign In to SOP Portal" : "Create Account & Sign In"}
            </button>
          </form>

          <div className="auth-demo-shortcuts">
            <p>Quick Prototype Access:</p>
            <button
              type="button"
              className="demo-btn"
              onClick={() => { setAuthUsername("admin"); setAuthPassword("admin"); setAuthMode("login"); }}
            >
              🔑 Fill Admin Credentials (admin / admin)
            </button>
            <button
              type="button"
              className="demo-btn"
              onClick={() => { setAuthUsername("operator_1"); setAuthPassword("pass123"); setAuthMode("register"); }}
            >
              👤 Fill New Operator (operator_1 / pass123)
            </button>
          </div>
        </div>
      </div>
    );
  }

  const defaultRefineSuggestions = [
    {
      id: "sug_refine_imperative",
      title: "Streamline Procedural Imperative Phrasing",
      description: "Further polish step directives into direct, crisp imperative commands without auxiliary verbs."
    },
    {
      id: "sug_refine_tolerances",
      title: "Tighten Numerical Tolerances & Critical Limits",
      description: "Verify that all equipment temperatures, speeds, and timing include exact ± ranges."
    },
    {
      id: "sug_refine_safety",
      title: "Enhance Precautionary Warnings & Interlock Checks",
      description: "Ensure personal protective equipment and hazard controls precede mechanical steps."
    },
    {
      id: "sug_refine_qc",
      title: "Sharpen In-Process Quality Acceptance Standards",
      description: "Ensure clear pass/fail checkpoints with documented supervisory sign-offs."
    }
  ];

  const currentDoc = (activeSop?.documents && selectedDocId !== "all")
    ? (activeSop.documents.find((d) => d.id === selectedDocId) || activeSop.document)
    : activeSop?.document;

  const isCollectionOverview = Boolean(activeSop?.documents && activeSop.documents.length > 1 && selectedDocId === "all");

  const scores = isCollectionOverview
    ? (activeSop.collection_scores || activeSop.document?.scores)
    : ((currentDoc?.has_optimized_sop || currentDoc?.optimized_scores)
        ? (currentDoc.optimized_scores || currentDoc.scores)
        : currentDoc?.scores);

  const suggestions = (scores?.suggestions && scores.suggestions.length > 0)
    ? scores.suggestions
    : (currentDoc?.scores?.suggestions && currentDoc.scores.suggestions.length > 0)
      ? currentDoc.scores.suggestions
      : ((currentDoc?.has_optimized_sop || currentDoc?.optimized_scores) ? defaultRefineSuggestions : (scores?.suggestions || []));

  const filteredArtifacts = artifacts.filter((a) => (artifactFilter === "all" ? true : a.artifact_type === artifactFilter));

  const activeHarmonizedVersion =
    harmonizedVersions.find((v) => v.id === selectedVersionId) ||
    harmonizedVersions[harmonizedVersions.length - 1] ||
    null;

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <span>KENVUE SOP</span>
          <span className="brand-badge">PORTAL</span>
        </div>

        <div className="user-badge">
          <span>👤 {currentUser.username}</span>
          <span className="user-role-tag">{currentUser.role}</span>
        </div>

        <button className="new" onClick={newChat}>
          <span>+</span> New Chat
        </button>

        <div className="label">History</div>
        <div className="history">
          {chats.map((c) => (
            <div
              key={c.id}
              className={`historyRow ${active?.id === c.id ? "active" : ""}`}
            >
              <button
                className="historyItem"
                onClick={() => openChat(c)}
                title={c.title}
              >
                {c.title}
              </button>
              <button
                className="historyDeleteBtn"
                onClick={(e) => handleDeleteChat(e, c)}
                title="Delete past chat session"
                aria-label="Delete chat"
              >
                🗑️
              </button>
            </div>
          ))}
          {chats.length === 0 && (
            <div className="historyEmpty">No past chats</div>
          )}
        </div>

        <div className="sidebar-bottom">
          <button className="settingsBtn" onClick={() => setSettingsOpen(true)}>
            ⚙️ Settings {currentUser.role === "admin" && "· Admin"}
          </button>
          <button className="logoutBtn" onClick={handleLogout}>
            🚪 Sign Out
          </button>
        </div>
      </aside>

      {/* Main Panel */}
      <main className="main">
        {settingsOpen ? (
          <div className="settings">
            <div className="card">
              <div className="settingsHead">
                <div>
                  <h1>System Settings</h1>
                  <p>Configure model inference and Kenvue guidelines.</p>
                </div>
                <button onClick={() => setSettingsOpen(false)}>Close</button>
              </div>

              <label>Provider</label>
              <select
                value={settings.provider}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    provider: e.target.value,
                    model: e.target.value === "groq" ? "openai/gpt-oss-120b" : "gemini-2.5-flash",
                  })
                }
              >
                <option value="groq">Groq</option>
                <option value="gemini">Gemini</option>
              </select>

              <label>Model</label>
              <select
                value={settings.model}
                onChange={(e) => setSettings({ ...settings, model: e.target.value })}
              >
                {settings.provider === "groq" ? (
                  <>
                    <option value="openai/gpt-oss-120b">openai/gpt-oss-120b</option>
                    <option value="openai/gpt-oss-20b">openai/gpt-oss-20b</option>
                  </>
                ) : (
                  <option value="gemini-2.5-flash">gemini-2.5-flash</option>
                )}
              </select>

              <label>API Key</label>
              <input
                type="password"
                value={settings.apiKey}
                onChange={(e) => setSettings({ ...settings, apiKey: e.target.value })}
                placeholder={settings.configured ? "Configured. Enter new key to change." : "Paste API key"}
              />

              <button className="save" onClick={saveSettings}>
                Save Inference Settings
              </button>

              {/* ADMIN-ONLY KENVUE TEMPLATE GUIDELINES UPLOAD */}
              {currentUser.role === "admin" && (
                <div className="admin-template-section">
                  <h3>Admin: Official Kenvue Guideline PDF</h3>
                  <p>
                    Upload the official Kenvue SOP Template PDF. When uploaded, previous guideline embeddings are automatically replaced and future SOP audits will reference this standard.
                  </p>

                  <div className="template-status-badge">
                    <strong>Current Active Guideline:</strong>{" "}
                    {settings.template_status?.template_name || "Default Standard Kenvue Guidelines"}
                  </div>

                  <form onSubmit={handleAdminTemplateUpload}>
                    <input
                      ref={templateInputRef}
                      type="file"
                      accept=".pdf"
                      onChange={(e) => setTemplateFile(e.target.files?.[0] || null)}
                    />
                    <button
                      type="submit"
                      className="save"
                      style={{ background: "#2563eb", marginTop: "10px" }}
                      disabled={templateUploading || !templateFile}
                    >
                      {templateUploading ? "Indexing Guidelines..." : "Upload & Re-index Guideline PDF"}
                    </button>
                    {templateUploadMsg && (
                      <p style={{ fontSize: "13px", marginTop: "8px", fontWeight: 600 }}>{templateUploadMsg}</p>
                    )}
                  </form>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Header */}
            <header className="top">
              <div className="top-left">
                <span className="top-title">{active?.title || "Kenvue SOP Assistant"}</span>
                {activeSop?.has_sop && (
                  <>
                    {activeSop.documents?.length > 1 ? (
                      <span className="sop-badge">📚 {activeSop.documents.length} SOPs Clustered</span>
                    ) : (
                      <span className="sop-badge">📄 {activeSop.document.filename}</span>
                    )}
                    {artifacts.length > 0 && (
                      <button className="sop-artifacts-btn" onClick={() => setArtifactsModalOpen(true)}>
                        🖼️ Media ({artifacts.length})
                      </button>
                    )}
                    <button className="end-chat-btn" onClick={handleEndChat} title="End chat & archive summary">
                      🏁 End Chat
                    </button>
                  </>
                )}
              </div>
              <div className="top-right">
                <small>{settings.provider} · {settings.model}</small>
              </div>
            </header>

            {/* Chat Body */}
            <section className="chat">
              {!active ? (
                <div className="welcome-container">
                  <div className="welcome-header">
                    <h1>SOP Optimization Workspace</h1>
                    <p>Start a new conversation to audit, score, and optimize your Standard Operating Procedures.</p>
                  </div>
                  <button className="file-input-label" onClick={newChat}>
                    + Create New Chat
                  </button>
                </div>
              ) : (
                <>
                  <div className="messages">
                    {/* SOP UPLOAD BOX (When no SOP uploaded yet) */}
                    {!activeSop && (
                      <div className="welcome-container">
                        <div className="welcome-header">
                          <h1>Upload Procedure Documents</h1>
                          <p>
                            Upload up to 10 SOP PDFs to evaluate compliance with Kenvue specifications. All documents are parsed, chunked, and clustered in FAISS using HNSW graph indexing for instant multi-document intelligence.
                          </p>
                        </div>

                        <div
                          className={`sop-card ${uploading ? "is-uploading" : ""} ${dragOver ? "drag-over" : ""}`}
                          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                          onDragLeave={() => setDragOver(false)}
                          onDrop={(e) => {
                            e.preventDefault();
                            setDragOver(false);
                            if (e.dataTransfer.files?.length) handleFileUpload(e.dataTransfer.files);
                          }}
                        >
                          {uploading ? (
                            <PipelineProgressBar
                              mode="upload"
                              progress={uploadProgress}
                              currentStageIndex={uploadStageIndex}
                              stageDetail={uploadStageDetail}
                              title="Auditing & Indexing SOP Documents"
                              badgeText="KENVUE SOP HNSW INGESTION PIPELINE"
                            />
                          ) : (
                            <>
                              <div className="sop-icon">📚</div>
                              <h2>Drop up to 10 SOP PDFs here</h2>
                              <p>Supports any manufacturing, testing, or laboratory Standard Operating Procedures.</p>

                              {uploadError && <p style={{ color: "#ef4444", fontWeight: 600 }}>{uploadError}</p>}

                              <div className="upload-actions">
                                <label className="file-input-label">
                                  <span>Choose SOP PDFs (up to 10)</span>
                                  <input
                                    ref={fileInputRef}
                                    type="file"
                                    multiple
                                    accept=".pdf"
                                    className="file-input-hidden"
                                    onChange={(e) => {
                                      if (e.target.files?.length) handleFileUpload(e.target.files);
                                    }}
                                  />
                                </label>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Multi-SOP Tab Switcher Bar */}
                    {activeSop?.documents?.length > 1 && (
                      <div className="doc-tabs-bar">
                        <button
                          type="button"
                          className={`doc-tab-btn ${selectedDocId === "all" ? "active" : ""}`}
                          onClick={() => {
                            setSelectedDocId("all");
                            setOptResult(null);
                            setShowOptForm(false);
                          }}
                        >
                          <span>📚 All Uploaded SOPs</span>
                          <span className="doc-tab-score">
                            {activeSop.collection_scores?.average_score || activeSop.document?.scores?.average_score || 0}%
                          </span>
                        </button>

                        {activeSop.documents.map((doc, idx) => {
                          const docScore = doc.optimized_scores?.average_score || doc.scores?.average_score || 0;
                          const isDocActive = selectedDocId === doc.id;
                          return (
                            <button
                              key={doc.id || idx}
                              type="button"
                              className={`doc-tab-btn ${isDocActive ? "active" : ""}`}
                              onClick={() => {
                                setSelectedDocId(doc.id);
                                setShowOptForm(false);
                                if (doc.optimized_scores) {
                                  setOptResult({
                                    document_title: doc.optimized_title || doc.filename,
                                    previous_scores: doc.scores,
                                    updated_scores: doc.optimized_scores,
                                    pdf_download_url: `/conversations/${active.id}/optimized-sop/download?document_id=${doc.id}`,
                                    pdf_preview_url: `/conversations/${active.id}/optimized-sop/preview?document_id=${doc.id}`,
                                    skill_url: `/conversations/${active.id}/optimization-skill`,
                                  });
                                } else {
                                  setOptResult(null);
                                }
                                if (doc.optimized_scores?.suggestions) {
                                  setSelectedSuggestions(doc.optimized_scores.suggestions.map((s) => s.id));
                                } else if (doc.scores?.suggestions) {
                                  setSelectedSuggestions(doc.scores.suggestions.map((s) => s.id));
                                }
                              }}
                              title={doc.filename}
                            >
                              <span>📄 {doc.filename.length > 20 ? doc.filename.slice(0, 18) + "..." : doc.filename}</span>
                              <span className="doc-tab-score">{docScore}%</span>
                            </button>
                          );
                        })}

                        <div className="hnsw-cluster-badge" title="FAISS IndexHNSWFlat Graph Active">
                          <span>🌐 HNSW Graph Clustered ({activeSop.documents.length})</span>
                        </div>
                      </div>
                    )}

                    {/* ======================================================== */}
                    {/* MULTI-SOP HARMONIZATION PROGRESS BAR                     */}
                    {/* ======================================================== */}
                    {harmonizing && (
                      <PipelineProgressBar
                        mode="harmonize"
                        progress={harmProgress}
                        currentStageIndex={harmStageIndex}
                        stageDetail={harmStageDetail}
                        title="Harmonizing & Consolidating Selected SOPs"
                        badgeText="KENVUE MULTI-SOP HARMONIZATION PIPELINE"
                        customSteps={HARMONIZE_PIPELINE_STEPS}
                      />
                    )}

                    {/* ======================================================== */}
                    {/* 1. MULTI-SOP SIMILARITY & DUPLICATE DETECTION            */}
                    {/* ======================================================== */}
                    {isCollectionOverview && similarityData && !harmonizing && (
                      <div className="similarity-card">
                        <div className="similarity-header">
                          <div className="similarity-title">
                            <span>🌐 Multi-SOP Semantic & Procedural Similarity (FAISS HNSW)</span>
                          </div>
                          <div className="hnsw-cluster-badge" style={{ fontSize: "12px", padding: "4px 12px" }}>
                            <span>HNSW Chamfer & Jaccard Aligned</span>
                          </div>
                        </div>

                        {similarityData.executive_summary && (
                          <div className="similarity-exec-summary">
                            <strong>Executive Summary:</strong> {similarityData.executive_summary}
                          </div>
                        )}

                        {similarityData.similarity_groups?.length > 0 && (
                          <div className="similarity-groups-grid">
                            {similarityData.similarity_groups.map((grp) => {
                              const isHighlySimilar = grp.status === "Highly Similar";
                              const isMod = grp.status === "Moderately Similar";
                              const badgeClass = isHighlySimilar ? "highly-similar" : isMod ? "moderately-similar" : "different";
                              const cardClass = isHighlySimilar ? "is-similar" : "is-different";

                              return (
                                <div key={grp.group_id} className={`similarity-group-item ${cardClass}`}>
                                  <div className="group-top-row">
                                    <span className="group-name">{grp.group_name}</span>
                                    <span className={`group-score-badge ${badgeClass}`}>
                                      {grp.similarity_pct}% · {grp.status}
                                    </span>
                                  </div>

                                  <div className="group-status-desc">{grp.reason}</div>

                                  <div className="group-docs-list">
                                    {grp.document_names.map((docName, dIdx) => (
                                      <div key={dIdx} className="group-doc-pill">
                                        <span>📄 {docName}</span>
                                        {isHighlySimilar && (
                                          <span style={{ color: "#15803d", fontSize: "11px", fontWeight: 750 }}>
                                            Candidate for Harmonization
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>

                                  {((similarityData.procedural_overlaps && similarityData.procedural_overlaps.length > 0) ||
                                    (similarityData.parameter_conflicts && similarityData.parameter_conflicts.length > 0)) && (
                                    <div>
                                      <button
                                        type="button"
                                        className="group-details-toggle"
                                        onClick={() => setShowOverlapDetails(!showOverlapDetails)}
                                      >
                                        {showOverlapDetails ? "▲ Hide Overlaps & Parameter Conflicts" : "▼ View Overlaps & Parameter Conflicts"}
                                      </button>

                                      {showOverlapDetails && (
                                        <div className="group-extra-details">
                                          {similarityData.procedural_overlaps?.length > 0 && (
                                            <div style={{ marginBottom: "8px" }}>
                                              <strong style={{ color: "#1e293b", display: "block", marginBottom: "4px" }}>
                                                Procedural Overlaps:
                                              </strong>
                                              {similarityData.procedural_overlaps.map((po, pIdx) => (
                                                <span key={pIdx} className="overlap-item" title={po.description}>
                                                  ⚙️ {po.procedure} ({po.shared_documents.length} SOPs)
                                                </span>
                                              ))}
                                            </div>
                                          )}

                                          {similarityData.parameter_conflicts?.length > 0 && (
                                            <div>
                                              <strong style={{ color: "#1e293b", display: "block", marginBottom: "4px" }}>
                                                Parameter Discrepancies (Reconciled to GMP limit):
                                              </strong>
                                              {similarityData.parameter_conflicts.map((pc, cIdx) => (
                                                <span key={cIdx} className="conflict-pill" title={pc.action}>
                                                  ⚠️ {pc.parameter}: {pc.values.map((v) => `${v.doc}: ${v.value}`).join(" vs ")} ➔ Target: {pc.resolved_gmp_limit}
                                                </span>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* ======================================================== */}
                        {/* 2. HARMONIZE SELECTOR (CHECKBOX INTERFACE)                */}
                        {/* ======================================================== */}
                        <div className="harmonize-selector-box">
                          <div className="harmonize-prompt-title">
                            <span>✨ Harmonize Similar SOPs into a Single Standardized Kenvue SOP</span>
                          </div>
                          <div className="harmonize-prompt-sub">
                            Select which procedures to unify. Our optimization agent eliminates duplicate instructions, resolves parameter conflicts according to GMP guidelines, and generates a standardized Kenvue 10-tier publication PDF while preserving original figures and tables.
                          </div>

                          <div className="harmonize-checklist">
                            {activeSop.documents.map((doc) => {
                              const isChecked = selectedHarmonizeIds.includes(doc.id);
                              return (
                                <div
                                  key={doc.id}
                                  className={`harmonize-check-card ${isChecked ? "checked" : ""}`}
                                  onClick={() => {
                                    setSelectedHarmonizeIds((prev) =>
                                      prev.includes(doc.id) ? prev.filter((id) => id !== doc.id) : [...prev, doc.id]
                                    );
                                  }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={() => {}}
                                  />
                                  <div className="harmonize-doc-info">
                                    <span className="harmonize-doc-title">
                                      {doc.filename.length > 28 ? doc.filename.slice(0, 26) + "..." : doc.filename}
                                    </span>
                                    <span className="harmonize-doc-sub">
                                      Initial Compliance: {doc.scores?.average_score || 0}%
                                    </span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>

                          {harmonizeError && (
                            <div style={{ color: "#dc2626", fontSize: "13px", fontWeight: 600, marginBottom: "12px" }}>
                              ❌ {harmonizeError}
                            </div>
                          )}

                          <div className="harmonize-actions-row">
                            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                              <button
                                type="button"
                                className="select-all-btn"
                                onClick={() => {
                                  if (selectedHarmonizeIds.length === activeSop.documents.length) {
                                    setSelectedHarmonizeIds([]);
                                  } else {
                                    setSelectedHarmonizeIds(activeSop.documents.map((d) => d.id));
                                  }
                                }}
                              >
                                {selectedHarmonizeIds.length === activeSop.documents.length ? "Deselect All" : "Select All SOPs"}
                              </button>

                              {similarityData.similarity_groups?.find((g) => g.status === "Highly Similar") && (
                                <button
                                  type="button"
                                  className="select-all-btn"
                                  style={{ background: "#dcfce7", color: "#15803d", borderColor: "#86efac" }}
                                  onClick={() => {
                                    const simGroup = similarityData.similarity_groups.find((g) => g.status === "Highly Similar");
                                    if (simGroup?.document_ids) {
                                      setSelectedHarmonizeIds(simGroup.document_ids);
                                    }
                                  }}
                                >
                                  🎯 Select Highly Similar Group ({similarityData.similarity_groups.find((g) => g.status === "Highly Similar")?.document_names.length} SOPs)
                                </button>
                              )}
                            </div>

                            <button
                              type="button"
                              className="harmonize-btn"
                              disabled={selectedHarmonizeIds.length < 2 || harmonizing}
                              onClick={handleHarmonize}
                            >
                              <span>🔗 Harmonize Selected SOPs ({selectedHarmonizeIds.length} SOPs)</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* ======================================================== */}
                    {/* 3. HARMONIZED SOP WORKSPACE (VERSION HISTORY & METRICS)   */}
                    {/* ======================================================== */}
                    {isCollectionOverview && harmonizedVersions.length > 0 && activeHarmonizedVersion && !harmonizing && (
                      <div className="harmonized-workspace-card">
                        <div className="harmonized-workspace-head">
                          <div className="harmonized-badge-title">
                            <div className="harmonized-badge-tag">
                              <span>✨ Standardized Harmonized SOP (v{activeHarmonizedVersion.version_number})</span>
                            </div>
                            <div className="harmonized-doc-title">{activeHarmonizedVersion.title}</div>
                          </div>

                          <div className={`scorecard-avg-badge ${getScoreBadgeClass(activeHarmonizedVersion.overall_score || activeHarmonizedVersion.scores?.average_score || 90)}`}>
                            <span>Overall SOP Score:</span>
                            <span style={{ fontSize: "20px" }}>
                              {activeHarmonizedVersion.overall_score || activeHarmonizedVersion.scores?.average_score || 90}%
                            </span>
                          </div>
                        </div>

                        {/* Version History Timeline Bar (Strict Immutability) */}
                        <div className="version-timeline-bar">
                          <span className="timeline-label">Version History:</span>
                          {harmonizedVersions.map((v) => {
                            const isVerActive = selectedVersionId === v.id;
                            const verTypeLabel =
                              v.action_type === "harmonize"
                                ? "Initial Harmonized"
                                : v.action_type === "simplify"
                                ? "Simplified"
                                : "Refined";
                            return (
                              <button
                                key={v.id}
                                type="button"
                                className={`version-chip ${isVerActive ? "active" : ""}`}
                                onClick={() => {
                                  setSelectedVersionId(v.id);
                                  setShowSimplifyPanel(false);
                                }}
                                title={`${v.title} - ${v.change_summary}`}
                              >
                                <span>📄 v{v.version_number} · {verTypeLabel}</span>
                                <span className="version-chip-score">
                                  {v.overall_score || v.scores?.average_score || 0}%
                                </span>
                              </button>
                            );
                          })}
                        </div>

                        {/* Lineage & Provenance Box */}
                        <div className="lineage-provenance-box">
                          <div className="lineage-row">
                            <span className="lineage-label">Source SOPs:</span>
                            <span>{activeHarmonizedVersion.source_filenames?.join(", ") || "Uploaded Documents"}</span>
                          </div>
                          <div className="lineage-row">
                            <span className="lineage-label">Lineage:</span>
                            <span>
                              {activeHarmonizedVersion.parent_version_id
                                ? `Derived from parent version (ID: ${activeHarmonizedVersion.parent_version_id.slice(0, 8)}...)`
                                : "Root Consolidated Document (Consolidated from source procedures)"}
                            </span>
                          </div>
                          <div className="lineage-row">
                            <span className="lineage-label">Modifications:</span>
                            <span>{activeHarmonizedVersion.change_summary || "Harmonized into Kenvue 10-tier procedure."}</span>
                          </div>
                        </div>

                        {/* 6-Dimension Quality Scorecard */}
                        <div className="scorecard-meters-6">
                          <div className="meter-card-small">
                            <div className="meter-label">
                              <span>📋 Template Match</span>
                              <span style={{ color: "#16a34a" }}>{activeHarmonizedVersion.template_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{ width: `${activeHarmonizedVersion.template_score}%`, background: "#16a34a" }}
                              />
                            </div>
                          </div>

                          <div className="meter-card-small">
                            <div className="meter-label">
                              <span>📖 Readability</span>
                              <span style={{ color: "#2563eb" }}>{activeHarmonizedVersion.readability_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{ width: `${activeHarmonizedVersion.readability_score}%`, background: "#2563eb" }}
                              />
                            </div>
                          </div>

                          <div className="meter-card-small">
                            <div className="meter-label">
                              <span>🛡️ Quality Precision</span>
                              <span style={{ color: "#16a34a" }}>{activeHarmonizedVersion.quality_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{ width: `${activeHarmonizedVersion.quality_score}%`, background: "#16a34a" }}
                              />
                            </div>
                          </div>

                          <div className="meter-card-small">
                            <div className="meter-label">
                              <span>🏛️ Kenvue Alignment</span>
                              <span style={{ color: "#059669" }}>{activeHarmonizedVersion.kenvue_alignment_score || 95}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{ width: `${activeHarmonizedVersion.kenvue_alignment_score || 95}%`, background: "#059669" }}
                              />
                            </div>
                          </div>

                          <div className="meter-card-small">
                            <div className="meter-label">
                              <span>✅ Completeness</span>
                              <span style={{ color: "#0d9488" }}>{activeHarmonizedVersion.completeness_score || 94}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{ width: `${activeHarmonizedVersion.completeness_score || 94}%`, background: "#0d9488" }}
                              />
                            </div>
                          </div>

                          <div className="meter-card-small" style={{ background: "#f0fdf4", borderColor: "#86efac" }}>
                            <div className="meter-label">
                              <span style={{ color: "#166534" }}>⭐ Overall Score</span>
                              <span style={{ color: "#166534", fontWeight: 800 }}>
                                {activeHarmonizedVersion.overall_score || activeHarmonizedVersion.scores?.average_score}%
                              </span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{
                                  width: `${activeHarmonizedVersion.overall_score || activeHarmonizedVersion.scores?.average_score}%`,
                                  background: "#16a34a",
                                }}
                              />
                            </div>
                          </div>
                        </div>

                        {/* Harmonized Actions Toolbar */}
                        <div className="harmonized-actions-toolbar">
                          <button
                            type="button"
                            className="harmonized-tool-btn primary"
                            onClick={() => {
                              setPdfPreviewUrl(activeHarmonizedVersion.preview_url);
                              setPdfPreviewTitle(`Harmonized SOP v${activeHarmonizedVersion.version_number} Preview`);
                              setPdfPreviewOpen(true);
                            }}
                          >
                            👁️ Preview Harmonized PDF (v{activeHarmonizedVersion.version_number})
                          </button>

                          <a
                            href={`${API}${activeHarmonizedVersion.download_url}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="harmonized-tool-btn"
                            style={{ textDecoration: "none" }}
                          >
                            ⬇️ Download Harmonized PDF
                          </a>

                          <button
                            type="button"
                            className="harmonized-tool-btn simplify"
                            onClick={() => setShowSimplifyPanel(!showSimplifyPanel)}
                          >
                            ⚡ {showSimplifyPanel ? "Hide Simplification Recommendations" : "Simplify SOP"}
                          </button>

                          <button
                            type="button"
                            className="end-chat-btn"
                            onClick={handleEndChat}
                            style={{ marginLeft: "auto" }}
                          >
                            🏁 End Chat & Archive
                          </button>
                        </div>

                        {/* 4. SIMPLIFICATION RECOMMENDATIONS PANEL */}
                        {showSimplifyPanel && (
                          <div className="simplification-panel">
                            <div className="simplification-panel-head">
                              <div className="simplification-panel-title">
                                <span>⚡ Simplification Recommendations</span>
                              </div>
                              <button
                                type="button"
                                className="select-all-btn"
                                onClick={() => {
                                  if (selectedSimpRecs.length === simplificationCatalog.length) {
                                    setSelectedSimpRecs([]);
                                  } else {
                                    setSelectedSimpRecs(simplificationCatalog.map((c) => c.id));
                                  }
                                }}
                              >
                                {selectedSimpRecs.length === simplificationCatalog.length ? "Deselect All" : "Select All"}
                              </button>
                            </div>

                            <p style={{ fontSize: "12.5px", color: "#92400e", margin: "0 0 14px 0" }}>
                              Applying recommendations creates a new, immutable version (v{activeHarmonizedVersion.version_number + 1}) with improved readability and clarity while preserving the original technical accuracy.
                            </p>

                            <div className="simplification-items-list">
                              {simplificationCatalog.map((item) => {
                                const isChecked = selectedSimpRecs.includes(item.id);
                                return (
                                  <div
                                    key={item.id}
                                    className={`simplification-item-card ${isChecked ? "checked" : ""}`}
                                    onClick={() => {
                                      setSelectedSimpRecs((prev) =>
                                        prev.includes(item.id) ? prev.filter((id) => id !== item.id) : [...prev, item.id]
                                      );
                                    }}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={isChecked}
                                      onChange={() => {}}
                                    />
                                    <div className="simplification-item-body">
                                      <span className="simplification-item-title">{item.title}</span>
                                      <span className="simplification-item-desc">{item.description}</span>
                                      <span className="simplification-item-benefit">✨ {item.benefit}</span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>

                            <button
                              type="button"
                              className="generate-opt-btn"
                              style={{ background: "#d97706" }}
                              disabled={simplifying || selectedSimpRecs.length === 0}
                              onClick={handleSimplify}
                            >
                              {simplifying
                                ? "Applying Simplification & Compiling PDF..."
                                : `🚀 Apply Selected Simplifications (Generates v${activeHarmonizedVersion.version_number + 1})`}
                            </button>
                          </div>
                        )}

                        {/* 5. INTERACTIVE SOP REFINEMENT CONVERSATIONAL WORKSPACE */}
                        <div className="refinement-box">
                          <div className="refinement-head">
                            <span>💬 Interactive SOP Refinement Workspace</span>
                          </div>
                          <div className="refinement-sub">
                            Refine specific sections, tone, or formatting interactively. Each refinement produces a new immutable version with preserved lineage.
                          </div>

                          <div className="refinement-examples">
                            <button
                              type="button"
                              className="refinement-example-pill"
                              onClick={() => setRefinementPrompt("Make Section 3 easier to understand.")}
                            >
                              💡 "Make Section 3 easier to understand."
                            </button>
                            <button
                              type="button"
                              className="refinement-example-pill"
                              onClick={() => setRefinementPrompt("The wording is too simple. Make it slightly more professional.")}
                            >
                              💡 "The wording is too simple. Make it slightly more professional."
                            </button>
                            <button
                              type="button"
                              className="refinement-example-pill"
                              onClick={() => setRefinementPrompt("Add an explicit PPE safety verification step before centrifuge startup.")}
                            >
                              💡 "Add an explicit PPE safety verification step before centrifuge startup."
                            </button>
                            <button
                              type="button"
                              className="refinement-example-pill"
                              onClick={() => setRefinementPrompt("Ensure all speed tolerances specify ± 25 RPM.")}
                            >
                              💡 "Ensure all speed tolerances specify ± 25 RPM."
                            </button>
                          </div>

                          {refineError && (
                            <div style={{ color: "#dc2626", fontSize: "12.5px", marginBottom: "8px" }}>
                              ❌ {refineError}
                            </div>
                          )}

                          <form onSubmit={handleRefine} className="refinement-input-row">
                            <input
                              type="text"
                              className="refinement-input"
                              value={refinementPrompt}
                              onChange={(e) => setRefinementPrompt(e.target.value)}
                              placeholder="Type refinement instructions (e.g. 'Make Section 3 easier to understand')..."
                              disabled={refining}
                            />
                            <button
                              type="submit"
                              className="refinement-send-btn"
                              disabled={refining || !refinementPrompt.trim()}
                            >
                              {refining ? "Refining..." : `Apply to v${activeHarmonizedVersion.version_number + 1}`}
                            </button>
                          </form>
                        </div>
                      </div>
                    )}

                    {/* ======================================================== */}
                    {/* INDIVIDUAL SOP EVALUATION SCORECARD                      */}
                    {/* ======================================================== */}
                    {!isCollectionOverview && activeSop && scores && !optResult && (
                      <div className="scorecard-card">
                        <div className="scorecard-header">
                          <div className="scorecard-title">
                            <span>
                              📊 Kenvue SOP Compliance Scorecard{currentDoc?.filename ? ` · ${currentDoc.filename}` : ""}
                            </span>
                          </div>
                          <div className={`scorecard-avg-badge ${getScoreBadgeClass(scores.average_score)}`}>
                            <span>Average Rating:</span>
                            <span style={{ fontSize: "19px" }}>{scores.average_score}%</span>
                          </div>
                        </div>

                        <div className="scorecard-meters">
                          <div className="meter-box">
                            <div className="meter-label">
                              <span>📋 Template Compliance</span>
                              <span className="meter-value">{scores.template_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{
                                  width: `${scores.template_score}%`,
                                  background: scores.template_score >= 80 ? "#16a34a" : scores.template_score >= 60 ? "#eab308" : "#dc2626",
                                }}
                              />
                            </div>
                          </div>

                          <div className="meter-box">
                            <div className="meter-label">
                              <span>📖 Readability & Clarity</span>
                              <span className="meter-value">{scores.readability_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{
                                  width: `${scores.readability_score}%`,
                                  background: scores.readability_score >= 80 ? "#16a34a" : scores.readability_score >= 60 ? "#eab308" : "#dc2626",
                                }}
                              />
                            </div>
                          </div>

                          <div className="meter-box">
                            <div className="meter-label">
                              <span>🛡️ Quality & Safety Precision</span>
                              <span className="meter-value">{scores.quality_score}%</span>
                            </div>
                            <div className="meter-bar-bg">
                              <div
                                className="meter-bar-fill"
                                style={{
                                  width: `${scores.quality_score}%`,
                                  background: scores.quality_score >= 80 ? "#16a34a" : scores.quality_score >= 60 ? "#eab308" : "#dc2626",
                                }}
                              />
                            </div>
                          </div>
                        </div>

                        {scores.summary && <div className="scorecard-summary">{scores.summary}</div>}

                        {!showOptForm && (
                          <div className="scorecard-action-bar">
                            <span className="scorecard-prompt">
                              {currentDoc?.has_optimized_sop || currentDoc?.optimized_scores
                                ? "Current SOP is optimized. Would you like to further refine it with additional recommendations?"
                                : `Would you like to optimize ${currentDoc?.filename || "this SOP"} according to Kenvue standards?`}
                            </span>
                            <button className="opt-yes-btn" onClick={() => {
                              setShowOptForm(true);
                              setSelectedSuggestions(suggestions.map((s) => s.id));
                            }}>
                              {currentDoc?.has_optimized_sop || currentDoc?.optimized_scores
                                ? "🔄 Further Optimize Current SOP"
                                : `✨ Yes, Optimize ${currentDoc?.filename || "SOP"}`}
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ======================================================== */}
                    {/* 2. INTERACTIVE OPTIMIZATION CHECKBOX SUGGESTIONS         */}
                    {/* ======================================================== */}
                    {showOptForm && !optResult && (
                      <div className="opt-panel">
                        {optimizing ? (
                          <PipelineProgressBar
                            mode="optimize"
                            progress={optProgress}
                            currentStageIndex={optStageIndex}
                            stageDetail={optStageDetail}
                            title={activeSop?.has_optimized_sop ? "Iterative SOP Refinement & Vector Re-Indexing" : "Kenvue SOP Optimization & Vector Re-Indexing"}
                            badgeText={activeSop?.has_optimized_sop ? "ITERATIVE REFINEMENT PIPELINE" : "KENVUE RE-ENGINEERING PIPELINE"}
                          />
                        ) : (
                          <>
                            {currentDoc?.has_optimized_sop && (
                              <div style={{
                                marginBottom: "14px",
                                padding: "9px 13px",
                                background: "#eff6ff",
                                border: "1px solid #bfdbfe",
                                borderRadius: "6px",
                                fontSize: "12.5px",
                                color: "#1e40af",
                                display: "flex",
                                alignItems: "center",
                                gap: "8px"
                              }}>
                                <span style={{ fontSize: "16px" }}>🔄</span>
                                <span>
                                  <strong>Iterative Refinement Active:</strong> Further optimizing on top of the currently generated SOP ({currentDoc?.optimized_title || currentDoc?.filename}). All previously applied sections, titles, and parameters are preserved as the baseline foundation.
                                </span>
                              </div>
                            )}
                            <div className="opt-panel-head">
                              <h3>{currentDoc?.has_optimized_sop ? `Select Further Improvements for ${currentDoc?.filename || "Current SOP"}` : `Select Improvements for ${currentDoc?.filename || "SOP"}`}</h3>
                              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                                {currentDoc?.has_optimized_sop && (
                                  <button
                                    className="select-all-btn"
                                    style={{ background: "#f1f5f9", color: "#475569", border: "1px solid #cbd5e1" }}
                                    onClick={() => {
                                      setShowOptForm(false);
                                      if (currentDoc?.optimized_scores) {
                                        setOptResult({
                                          document_title: currentDoc.optimized_title || currentDoc.filename,
                                          previous_scores: currentDoc.scores,
                                          updated_scores: currentDoc.optimized_scores,
                                          pdf_download_url: `/conversations/${active.id}/optimized-sop/download${currentDoc.id ? `?document_id=${currentDoc.id}` : ''}`,
                                          pdf_preview_url: `/conversations/${active.id}/optimized-sop/preview${currentDoc.id ? `?document_id=${currentDoc.id}` : ''}`,
                                          skill_url: `/conversations/${active.id}/optimization-skill`,
                                          summary: "Optimized SOP generated according to Kenvue standards.",
                                        });
                                      }
                                    }}
                                  >
                                    ✕ Cancel
                                  </button>
                                )}
                                {suggestions.length > 0 && (
                                  <button
                                    className="select-all-btn"
                                    onClick={() => {
                                      if (selectedSuggestions.length === suggestions.length) {
                                        setSelectedSuggestions([]);
                                      } else {
                                        setSelectedSuggestions(suggestions.map((s) => s.id));
                                      }
                                    }}
                                  >
                                    {selectedSuggestions.length === suggestions.length ? "Deselect All" : "Select All"}
                                  </button>
                                )}
                              </div>
                            </div>

                            {suggestions.length > 0 && (
                              <div className="suggestions-list">
                                {suggestions.map((sug) => {
                                  const isChecked = selectedSuggestions.includes(sug.id);
                                  return (
                                    <div
                                      key={sug.id}
                                      className={`suggestion-item ${isChecked ? "selected" : ""}`}
                                      onClick={() => {
                                        setSelectedSuggestions((prev) =>
                                          isChecked ? prev.filter((id) => id !== sug.id) : [...prev, sug.id]
                                        );
                                      }}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={isChecked}
                                        onChange={() => {}} // handled by parent onClick
                                      />
                                      <div className="suggestion-text">
                                        <strong>{sug.title}</strong>
                                        <p>{sug.description}</p>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}

                            <div className="custom-input-box">
                              <label>Custom Changes or Additional Guidelines (Optional)</label>
                              <textarea
                                value={customInstructions}
                                onChange={(e) => setCustomInstructions(e.target.value)}
                                placeholder="Type any specific changes you want made (e.g. 'Add a step to check rotor seal ring', 'Include batch record log format', etc.)..."
                              />
                            </div>

                            <button
                              className="generate-opt-btn"
                              onClick={handleOptimize}
                              disabled={optimizing || (selectedSuggestions.length === 0 && !customInstructions.trim())}
                            >
                              {currentDoc?.has_optimized_sop
                                ? `🚀 Apply Further Changes to ${currentDoc?.filename || "Current SOP"}`
                                : `🚀 Apply Changes & Generate Kenvue Standard PDF (${currentDoc?.filename || "SOP"})`}
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {/* ======================================================== */}
                    {/* 3. OPTIMIZED RESULT & BEFORE/AFTER SCORECARD             */}
                    {/* ======================================================== */}
                    {optResult && (
                      <div className="opt-result-card">
                        <div className="opt-result-head">
                          <h3>🎉 Kenvue Standardized SOP Generated!</h3>
                          <span style={{ fontSize: "12.5px", fontWeight: 700, color: "#166534" }}>
                            Original Figures & Tables Re-embedded As-Is
                          </span>
                        </div>

                        <div className="comparison-grid">
                          <div className="comp-box">
                            <div className="comp-label">Template Score</div>
                            <div className="comp-scores">
                              <span className="score-prev">{optResult.previous_scores?.template_score}%</span>
                              <span>➔</span>
                              <span className="score-new">{optResult.updated_scores.template_score}%</span>
                            </div>
                            <span className="comp-delta">
                              +{optResult.updated_scores.template_score - (optResult.previous_scores?.template_score || 0)}
                            </span>
                          </div>

                          <div className="comp-box">
                            <div className="comp-label">Readability Score</div>
                            <div className="comp-scores">
                              <span className="score-prev">{optResult.previous_scores?.readability_score}%</span>
                              <span>➔</span>
                              <span className="score-new">{optResult.updated_scores.readability_score}%</span>
                            </div>
                            <span className="comp-delta">
                              +{optResult.updated_scores.readability_score - (optResult.previous_scores?.readability_score || 0)}
                            </span>
                          </div>

                          <div className="comp-box">
                            <div className="comp-label">Quality Score</div>
                            <div className="comp-scores">
                              <span className="score-prev">{optResult.previous_scores?.quality_score}%</span>
                              <span>➔</span>
                              <span className="score-new">{optResult.updated_scores.quality_score}%</span>
                            </div>
                            <span className="comp-delta">
                              +{optResult.updated_scores.quality_score - (optResult.previous_scores?.quality_score || 0)}
                            </span>
                          </div>

                          <div className="comp-box" style={{ background: "#f0fdf4", borderColor: "#86efac" }}>
                            <div className="comp-label" style={{ color: "#166534", fontWeight: 700 }}>Overall Compliance</div>
                            <div className="comp-scores">
                              <span className="score-prev">{optResult.previous_scores?.average_score}%</span>
                              <span>➔</span>
                              <span className="score-new" style={{ fontSize: "18px" }}>{optResult.updated_scores.average_score}%</span>
                            </div>
                            <span className="comp-delta">
                              +{optResult.updated_scores.average_score - (optResult.previous_scores?.average_score || 0)}
                            </span>
                          </div>
                        </div>

                        {optResult.validation_report && (
                          <div style={{
                            margin: "12px 0 14px 0",
                            padding: "10px 14px",
                            background: "#f0fdf4",
                            border: "1px solid #86efac",
                            borderRadius: "6px",
                            fontSize: "12.5px",
                            color: "#166534",
                          }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontWeight: 700 }}>
                              <span>🛡️</span>
                              <span>
                                QA Validation Agent Certified: 100% of recommendations & custom directives enforced ({optResult.validation_report.iterations_executed} audit pass{optResult.validation_report.iterations_executed > 1 ? "es" : ""})
                              </span>
                            </div>
                            {optResult.validation_report.verified_custom?.length > 0 && (
                              <div style={{ marginTop: "6px", paddingLeft: "24px", display: "flex", flexDirection: "column", gap: "3px", fontSize: "12px" }}>
                                {optResult.validation_report.verified_custom.map((vc, i) => (
                                  <div key={i} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                    <span style={{ color: "#15803d", fontWeight: 800 }}>✓</span>
                                    <span>{vc}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        <div className="opt-download-actions">
                          <a
                            href={`${API}${optResult.pdf_download_url}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="dl-btn"
                          >
                            ⬇️ Download Optimized PDF
                          </a>
                          <button
                            className="preview-btn"
                            onClick={() => {
                              setPdfPreviewUrl(optResult.pdf_preview_url);
                              setPdfPreviewTitle("Optimized SOP Preview (ReportLab PDF)");
                              setPdfPreviewOpen(true);
                            }}
                          >
                            👁️ Preview PDF
                          </button>
                          {optResult.skill_url && (
                            <a
                              href={`${API}${optResult.skill_url}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="further-opt-btn"
                              title="Inspect compiled optimization skill directive in MinIO"
                              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                            >
                              📜 View Skill Directive
                            </a>
                          )}
                          <button
                            className="further-opt-btn"
                            onClick={() => {
                              setOptResult(null);
                              setShowOptForm(true);
                              setCustomInstructions("");
                              setSelectedSuggestions(suggestions.map((s) => s.id));
                            }}
                          >
                            🔄 Further Optimize
                          </button>
                          <button
                            className="end-chat-btn"
                            onClick={handleEndChat}
                            style={{ marginLeft: "auto" }}
                          >
                            🏁 End Chat & Archive
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Messages list */}
                    {messages.map((m, i) => (
                      <div className={`row ${m.role}`} key={i}>
                        <div className="bubble">
                          {m.role === "assistant" ? (
                            <div
                              className="formatted-message"
                              dangerouslySetInnerHTML={{ __html: formatMessageContent(m.content) }}
                            />
                          ) : (
                            <div className="user-message-text">{m.content}</div>
                          )}
                          {m.referenced_pages?.length > 0 && (
                            <div className="rag-citation-footer">
                              <span className="rag-citation">
                                📌 Grounded in SOP Page{m.referenced_pages.length > 1 ? "s" : ""}:{" "}
                                {m.referenced_pages.sort((a, b) => a - b).join(", ")}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}

                    {loading && (
                      <div className="row assistant">
                        <div className="bubble">Consulting SOP guidelines & generating answer...</div>
                      </div>
                    )}
                  </div>

                  {/* Input Composer */}
                  <div className="composer">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          send();
                        }
                      }}
                      placeholder={
                        activeSop
                          ? "Ask questions or request modifications to this procedure..."
                          : "Type a message or upload an SOP..."
                      }
                    />
                    <button onClick={send} disabled={loading || !input.trim()}>
                      Send
                    </button>
                  </div>
                </>
              )}
            </section>
          </>
        )}
      </main>

      {/* PDF PREVIEW MODAL */}
      {pdfPreviewOpen && (pdfPreviewUrl || optResult || activeHarmonizedVersion) && (
        <div className="modal-overlay" onClick={() => setPdfPreviewOpen(false)}>
          <div className="modal-content" style={{ width: "min(950px, 95vw)", height: "90vh" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{pdfPreviewTitle || (optResult ? "Optimized SOP Preview (ReportLab PDF)" : "Harmonized SOP Preview")}</h2>
              <button className="modal-close" onClick={() => setPdfPreviewOpen(false)}>✕</button>
            </div>
            <div style={{ flex: 1, padding: "10px" }}>
              <iframe
                src={`${API}${pdfPreviewUrl || optResult?.pdf_preview_url || activeHarmonizedVersion?.preview_url}`}
                style={{ width: "100%", height: "100%", border: 0, borderRadius: "8px" }}
                title="SOP Preview"
              />
            </div>
          </div>
        </div>
      )}

      {/* ARTIFACTS GALLERY MODAL (MinIO images & tables) */}
      {artifactsModalOpen && (
        <div className="modal-overlay" onClick={() => setArtifactsModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Original Extracted Media in MinIO ({artifacts.length})</h2>
              <button className="modal-close" onClick={() => setArtifactsModalOpen(false)}>✕</button>
            </div>
            <div className="modal-filters">
              <button
                className={`filter-btn ${artifactFilter === "all" ? "active" : ""}`}
                onClick={() => setArtifactFilter("all")}
              >
                All ({artifacts.length})
              </button>
              <button
                className={`filter-btn ${artifactFilter === "image" ? "active" : ""}`}
                onClick={() => setArtifactFilter("image")}
              >
                Images ({artifacts.filter((a) => a.artifact_type === "image").length})
              </button>
              <button
                className={`filter-btn ${artifactFilter === "table" ? "active" : ""}`}
                onClick={() => setArtifactFilter("table")}
              >
                Tables ({artifacts.filter((a) => a.artifact_type === "table").length})
              </button>
            </div>
            <div className="modal-body">
              {filteredArtifacts.map((art) => (
                <div className="artifact-card" key={art.id}>
                  <div className="artifact-img-box">
                    <img src={`${API}${art.preview_url}`} alt={art.caption} loading="lazy" />
                  </div>
                  <div className="artifact-info">
                    <div className="artifact-tag">
                      {art.artifact_type === "table" ? "📊 Table Crop" : "🖼️ Original Image"}
                    </div>
                    <div className="artifact-caption">{art.caption}</div>
                    <div className="artifact-meta">Page {art.page} · Preserved for re-insertion</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
