"""AI pages: vector index management, one-shot Ask and multi-turn Chat."""

from __future__ import annotations

import io
import uuid
from collections import OrderedDict

from flask import flash, redirect, render_template, request, send_file, session, url_for
from markupsafe import escape

from mosaic.services import (
    RAG_MODES,
    build_filters,
    format_answer,
    select_cached_papers,
    subset_uids,
)
from mosaic.ui.routes.common import (
    app_cache,
    app_cfg,
    app_version,
    bp,
    form_flag,
    job_manager,
    poll_html,
    read_uploaded_dois,
    safe_int,
)

# ---------------------------------------------------------------------------
# RAG — Index, Ask, Chat
# ---------------------------------------------------------------------------

# In-process chat history: session_id → list of messages
# ({"role": "user"|"assistant", "content": str, "sources"?: [...], "error"?: bool}).
# Bounded so a long-running UI does not grow without limit.
_CHAT_MAX_SESSIONS = 50
_CHAT_MAX_MESSAGES = 60
_chat_histories: OrderedDict[str, list[dict]] = OrderedDict()


def _chat_history(sid: str) -> list[dict]:
    history = _chat_histories.setdefault(sid, [])
    _chat_histories.move_to_end(sid)
    while len(_chat_histories) > _CHAT_MAX_SESSIONS:
        _chat_histories.popitem(last=False)
    del history[:-_CHAT_MAX_MESSAGES]
    return history


def _chat_sid() -> str:
    session.permanent = True
    return session.setdefault("chat_id", str(uuid.uuid4()))


def _rag_index_status(cache):
    """Return dict with index stats (and problems to fix) for the template."""
    from mosaic.config import get_embedding_cfg
    from mosaic.rag import index_health

    cfg = app_cfg()
    return {
        "total_papers": cache.count_papers(),
        "indexed_count": len(cache.get_indexed_uids()),
        # configured model vs. the one the existing index was built with
        "embedding_model": get_embedding_cfg(cfg).get("model", ""),
        "indexed_model": cache.get_rag_meta("embedding_model") or "",
        "health": index_health(cfg, cache),
    }


@bp.route("/rag")
def rag_landing():
    cache = app_cache()
    info = _rag_index_status(cache)
    cfg = app_cfg()
    llm_configured = bool(cfg.get("llm", {}).get("provider") and cfg.get("llm", {}).get("api_key"))
    return render_template(
        "rag_landing.html", version=app_version(), llm_configured=llm_configured, **info
    )


@bp.route("/rag/index")
def rag_index_page():
    cache = app_cache()
    info = _rag_index_status(cache)
    return render_template("rag_index.html", version=app_version(), **info)


def _run_rag_index(cfg, reindex, batch_size, query="", dois=None, enrich=False):
    """Executed in a worker thread — same pipeline as ``mosaic index``."""
    from mosaic.db import Cache
    from mosaic.rag import index_health, index_papers

    with Cache(cfg["db_path"]) as cache:
        papers = select_cached_papers(cache, query=query, dois=dois)
        if papers is None:
            papers = cache.get_all_papers()
        if not papers:
            return {"newly": 0, "skipped": 0, "full_text": 0, "total": 0, "notes": []}

        notes: list[str] = []
        newly, skipped, full_text = index_papers(
            papers, cfg, cache, reindex=reindex, progress=False, batch_size=batch_size
        )
        if enrich or cfg.get("rag", {}).get("citations", {}).get("enabled", False):
            from mosaic.citations.enrichment import enrich_citations

            try:
                n_enriched, n_skipped = enrich_citations(papers, cfg, cache, reindex=reindex)
                notes.append(
                    f"Citation edges stored for {n_enriched} paper(s), {n_skipped} skipped."
                )
            except Exception as e:
                notes.append(f"Citation enrichment warning: {e}")
        notes.extend(index_health(cfg, cache))
        return {
            "newly": newly,
            "skipped": skipped,
            "full_text": full_text,
            "total": len(papers),
            "notes": notes,
        }


@bp.route("/rag/index", methods=["POST"])
def rag_index_submit():
    dois, error = read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    batch_size = safe_int(request.form.get("batch_size", 96), default=96, lo=1, hi=512)
    job_id = job_manager().submit(
        _run_rag_index,
        app_cfg(),
        form_flag("reindex"),
        batch_size,
        request.form.get("query", "").strip(),
        dois,
        form_flag("enrich_citations"),
    )
    status_url = url_for("ui.rag_index_status", job_id=job_id)
    return poll_html(status_url, "#index-job", "Indexing papers&hellip;")


@bp.route("/rag/index/status/<job_id>")
def rag_index_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.rag_index_status", job_id=job_id)
        return poll_html(status_url, "#index-job", "Indexing papers&hellip;")
    job_manager().pop(job_id)
    if job.status == "error":
        return f"<article><mark>Indexing failed: {escape(job.error_message)}</mark></article>"
    r = job.result
    if not r["total"]:
        return "<article>No matching papers in the cache. Run some searches first.</article>"
    html = (
        f"<article><ins>Done.</ins> {r['newly']} paper(s) newly indexed "
        f"({r['full_text']} full-text, {r['newly'] - r['full_text']} metadata-only), "
        f"{r['skipped']} skipped (already indexed), {r['total']} selected."
    )
    for note in r["notes"]:
        html += f"<br><small>{escape(note)}</small>"
    return html + "</article>"


@bp.route("/rag/ask")
def rag_ask_page():
    return render_template("rag_ask.html", version=app_version(), modes=RAG_MODES)


def _run_rag_ask(query, cfg, mode, top_k, subset_query, year, dois):
    """Executed in a worker thread — full RAG pipeline."""
    from mosaic.db import Cache
    from mosaic.rag import ask

    with Cache(cfg["db_path"]) as cache:
        pre_filter = subset_uids(cache, query=subset_query, dois=dois, year=year)
        answer, papers = ask(query, cfg, cache, mode=mode, k=top_k, pre_filter=pre_filter)
        return {"answer": answer, "papers": papers, "question": query, "mode": mode}


@bp.route("/rag/ask", methods=["POST"])
def rag_ask_submit():
    query = request.form.get("query", "").strip()
    if not query:
        return "<article>Please enter a question.</article>"

    mode = request.form.get("mode", "synthesis")
    if mode not in RAG_MODES:
        return f"<article>Unknown mode. Choose from: {', '.join(RAG_MODES)}.</article>"
    year = request.form.get("year", "").strip()
    if year:
        _, year_warning = build_filters(year=year)
        if year_warning:
            return f"<article>{escape(year_warning)}</article>"
    dois, error = read_uploaded_dois("file")
    if error:
        return f"<article>{escape(error)}</article>"
    top_k_raw = request.form.get("top_k", "").strip()
    top_k = safe_int(top_k_raw, default=10, lo=1, hi=50) if top_k_raw else None

    job_id = job_manager().submit(
        _run_rag_ask,
        query,
        app_cfg(),
        mode,
        top_k,
        request.form.get("subset_query", "").strip(),
        year,
        dois,
        meta={"show_sources": form_flag("show_sources")},
    )
    status_url = url_for("ui.rag_ask_status", job_id=job_id)
    return poll_html(status_url, "#ask-result", "Retrieving papers and generating answer&hellip;")


@bp.route("/rag/ask/status/<job_id>")
def rag_ask_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return "<article>Job not found.</article>"
    if job.status == "running":
        status_url = url_for("ui.rag_ask_status", job_id=job_id)
        return poll_html(
            status_url, "#ask-result", "Retrieving papers and generating answer&hellip;"
        )
    if job.status == "error":
        job_manager().pop(job_id)
        return f"<article><mark>Error: {escape(job.error_message)}</mark></article>"

    # Keep the job (until purged) so the answer can be downloaded
    result = job.result
    papers = result["papers"]
    html = f'<article><div class="rag-answer">{escape(result["answer"])}</div></article>'
    if papers:
        md_url = url_for("ui.rag_ask_export", job_id=job_id, format="md")
        json_url = url_for("ui.rag_ask_export", job_id=job_id, format="json")
        html += (
            f'<div class="export-bar"><strong>Save answer:</strong>'
            f'<a href="{md_url}" role="button" class="outline secondary">Markdown</a>'
            f'<a href="{json_url}" role="button" class="outline secondary">JSON</a></div>'
        )
    if job.meta.get("show_sources", True) and papers:
        html += '<details open><summary><strong>Source papers</strong></summary><ol class="source-list">'
        for p in papers:
            title = escape(p.title or "Untitled")
            authors = escape(", ".join(p.authors[:3]))
            year_str = escape(str(p.year or ""))
            detail_url = url_for("ui.paper_detail", uid=p.uid)
            html += f'<li><a href="{detail_url}">{title}</a> &mdash; {authors} ({year_str})</li>'
        html += "</ol></details>"
    return html


@bp.route("/rag/ask/export/<job_id>")
def rag_ask_export(job_id):
    job = job_manager().get(job_id)
    if job is None or job.status != "done":
        flash("This answer has expired. Please ask again.", "warning")
        return redirect(url_for("ui.rag_ask_page"))
    fmt = request.args.get("format", "md")
    if fmt not in ("md", "json"):
        return f"Unsupported export format: {escape(fmt)}", 400
    r = job.result
    content = format_answer(r["question"], r["mode"], r["answer"], r["papers"], fmt)
    return send_file(
        io.BytesIO(content.encode("utf-8")),
        mimetype="application/json" if fmt == "json" else "text/markdown",
        as_attachment=True,
        download_name=f"mosaic_answer.{fmt}",
    )


@bp.route("/rag/chat")
def rag_chat_page():
    history = _chat_history(_chat_sid())
    return render_template(
        "rag_chat.html",
        version=app_version(),
        thread_html=_render_chat_thread(history),
        modes=RAG_MODES,
    )


def _run_rag_chat(query, history, cfg, mode, subset_query):
    """Executed in a worker thread — one conversational turn (with memory)."""
    from mosaic.db import Cache
    from mosaic.rag import chat_turn

    with Cache(cfg["db_path"]) as cache:
        pre_filter = subset_uids(cache, query=subset_query) if subset_query else None
        answer, papers = chat_turn(query, history, cfg, cache, mode=mode, pre_filter=pre_filter)
        sources = [{"title": p.title, "uid": p.uid, "year": p.year} for p in papers]
        return {"answer": answer, "sources": sources}


def _render_chat_thread(history, thinking: bool = False) -> str:
    """Return HTML for the chat thread content."""
    if not history and not thinking:
        return '<p class="stats-line"><em>No messages yet. Ask your first question below.</em></p>'
    parts = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "assistant"
        content = escape(msg["content"])
        if role == "user":
            parts.append(f'<div class="chat-msg chat-user">{content}</div>')
            continue
        body = f'<div class="chat-md">{content}</div>'
        sources = msg.get("sources") or []
        if sources:
            items = "".join(
                f'<li><a href="{url_for("ui.paper_detail", uid=s["uid"])}">'
                f"{escape(s['title'] or 'Untitled')}</a> ({escape(str(s['year'] or '?'))})</li>"
                for s in sources
            )
            body += (
                f'<details class="chat-sources"><summary>Sources ({len(sources)})</summary>'
                f"<ol>{items}</ol></details>"
            )
        css = "chat-msg chat-assistant" + (" chat-error" if msg.get("error") else "")
        parts.append(f'<div class="{css}">{body}</div>')
    if thinking:
        parts.append(
            '<div class="chat-msg chat-assistant" style="opacity:.6;">'
            '<span aria-busy="true">Thinking&hellip;</span></div>'
        )
    return "\n".join(parts)


def _oob_poll(status_url: str) -> str:
    """OOB swap that keeps the poll trigger alive outside #chat-thread."""
    return (
        f'<div id="chat-poll" hx-swap-oob="true">'
        f'<div hx-get="{status_url}" hx-trigger="every 2s"'
        f' hx-target="#chat-thread" hx-swap="innerHTML"></div>'
        f"</div>"
    )


def _oob_poll_stop() -> str:
    """OOB swap that clears #chat-poll, stopping the poll loop."""
    return '<div id="chat-poll" hx-swap-oob="true"></div>'


@bp.route("/rag/chat/send", methods=["POST"])
def rag_chat_send():
    query = request.form.get("query", "").strip()
    mode = request.form.get("mode", "synthesis")
    sid = _chat_sid()
    history = _chat_history(sid)

    if not query:
        return _render_chat_thread(history)
    if mode not in RAG_MODES:
        mode = "synthesis"

    # Prior turns sent to the LLM: plain role/content, failed turns excluded
    prior = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if not m.get("error") and m["role"] in ("user", "assistant")
    ]
    history.append({"role": "user", "content": query})
    job_id = job_manager().submit(
        _run_rag_chat,
        query,
        prior,
        app_cfg(),
        mode,
        request.form.get("subset_query", "").strip(),
        meta={"sid": sid},
    )

    # Main swap → #chat-thread; OOB swap → #chat-poll (outside thread, survives swaps)
    status_url = url_for("ui.rag_chat_status", job_id=job_id)
    return _render_chat_thread(history, thinking=True) + "\n" + _oob_poll(status_url)


@bp.route("/rag/chat/status/<job_id>")
def rag_chat_status(job_id):
    job = job_manager().get(job_id)
    if job is None:
        return _render_chat_thread(_chat_history(_chat_sid())) + "\n" + _oob_poll_stop()

    sid = job.meta.get("sid") or _chat_sid()
    history = _chat_history(sid)
    if job.status == "running":
        status_url = url_for("ui.rag_chat_status", job_id=job_id)
        return _render_chat_thread(history, thinking=True) + "\n" + _oob_poll(status_url)

    job_manager().pop(job_id)
    if job.status == "error":
        # Drop the unanswered question from the context sent on later turns
        if history and history[-1]["role"] == "user":
            history[-1]["error"] = True
        history.append(
            {"role": "assistant", "content": f"[Error: {job.error_message}]", "error": True}
        )
    else:
        answered = bool(job.result["sources"])
        if not answered and history and history[-1]["role"] == "user":
            # "No indexed papers…" replies carry no context worth replaying
            history[-1]["error"] = True
        history.append(
            {
                "role": "assistant",
                "content": job.result["answer"],
                "sources": job.result["sources"],
                "error": not answered,
            }
        )

    return _render_chat_thread(history) + "\n" + _oob_poll_stop()


@bp.route("/rag/chat/clear", methods=["POST"])
def rag_chat_clear():
    _chat_histories.pop(_chat_sid(), None)
    return '<p class="stats-line"><em>Conversation cleared.</em></p>' + "\n" + _oob_poll_stop()
