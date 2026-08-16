
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from typing import List, Dict, Any, Tuple

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE = Path(__file__).parent
POLICIES = json.loads((BASE / "data" / "policies.json").read_text(encoding="utf-8"))

CHUNKS: List[Dict[str, Any]] = []
for policy in POLICIES:
    for section in policy["sections"]:
        CHUNKS.append({
            "policy_id": policy["id"],
            "title": policy["title"],
            "effective_date": policy["effective_date"],
            "section": section["section"],
            "heading": section["heading"],
            "topic": section.get("topic", []),
            "text": section["text"],
        })

CORPUS = [f'{c["title"]} {c["heading"]} {" ".join(c["topic"])} {c["text"]}' for c in CHUNKS]
VECTORIZER = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
MATRIX = VECTORIZER.fit_transform(CORPUS)

app = FastAPI(title="Aegis AI Governance Assistant")

MAX_QUESTION_CHARS = int(os.getenv("DEMO_MAX_QUESTION_CHARS", "500"))
RATE_LIMIT_PER_HOUR = int(os.getenv("DEMO_RATE_LIMIT_PER_HOUR", "8"))
RATE_WINDOW_SECONDS = 3600

_request_log = defaultdict(deque)
_request_lock = Lock()

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)

AI_DOMAIN_TERMS = [
    "ai", "artificial intelligence", "chatbot", "chatgpt", "claude", "copilot",
    "model", "prompt", "generative", "firmai", "researchai", "approved tool",
    "public chatbot", "public ai", "client", "matter", "confidential", "privileged",
    "privilege", "work product", "restricted", "data classification",
    "information security", "human review", "hallucination", "retention",
    "disclosure", "uploaded", "pasted", "summarize", "draft", "memo",
    "filing", "court", "legal advice", "legal research"
]

OUT_OF_DOMAIN_TERMS = [
    "maternity leave", "parental leave", "vacation", "pto", "paid time off",
    "health insurance", "dental insurance", "401k", "401(k)", "retirement",
    "parking", "dress code", "holiday schedule", "tuition", "salary",
    "expense reimbursement"
]

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def enforce_rate_limit(request: Request):
    ip = client_ip(request)
    now = time.time()
    cutoff = now - RATE_WINDOW_SECONDS
    with _request_lock:
        q = _request_log[ip]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=f"Demo limit reached. Please try again later. This public portfolio demo allows {RATE_LIMIT_PER_HOUR} questions per hour per visitor."
            )
        q.append(now)

def detect_intent(question: str) -> str:
    q = question.lower()
    if any(x in q for x in ["accidentally", "by mistake", "accidental", "pasted", "uploaded"]) and \
       any(x in q for x in ["unapproved", "public chatbot", "public ai", "consumer chatbot"]):
        return "incident"
    if any(x in q for x in ["public chatbot", "public chatgpt", "consumer chatbot", "public ai"]) and \
       any(x in q for x in ["client", "contract", "matter", "confidential", "privileged", "work product"]):
        return "public_ai_confidential"
    if ("firmai" in q or "firm ai" in q) and \
       any(x in q for x in ["privileged", "privilege", "work product", "attorney-client"]):
        return "privileged_firmai"
    if any(x in q for x in ["privileged", "privilege", "work product", "attorney-client"]):
        return "privileged"
    if any(x in q for x in ["restricted", "sealed", "credentials", "encryption key"]):
        return "restricted"
    if any(x in q for x in ["court", "filing", "client deliverable", "legal advice", "citation", "citations"]):
        return "high_impact_review"
    return "general"

def knowledge_base_covers(question: str, intent: str) -> Tuple[bool, str]:
    q = question.lower()
    if any(term in q for term in OUT_OF_DOMAIN_TERMS) and not any(
        term in q for term in ["ai", "chatbot", "chatgpt", "claude", "firmai", "generative"]
    ):
        return False, "This question is outside the AI-governance knowledge base."
    has_domain_signal = any(term in q for term in AI_DOMAIN_TERMS)
    if not has_domain_signal and intent == "general":
        return False, "The question does not appear to concern AI use, data handling, confidentiality, review, or escalation."
    return True, ""

def expand_question(question: str, intent: str) -> str:
    expansions = {
        "incident": "accidental disclosure unapproved AI tool stop using preserve evidence notify AI Governance Information Security responsible attorney",
        "public_ai_confidential": "public consumer chatbots approved only public information client confidential matter data classification approved secure tool minimum necessary",
        "privileged_firmai": "privileged communications attorney work product FirmAI Secure approved firm systems responsible attorney appropriate matter client-specific restrictions",
        "privileged": "privileged communications attorney work product approved firm systems responsible attorney confidentiality client-specific restrictions",
        "restricted": "restricted information Information Security responsible attorney explicit approval",
        "high_impact_review": "human review verify legal authorities citations high impact substantive attorney review",
        "general": ""
    }
    return question + " " + expansions.get(intent, "")

def scenario_boost(chunk: Dict[str, Any], intent: str) -> float:
    pid, sec = chunk["policy_id"], chunk["section"]
    topic = set(chunk.get("topic", []))
    boost = 0.0
    if intent == "incident":
        if pid == "ESC-006" and sec == "2.1": boost += 1.20
        if "incident" in topic or "accidental_disclosure" in topic: boost += 0.55
        if "prevention" in topic: boost -= 0.15
    elif intent == "public_ai_confidential":
        if pid == "TOOLS-005" and sec == "1.3": boost += 1.10
        if pid == "CONF-003" and sec == "1.1": boost += 0.65
        if pid == "DATA-002" and sec == "2.3": boost += 0.55
        if pid == "CONF-003" and sec == "4.1": boost += 0.20
    elif intent == "privileged_firmai":
        if pid == "CONF-003" and sec == "2.1": boost += 1.20
        if pid == "TOOLS-005" and sec == "1.1": boost += 0.90
        if pid == "CONF-003" and sec == "3.1": boost += 0.45
    elif intent == "privileged":
        if pid == "CONF-003" and sec == "2.1": boost += 1.20
        if pid == "CONF-003" and sec == "3.1": boost += 0.45
    elif intent == "restricted":
        if pid == "DATA-002" and sec == "2.4": boost += 1.10
        if pid == "ESC-006" and sec == "1.1": boost += 0.75
    elif intent == "high_impact_review":
        if pid == "REVIEW-004" and sec in {"1.1","2.1","3.1"}: boost += 0.75
    return boost

def retrieve(question: str, intent: str, top_k: int = 4):
    expanded = expand_question(question, intent)
    q = VECTORIZER.transform([expanded])
    semantic_scores = cosine_similarity(q, MATRIX)[0]
    scored = []
    for idx, base_score in enumerate(semantic_scores):
        final_score = float(base_score) + scenario_boost(CHUNKS[idx], intent)
        scored.append((idx, final_score, float(base_score)))
    scored.sort(key=lambda x: x[1], reverse=True)
    results = []
    for rank, (idx, final_score, base_score) in enumerate(scored[:top_k]):
        item = dict(CHUNKS[idx])
        item["score"] = round(base_score, 4)
        item["rank_score"] = round(final_score, 4)
        item["source_role"] = "primary" if rank == 0 else "supporting"
        results.append(item)
    return results

def make_demo_answer(question: str, intent: str, sources):
    if intent == "public_ai_confidential":
        return {
            "answer":"No. Do not submit the client material to a public consumer AI tool. Public chatbots are approved only for Public information. Client and matter information must remain in an AI environment approved for the relevant data classification. If AI-assisted summarization is appropriate for the matter, use an approved secure tool, provide only the minimum information necessary, and complete the required human review.",
            "action":"DO NOT USE PUBLIC AI","risk":"High",
            "human_review":"Required before any client-facing or substantive use"
        }
    if intent == "privileged_firmai":
        return {
            "answer":"Yes, potentially, but not automatically. FirmAI Secure is approved for Confidential information, but privileged communications and attorney work product require heightened care. Use it only when the responsible attorney determines that AI use is appropriate for the matter and no client-specific or matter-specific restriction prohibits the use. Restricted information requires separate approval.",
            "action":"USE ONLY AFTER MATTER-LEVEL CONFIRMATION","risk":"Elevated",
            "human_review":"Responsible attorney confirmation and substantive human review required"
        }
    if intent == "incident":
        return {
            "answer":"Stop using the unapproved tool and escalate immediately. Do not delete or alter evidence of what occurred. Promptly notify the AI Governance Team and Information Security, and inform the responsible attorney because client or matter information is involved. Do not attempt to resolve or conceal the incident on your own.",
            "action":"ESCALATE IMMEDIATELY","risk":"High",
            "human_review":"Immediate human escalation required"
        }
    if intent == "restricted":
        return {
            "answer":"Do not proceed without explicit approval. Restricted information may be submitted to an AI system only when Information Security and the responsible attorney have approved the specific use case.",
            "action":"ESCALATE / OBTAIN APPROVAL","risk":"High",
            "human_review":"Explicit Information Security and attorney approval required"
        }
    if intent == "high_impact_review":
        return {
            "answer":"AI may assist with the work, but a qualified human must review the output before use. Material facts, legal authorities, quotations, citations, calculations, and substantive conclusions must be independently verified. Higher-impact work requires deeper attorney review.",
            "action":"PROCEED WITH SUBSTANTIVE HUMAN REVIEW","risk":"Elevated",
            "human_review":"Required"
        }
    primary = sources[0] if sources else None
    if not primary:
        return {"answer":"The available policy library does not provide enough support for a reliable answer.",
                "action":"ESCALATE / CONFIRM","risk":"Unknown","human_review":"Required"}
    return {
        "answer":f"The most relevant firm guidance is {primary['title']} §{primary['section']}. {primary['text']}",
        "action":"FOLLOW PRIMARY POLICY GUIDANCE","risk":"Context dependent",
        "human_review":"Use professional judgment and escalate if the situation is uncertain"
    }

def unsupported_answer(reason: str):
    return {
        "answer":"I could not find a policy in the available AI-governance knowledge base that directly addresses this question. I should not infer a firm rule from unrelated policies. Please consult the appropriate firm resource or the AI Governance Team.",
        "action":"KNOWLEDGE BASE DOES NOT COVER THIS","risk":"Unknown",
        "human_review":"Consult the appropriate firm resource","coverage_reason":reason
    }

def claude_synthesis(question: str, intent: str, sources):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        context = "\n\n".join(
            f"[{s['source_role'].upper()} | {s['policy_id']} | {s['title']} | §{s['section']} {s['heading']}]\n{s['text']}"
            for s in sources
        )
        system = """You are Aegis, an internal AI-use policy assistant for a fictional law firm.
Answer ONLY from supplied policy excerpts. Treat the PRIMARY source as controlling unless a SUPPORTING source adds a narrower restriction. Reconcile policies rather than merely quoting them. For incidents, prioritize immediate response requirements. Never invent firm rules, legal conclusions, or facts. If the excerpts are insufficient, recommend escalation. State what the user should do, why, and what human review is required. Describe only what fictional firm policy permits. Be concise and professional."""
        prompt = f"""SCENARIO INTENT: {intent}

USER QUESTION:
{question}

RETRIEVED FIRM POLICY EXCERPTS:
{context}

Write a concise, direct answer. Do not merely restate the policy text."""
        message = client.messages.create(
            model=model,
            max_tokens=350,
            system=system,
            messages=[{"role":"user","content":prompt}],
        )
        answer = "".join(block.text for block in message.content if getattr(block, "type", None) == "text").strip()
        guardrail = make_demo_answer(question, intent, sources)
        guardrail["answer"] = answer
        return guardrail
    except Exception:
        return None

@app.get("/health")
def health():
    return {"status":"ok"}

@app.post("/api/ask")
def ask(req: AskRequest, request: Request):
    enforce_rate_limit(request)
    question = req.question.strip()
    intent = detect_intent(question)
    covered, reason = knowledge_base_covers(question, intent)
    if not covered:
        result = unsupported_answer(reason)
        return {"question":question,"intent":"out_of_domain",**result,"sources":[],"mode":"coverage_guardrail"}
    sources = retrieve(question, intent)
    result = claude_synthesis(question, intent, sources) or make_demo_answer(question, intent, sources)
    return {
        "question":question,"intent":intent,**result,"sources":sources,
        "mode":"claude" if os.getenv("ANTHROPIC_API_KEY") else "demo"
    }

@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
